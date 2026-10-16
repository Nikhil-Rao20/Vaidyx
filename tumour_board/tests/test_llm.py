"""llm: one model queue per server URL (sizes from env), connection-level retries with audit, no retry on HTTP errors.

No network, no GPU: every request goes to an httpx.MockTransport."""
import asyncio, json

import httpx
import pytest

from tumour_board import config, llm

READER = "http://127.0.0.1:8101/v1"
REASONER = "http://127.0.0.1:8100/v1"


@pytest.fixture(autouse=True)
def fresh(monkeypatch):
    """Empty queue cache and no real client; retry delays patched to 0."""
    monkeypatch.setattr(llm, "_queues", {})
    monkeypatch.setattr(llm, "_client", None)
    monkeypatch.setattr(llm, "_RETRY_DELAYS", (0, 0, 0))
    for k in ("TB_CONCURRENCY_READER", "TB_CONCURRENCY_REASONER", "TB_LLM_CONCURRENCY"):
        monkeypatch.delenv(k, raising=False)
    yield


def _mock(monkeypatch, handler):
    """Route llm.client() to a MockTransport running `handler`; returns the list of requests seen."""
    seen = []

    def h(request):
        seen.append(request)
        return handler(request)
    monkeypatch.setattr(llm, "_client", httpx.AsyncClient(transport=httpx.MockTransport(h)))
    return seen


def _ok(text="hello"):
    return httpx.Response(200, json={"choices": [{"message": {"content": text}, "finish_reason": "stop"}],
                                     "usage": {"prompt_tokens": 3, "completion_tokens": 1}})


MSG = [{"role": "user", "content": "hi"}]


def test_queue_per_server_url_shared_by_roles_on_same_server():
    cfg = config.models()
    assert llm._norm(cfg["reader"]["base_url"]) != llm._norm(cfg["reasoner"]["base_url"])
    assert llm._queue(cfg["reader"]["base_url"]) is not llm._queue(cfg["reasoner"]["base_url"])
    # same server -> same queue, trailing slash ignored; the extractor defaults to the reasoner's server
    assert llm._queue(READER) is llm._queue(READER + "/")
    assert llm._queue(cfg["extractor"]["base_url"]) is llm._queue(cfg["reasoner"]["base_url"])


def test_default_sizes():
    assert llm._queue_size(READER) == 24
    assert llm._queue_size(REASONER) == 32
    assert llm._queue_size("http://127.0.0.1:8102/v1") == 48


def test_sizes_from_env(monkeypatch):
    monkeypatch.setenv("TB_CONCURRENCY_READER", "5")
    monkeypatch.setenv("TB_CONCURRENCY_REASONER", "7")
    monkeypatch.setenv("TB_LLM_CONCURRENCY", "3")
    assert llm._queue(READER)._value == 5
    assert llm._queue(REASONER + "/")._value == 7
    assert llm._queue("http://127.0.0.1:8102/v1")._value == 3


def test_third_server_from_models_json_gets_fallback_queue(data_root, monkeypatch):
    monkeypatch.setenv("TB_LLM_CONCURRENCY", "9")
    (data_root / "models.json").write_text(json.dumps({"extractor": {"base_url": "http://127.0.0.1:8102/v1", "model": "x"}}))
    q = llm._queue(config.models()["extractor"]["base_url"])
    assert q is not llm._queue(READER) and q is not llm._queue(REASONER)
    assert q._value == 9


def test_reader_queue_full_does_not_block_reasoner(monkeypatch):
    """Reader limited to 2 in flight; a reasoner call finishes while the reader queue is saturated."""
    monkeypatch.setenv("TB_CONCURRENCY_READER", "2")
    inflight = {"reader": 0, "max": 0}
    release = None

    async def handler(request):
        if request.url.port == 8101:
            inflight["reader"] += 1; inflight["max"] = max(inflight["max"], inflight["reader"])
            await release.wait()
            inflight["reader"] -= 1
        return _ok()
    _mock(monkeypatch, handler)

    async def go():
        nonlocal release
        release = asyncio.Event()
        readers = [asyncio.create_task(llm.chat("reader", MSG)) for _ in range(6)]
        await asyncio.sleep(0.05)
        assert inflight["reader"] == 2
        assert await asyncio.wait_for(llm.chat("reasoner", MSG), 2) == "hello"
        release.set()
        assert await asyncio.gather(*readers) == ["hello"] * 6
    asyncio.run(go())
    assert inflight["max"] == 2


def test_connect_error_retried_then_succeeds(monkeypatch):
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        if calls["n"] <= 2:
            raise httpx.ConnectError("connection refused")
        return _ok("fine")
    seen = _mock(monkeypatch, handler)
    events = []
    assert asyncio.run(llm.chat("reader", MSG, audit=events.append)) == "fine"
    assert len(seen) == 3
    retries = [e for e in events if e["kind"] == "llm_retry"]
    assert [(e["role"], e["attempt"]) for e in retries] == [("reader", 1), ("reader", 2)]
    assert retries[0]["error"] == "ConnectError: connection refused"
    assert [e["kind"] for e in events].count("llm_call") == 1


def test_connect_timeout_gives_up_after_four_attempts(monkeypatch):
    def handler(request):
        raise httpx.ConnectTimeout("timed out")
    seen = _mock(monkeypatch, handler)
    events = []
    with pytest.raises(llm.LLMError) as ei:
        asyncio.run(llm.chat("reader", MSG, audit=events.append))
    msg = str(ei.value)
    assert "ConnectTimeout" in msg and READER in msg and "unreachable" in msg
    assert msg == f"reader model server unreachable at {READER} (ConnectTimeout: timed out)"
    assert len(seen) == 4
    assert [e["attempt"] for e in events if e["kind"] == "llm_retry"] == [1, 2, 3]


def test_retry_delays_used_in_order(monkeypatch):
    monkeypatch.setattr(llm, "_RETRY_DELAYS", (0.01, 0.02, 0.04))
    slept = []
    real_sleep = asyncio.sleep

    async def fake_sleep(s):
        slept.append(s); await real_sleep(0)
    monkeypatch.setattr(llm.asyncio, "sleep", fake_sleep)

    def handler(request):
        raise httpx.RemoteProtocolError("server disconnected")
    _mock(monkeypatch, handler)
    with pytest.raises(llm.LLMError, match="RemoteProtocolError"):
        asyncio.run(llm.chat("reasoner", MSG))
    assert slept == [0.01, 0.02, 0.04]


def test_read_timeout_not_retried(monkeypatch):
    def handler(request):
        raise httpx.ReadTimeout("read timed out")
    seen = _mock(monkeypatch, handler)
    with pytest.raises(llm.LLMError, match=r"ReadTimeout: read timed out"):
        asyncio.run(llm.chat("reasoner", MSG))
    assert len(seen) == 1


def test_http_500_not_retried(monkeypatch):
    seen = _mock(monkeypatch, lambda request: httpx.Response(500, text="boom"))
    events = []
    with pytest.raises(llm.LLMError, match="model error 500"):
        asyncio.run(llm.chat("reader", MSG, audit=events.append))
    assert len(seen) == 1 and events == []


def test_json_repair_retry_unchanged(monkeypatch):
    replies = iter(["not json at all", '{"a": 1,}'])
    seen = _mock(monkeypatch, lambda request: _ok(next(replies)))
    events = []
    out = asyncio.run(llm.chat("reasoner", MSG, json_schema={"type": "object", "properties": {"a": {"type": "integer"}}},
                               purpose="t", audit=events.append))
    assert out == {"a": 1} and len(seen) == 2
    assert [e["purpose"] for e in events] == ["t", "t (repair)"]


def _sse(*chunks):
    lines = [f"data: {json.dumps({'choices': [{'delta': {'content': c}}]})}" for c in chunks] + ["data: [DONE]"]
    return httpx.Response(200, text="\n\n".join(lines) + "\n\n", headers={"content-type": "text/event-stream"})


def test_stream_yields_deltas_through_queue(monkeypatch):
    seen = _mock(monkeypatch, lambda request: _sse("Hel", "lo"))

    async def go():
        return [d async for d in llm.stream("reasoner", MSG)]
    assert asyncio.run(go()) == ["Hel", "lo"]
    assert len(seen) == 1 and json.loads(seen[0].content)["stream"] is True
    assert list(llm._queues) == [REASONER]


def test_stream_retries_connect_error_before_first_delta(monkeypatch):
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        if calls["n"] == 1:
            raise httpx.ConnectError("refused")
        return _sse("ok")
    _mock(monkeypatch, handler)
    events = []

    async def go():
        return [d async for d in llm.stream("reader", MSG, audit=events.append)]
    assert asyncio.run(go()) == ["ok"]
    assert [(e["kind"], e["attempt"]) for e in events] == [("llm_retry", 1)]


def test_connect_timeout_raised_to_30s():
    c = llm.client()
    assert c.timeout.connect == 30 and c.timeout.read == 600
