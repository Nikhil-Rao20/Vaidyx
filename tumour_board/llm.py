"""Async client for the local vLLM servers: parallel calls, JSON-schema constrained outputs, image inputs, audit.

Constrained decoding only restricts which tokens may be emitted (valid JSON for the schema). Weights, precision and
sampling are untouched (bf16, greedy), so nothing here is accuracy-lossy.
"""
import asyncio, base64, hashlib, io, json, mimetypes, re, time
from typing import Any, AsyncIterator, Optional

import httpx

from . import config

_client: Optional[httpx.AsyncClient] = None
_queues: dict[str, asyncio.Semaphore] = {}  # one queue per model server URL, created lazily on first use

# Connection-level failures (the server is busy accepting connections, or dropped one) are retried with these delays
# (seconds). A read timeout (the 600 s budget) and HTTP error statuses are not retried.
_RETRY_DELAYS = (1, 2, 4)
_RETRYABLE = (httpx.ConnectError, httpx.ConnectTimeout, httpx.PoolTimeout, httpx.RemoteProtocolError, httpx.ReadError)


class LLMError(RuntimeError):
    pass


def client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(timeout=httpx.Timeout(600, connect=30), limits=httpx.Limits(max_connections=128))
    return _client


def _norm(base_url: str) -> str:
    return base_url.rstrip("/")


def _queue_size(base_url: str) -> int:
    """Reader's server -> reader size; reasoner's server -> reasoner size; any other server -> fallback size."""
    url, cfg, sizes = _norm(base_url), config.models(), config.concurrency()
    for role in ("reader", "reasoner"):
        if role in cfg and _norm(cfg[role]["base_url"]) == url:
            return sizes[role]
    return sizes["other"]


def _queue(base_url: str) -> asyncio.Semaphore:
    """The queue for one model server (cached per URL, not per role: roles on the same server share it)."""
    url = _norm(base_url)
    q = _queues.get(url)
    if q is None:
        q = _queues[url] = asyncio.Semaphore(_queue_size(url))
    return q


def _err(e: Exception) -> str:
    return f"{type(e).__name__}: {e}"


def _unreachable(role, m, e) -> LLMError:
    return LLMError(f"{role} model server unreachable at {m['base_url']} ({_err(e)})")


async def _retry_wait(role, attempt, e, audit):
    """Audit one connection-level failure and wait before the next attempt (outside the queue, so the slot is free)."""
    if audit:
        audit({"kind": "llm_retry", "role": role, "attempt": attempt, "error": _err(e)[:300]})
    await asyncio.sleep(_RETRY_DELAYS[attempt - 1])


def image_part(path_or_bytes, mime: str = None, max_side: int = None) -> dict:
    """Image content part. Large images are downscaled to max_side (long edge) only if larger."""
    from PIL import Image
    if isinstance(path_or_bytes, (bytes, bytearray)):
        raw = bytes(path_or_bytes)
    else:
        raw = open(path_or_bytes, "rb").read()
        mime = mime or mimetypes.guess_type(str(path_or_bytes))[0]
    max_side = max_side or config.OCR_MAX_SIDE
    im = Image.open(io.BytesIO(raw))
    if max(im.size) > max_side or im.mode not in ("RGB", "L"):
        im = im.convert("RGB")
        if max(im.size) > max_side:
            s = max_side / max(im.size); im = im.resize((int(im.size[0] * s), int(im.size[1] * s)), Image.LANCZOS)
        buf = io.BytesIO(); im.save(buf, "PNG"); raw = buf.getvalue(); mime = "image/png"
    return {"type": "image_url", "image_url": {"url": f"data:{mime or 'image/png'};base64," + base64.b64encode(raw).decode()}}


def _guided(role):
    # Default: validate-and-retry (no constrained decoding). Measured on our corpus as more accurate and it leaves the
    # model's token choices untouched; set "guided_json": true in models.json to use vLLM structured outputs instead.
    return config.models()[role].get("guided_json", False)


def skeleton(schema):
    """Human-readable JSON template of a schema (models follow examples better than raw JSON Schema)."""
    t = schema.get("type")
    if t == "object":
        return {k: skeleton(v) for k, v in schema.get("properties", {}).items()}
    if t == "array":
        return [skeleton(schema.get("items", {}))]
    if "enum" in schema:
        return "one of: " + " | ".join(map(str, schema["enum"]))
    if t == "boolean":
        return "true or false"
    if t in ("integer", "number"):
        return 0
    return schema.get("description") or "text"


def _payload(role, messages, max_tokens, temperature, json_schema, stream):
    m = config.models()[role]
    if json_schema is not None and not _guided(role):  # validate-and-retry mode: schema given as instructions only
        messages = messages[:-1] + [{**messages[-1], "content": _append_text(messages[-1]["content"],
                    "\n\nAnswer with only one JSON object (no prose, no code fences) with exactly this structure, filled in:\n" + json.dumps(skeleton(json_schema), indent=1))}]
        json_schema = None
    body: dict[str, Any] = {"model": m["model"], "messages": messages, "max_tokens": max_tokens, "temperature": temperature, "stream": stream}
    if json_schema is not None:
        # vLLM structured outputs; disable_any_whitespace stops the known "endless whitespace" failure of JSON grammars
        body["structured_outputs"] = {"json": json_schema, "disable_any_whitespace": True}
    if m.get("chat_template_kwargs"):
        body["chat_template_kwargs"] = m["chat_template_kwargs"]
    if stream:
        body["stream_options"] = {"include_usage": True}
    return m, body


def _append_text(content, extra):
    if isinstance(content, str):
        return content + extra
    return content + [{"type": "text", "text": extra}]


def parse_json_loose(text):
    """Parse the JSON object inside possibly chatty output; repairs the common trailing-comma slip."""
    t = text.strip()
    if "```" in t:
        t = re.sub(r"^.*?```(?:json)?\s*", "", t, count=1, flags=re.S)
        t = t.rsplit("```", 1)[0]
    i, j = t.find("{"), t.rfind("}")
    if i < 0 or j < 0:
        raise ValueError("no JSON object")
    body = t[i: j + 1]
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        return json.loads(re.sub(r",\s*([}\]])", r"\1", body))


async def chat(role: str, messages: list, *, json_schema: dict = None, max_tokens: int = 1024, temperature: float = 0.0,
               purpose: str = "", audit=None, _retries: int = 0) -> Any:
    """One completion. Returns parsed JSON when json_schema is given, else text. Logs to `audit` (callable) if given."""
    m, body = _payload(role, messages, max_tokens, temperature, json_schema, False)
    t0 = time.time()
    url = _norm(m["base_url"])
    for attempt in range(len(_RETRY_DELAYS) + 1):
        try:
            async with _queue(url):
                r = await client().post(url + "/chat/completions", json=body)
            break
        except _RETRYABLE as e:
            if attempt >= len(_RETRY_DELAYS):
                raise _unreachable(role, m, e) from e
            await _retry_wait(role, attempt + 1, e, audit)
        except httpx.HTTPError as e:
            raise _unreachable(role, m, e) from e
    if r.status_code != 200:
        raise LLMError(f"{role} model error {r.status_code}: {r.text[:300]}")
    d = r.json(); text = d["choices"][0]["message"].get("content") or ""
    finish = d["choices"][0].get("finish_reason")
    usage = d.get("usage", {}); dt = time.time() - t0
    if audit:
        audit({"kind": "llm_call", "role": role, "model": m["model"], "purpose": purpose, "seconds": round(dt, 2), "attempts": attempt + 1,  # seconds include retry waits
               "prompt_tokens": usage.get("prompt_tokens"), "completion_tokens": usage.get("completion_tokens"),
               "finish": d["choices"][0].get("finish_reason"),
               "prompt_sha256": hashlib.sha256(json.dumps(messages, default=str).encode()).hexdigest()[:16]})
    if json_schema is not None:
        try:
            return json.loads(text) if _guided(role) else parse_json_loose(text)
        except (json.JSONDecodeError, ValueError) as e:
            # Greedy decoding is deterministic: re-sending the same prompt gives the same broken output. So the retry
            # must change something: (1) output cut off -> more room; (2) otherwise ask the model to repair its own JSON.
            if _retries < 2:
                if finish == "length":
                    return await chat(role, messages, json_schema=json_schema, max_tokens=int(max_tokens * 1.8), temperature=temperature,
                                      purpose=purpose, audit=audit, _retries=_retries + 1)
                repair = messages + [{"role": "assistant", "content": text},
                                     {"role": "user", "content": "That was not valid JSON. Return the same content as ONE valid JSON object only, "
                                      "no prose and no code fences, matching the requested structure exactly."}]
                return await chat(role, repair, json_schema=json_schema, max_tokens=max_tokens, temperature=temperature,
                                  purpose=purpose + " (repair)", audit=audit, _retries=_retries + 1)
            raise LLMError(f"invalid JSON from {role} ({purpose}): {text[:200]}") from e
    return text


async def stream(role: str, messages: list, *, max_tokens: int = 1024, temperature: float = 0.0, audit=None) -> AsyncIterator[str]:
    m, body = _payload(role, messages, max_tokens, temperature, None, True)
    url = _norm(m["base_url"])
    yielded = False
    for attempt in range(len(_RETRY_DELAYS) + 1):
        try:
            async with _queue(url):
                async with client().stream("POST", url + "/chat/completions", json=body) as r:
                    if r.status_code != 200:
                        raise LLMError(f"{role} model error {r.status_code}: {(await r.aread())[:300]!r}")
                    async for line in r.aiter_lines():
                        if not line.startswith("data: ") or line.endswith("[DONE]"):
                            continue
                        d = json.loads(line[6:])
                        if d.get("choices") and d["choices"][0]["delta"].get("content"):
                            yielded = True
                            yield d["choices"][0]["delta"]["content"]
            return
        except _RETRYABLE as e:
            # retry only before any text went out; a half-streamed answer is never restarted
            if yielded or attempt >= len(_RETRY_DELAYS):
                raise _unreachable(role, m, e) from e
            await _retry_wait(role, attempt + 1, e, audit)


async def health() -> dict:
    out = {}
    for role, m in config.models().items():
        try:
            r = await client().get(m["base_url"].rstrip("/") + "/models", timeout=3)
            ids = [x["id"] for x in r.json().get("data", [])]
            out[role] = {"online": m["model"] in ids, "served": ids, **{k: m.get(k) for k in ("model", "label", "origin", "medical", "base_url")}}
        except Exception as e:
            out[role] = {"online": False, "error": str(e)[:120], **{k: m.get(k) for k in ("model", "label", "origin", "medical", "base_url")}}
    return out
