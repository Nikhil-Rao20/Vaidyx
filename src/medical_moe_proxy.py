"""
Medical MoE Router — Vaidyx Clinical AI (Speed-Optimised v2)

Implements MoE principles using dedicated clinical specialist models.
Architecture:
  1. Domain Classifier  — keyword-based medical domain detection
  2. Expert Selector    — picks 2 best specialists for the query
  3. Parallel Inference — queries selected experts simultaneously (capped at 250 tok each)
  4. Synthesis          — med42:8b (31 tok/s) synthesises expert responses (350 tok)
  5. Streaming          — synthesis tokens streamed to client immediately (TTFB ~2–3s)

Speed budget per query (2 experts + synthesis):
  - Expert parallel: max(expert times) ≈ max(250/31, 250/8.4) ≈ ~30s (if 27B expert)
    → By routing most queries to 7-8B specialists: max(250/31, 250/40) ≈ ~8s
  - Synthesis (med42, 350 tok): 350/31 ≈ 11s (streaming — first token at ~1s)
  - Total wall-clock for user: ~10–25s depending on domain
"""

import asyncio
import json
import logging
import re
import time
import uuid
from typing import List, Tuple, Optional

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse, JSONResponse

logging.basicConfig(level=logging.INFO, format='%(asctime)s [MoE] %(message)s')
logger = logging.getLogger(__name__)

OLLAMA_BASE     = "http://127.0.0.1:11434"
PROXY_PORT      = 11435
MOE_MODEL_ID    = "medical-moe"

# Synthesizer — med42:8b is fastest among high-quality models (31 tok/s)
# NEVER use medgemma:27b as synthesizer (8.4 tok/s = slow)
SYNTHESIZER     = "med42:8b"

# Expert token budget — enough for a clear clinical answer, short enough to be fast
EXPERT_TOKENS   = 220    # ~7s on med42, ~26s on medgemma:27b
SYNTH_TOKENS    = 380    # synthesis output cap

# ─── Domain → Expert Routing ──────────────────────────────────────────────────
# Rule: prefer 7-8B specialists over 27B wherever quality is comparable.
# medgemma:27b is reserved for cases where its larger knowledge base is critical.

DOMAIN_RULES = [
    # (domain, regex, [expert1, expert2])  — ordered by preference
    ("emergency",
     r"\b(emergency|acute|immediate|stat|urgent|resuscit|collapse|arrest|shock|status\s+epilep|seiz|anaphyl|trauma|overdose|poison|snake\s*bite|OP\s*poison|atropine|antidote)\b",
     ["med42:8b", "openbiollm:8b"]),          # both fast (31 tok/s)

    ("pharmacology",
     r"\b(drug|dose|dosage|interact|contraind|side\s*effect|adverse|tablet|injection|IV|IM|PO|mg|mcg|mg/kg|prescri|formulary|NLEM|brand|generic|antibiotic|antihypertensive|analgesic|antifungal|antiviral|pharmaco)\b",
     ["openbiollm:8b", "med42:8b"]),          # openbiollm strongest on drug queries

    ("infectious",
     r"\b(fever|infect|malaria|dengue|typhoid|scrub\s*typhus|leptospirosis|tuberculosis|TB|HIV|sepsis|meningitis|encephalitis|pneumonia|UTI|COVID|enteric|tropical|NVBDCP|NTEP)\b",
     ["medllama2:7b", "med42:8b"]),           # medllama2 strong on infectious, fast (39 tok/s)

    ("renal_hepatic",
     r"\b(kidney|renal|CrCl|GFR|eGFR|dialysis|hepatic|liver|Child-Pugh|cirrhosis|creatinine|nephro|dosing\s+adjust)\b",
     ["jslmed:8b", "openbiollm:8b"]),         # both 30+ tok/s, strong on renal dosing

    ("cardiology",
     r"\b(heart|cardiac|MI|STEMI|NSTEMI|ACS|angina|ECG|arrhythmia|atrial|ventricular|hypertension|BP|blood\s*pressure|cholesterol|statin|anticoagul|thrombol|fibrinolysis)\b",
     ["med42:8b", "jslmed:8b"]),

    ("neurology",
     r"\b(seizure|epilepsy|stroke|TIA|parkinson|alzheimer|dementia|headache|migraine|neuropathy|brain|spinal|coma|GCS|lorazepam|phenytoin|levetiracetam|valproate)\b",
     ["med42:8b", "medgemma1.5:4b"]),         # medgemma1.5 strong on neurology + fast (53 tok/s)

    ("endocrine",
     r"\b(diabetes|DM|HbA1c|insulin|glucose|DKA|hypoglycaemia|thyroid|TSH|adrenal|cortisol|RSSDI|metformin|glipizide|SGLT2|GLP-1|obesity)\b",
     ["jslmed:8b", "med42:8b"]),

    ("paediatric",
     r"\b(child|infant|neonate|paediatric|pediatric|IAP|mg/kg|weight.based|febrile|newborn|neonatal|immunisation|vaccine)\b",
     ["medgemma:4b", "med42:8b"]),            # medgemma:4b fastest (53 tok/s)

    ("imaging",
     r"\b(X-ray|CT|MRI|ultrasound|USG|radiol|imaging|CECT|PET|scan|chest\s*x-ray|CXR|opacity|consolidat|effusion|BIRADS|fracture|shadow)\b",
     ["medgemma:4b", "medgemma1.5:4b"]),      # vision-capable, both fast

    ("obstetric",
     r"\b(pregnancy|obstetric|prenatal|antenatal|eclampsia|pre-eclampsia|labour|delivery|postpartum|foetal|fetal|trimester|FOGSI|ACOG|gestational)\b",
     ["med42:8b", "jslmed:8b"]),

    ("complex_diagnosis",
     r"\b(differential|DDx|rare|unusual|atypical|syndrome|present\w+\s+with|multi.*system|complex|ambiguous)\b",
     ["medgemma:27b", "med42:8b"]),           # only case where 27B is a primary expert
]

DEFAULT_EXPERTS = ["med42:8b", "openbiollm:8b"]


# ─── Domain Classification ────────────────────────────────────────────────────

def classify_domain(query: str) -> Tuple[str, List[str]]:
    """Return (domain_name, [expert_model_ids]) for the query."""
    scores: dict[str, Tuple[int, List[str]]] = {}
    for domain, pattern, experts in DOMAIN_RULES:
        matches = len(re.findall(pattern, query, re.IGNORECASE))
        if matches:
            scores[domain] = (matches, experts)
    if not scores:
        return "general", DEFAULT_EXPERTS
    top = max(scores, key=lambda d: scores[d][0])
    return top, scores[top][1]


# ─── Expert Inference ─────────────────────────────────────────────────────────

async def query_expert(client: httpx.AsyncClient, model: str,
                       messages: list, temperature: float) -> Optional[str]:
    """Query one expert. Capped at EXPERT_TOKENS for speed."""
    try:
        resp = await client.post(
            f"{OLLAMA_BASE}/api/chat",
            json={
                "model": model,
                "messages": messages,
                "stream": False,
                "options": {"temperature": temperature, "num_predict": EXPERT_TOKENS},
            },
            timeout=httpx.Timeout(90.0),
        )
        if resp.status_code == 200:
            return resp.json().get("message", {}).get("content", "").strip()
        logger.warning(f"{model} returned HTTP {resp.status_code}")
    except Exception as e:
        logger.warning(f"{model} failed: {e}")
    return None


async def stream_synthesis(client: httpx.AsyncClient, domain: str,
                            expert_responses: List[Tuple[str, str]],
                            original_query: str, temperature: float):
    """Stream synthesis tokens directly from med42:8b to the client."""
    if not expert_responses:
        yield "[MoE: no expert responses available]"
        return

    if len(expert_responses) == 1:
        model, resp = expert_responses[0]
        yield f"[MoE: {domain} — {model.split(':')[0]}]\n\n{resp}"
        return

    expert_section = "\n\n".join([
        f"### {m.split(':')[0].upper()} Expert:\n{r}"
        for m, r in expert_responses if r
    ])
    expert_list = " + ".join(m.split(":")[0] for m, _ in expert_responses)

    synth_messages = [
        {
            "role": "system",
            "content": (
                "You are a senior clinical synthesizer. Combine these expert medical opinions "
                "into ONE definitive clinical answer.\n"
                "Rules: Start immediately with the drug/treatment. Include exact dose, route, "
                "frequency. Note any important agreement or disagreement between experts. "
                "Be concise but complete. No disclaimers. No preamble."
            ),
        },
        {
            "role": "user",
            "content": (
                f"QUESTION: {original_query}\n\n"
                f"DOMAIN: {domain.upper()}\n\n"
                f"EXPERT OPINIONS:\n{expert_section}\n\n"
                "Synthesize into one definitive clinical answer:"
            ),
        },
    ]

    # Yield the MoE header first (immediate feedback)
    yield f"[MoE: {domain} → {expert_list}]\n\n"

    # Stream synthesis from med42:8b
    try:
        async with client.stream(
            "POST",
            f"{OLLAMA_BASE}/api/chat",
            json={
                "model": SYNTHESIZER,
                "messages": synth_messages,
                "stream": True,
                "options": {"temperature": 0.2, "num_predict": SYNTH_TOKENS},
            },
            timeout=httpx.Timeout(120.0),
        ) as resp:
            async for line in resp.aiter_lines():
                if not line.strip():
                    continue
                try:
                    data = json.loads(line)
                    token = data.get("message", {}).get("content", "")
                    if token:
                        yield token
                    if data.get("done"):
                        break
                except json.JSONDecodeError:
                    continue
    except Exception as e:
        logger.error(f"Synthesis stream failed: {e}")
        # Fallback: return best expert response
        yield expert_responses[0][1]


# ─── FastAPI App ──────────────────────────────────────────────────────────────

app = FastAPI(title="Medical MoE Router v2 (Speed-Optimised)")


def _get_user_text(messages: list) -> str:
    for msg in reversed(messages or []):
        if isinstance(msg, dict) and msg.get("role") == "user":
            content = msg.get("content", "")
            if isinstance(content, str):
                return content
            if isinstance(content, list):
                return " ".join(
                    p.get("text", "") for p in content
                    if isinstance(p, dict) and p.get("type") == "text"
                )
    return ""


@app.get("/api/tags")
async def list_models():
    return {"models": [{"name": MOE_MODEL_ID, "model": MOE_MODEL_ID,
                         "modified_at": "2026-01-01T00:00:00Z", "size": 0,
                         "digest": "medical-moe-v2",
                         "details": {"family": "moe-router", "parameter_size": "2x8B",
                                     "quantization_level": "clinical-ensemble"}}]}


@app.get("/v1/models")
async def list_models_v1():
    return {"object": "list", "data": [{"id": MOE_MODEL_ID, "object": "model",
                                         "created": 1700000000, "owned_by": "vaidyx-moe"}]}


def _chunk(content: str, done: bool = False) -> str:
    """Serialise one Ollama ndjson chunk."""
    obj = {"model": MOE_MODEL_ID,
           "message": {"role": "assistant", "content": content},
           "done": done}
    if done:
        obj["done_reason"] = "stop"
    return json.dumps(obj) + "\n"


@app.post("/api/chat")
async def chat_handler(request: Request):
    body = await request.json()
    messages    = body.get("messages", [])
    temperature = float(body.get("options", {}).get("temperature", 0.3))
    do_stream   = body.get("stream", False)

    user_text = _get_user_text(messages)
    domain, selected_experts = classify_domain(user_text)
    logger.info(f"domain={domain} | experts={selected_experts}")

    expert_list = " + ".join(m.split(":")[0] for m in selected_experts)

    async def _generate():
        async with httpx.AsyncClient() as client:
            # 1. Immediate header — user sees domain in <1s
            header = f"[MoE: {domain} → {expert_list}]\n\n"
            yield _chunk(header)

            # 2. Query experts in parallel (user sees header while waiting)
            tasks = [query_expert(client, m, messages, temperature) for m in selected_experts]
            expert_results = await asyncio.gather(*tasks)
            expert_responses = [(m, r) for m, r in zip(selected_experts, expert_results) if r]

            if not expert_responses:
                yield _chunk("All expert models unavailable. Please retry.", done=False)
                yield _chunk("", done=True)
                return

            if len(expert_responses) == 1:
                # Single expert — stream its response directly
                yield _chunk(expert_responses[0][1])
                yield _chunk("", done=True)
                return

            # 3. Build synthesis prompt — include any system message from the caller
            sys_msgs = [m for m in messages if isinstance(m, dict) and m.get("role") == "system"]
            expert_section = "\n\n".join([
                f"### {m.split(':')[0].upper()} Expert:\n{r}"
                for m, r in expert_responses if r
            ])
            synth_system = (
                "You are a senior clinical synthesizer. Combine these expert medical opinions "
                "into ONE definitive clinical answer.\n"
                "Rules: Start immediately with the drug/treatment. Include exact dose, route, "
                "frequency (use Indian brand names alongside generics). Note any agreement or "
                "disagreement between experts. Reference Indian guidelines (ICMR, API, CSI, RSSDI). "
                "No disclaimers. No preamble."
            )
            if sys_msgs:
                # Merge caller's system context (Vaidyx global prompt) with synthesis instructions
                caller_sys = sys_msgs[0].get("content", "")
                synth_system = caller_sys + "\n\n" + synth_system

            synth_messages = [
                {"role": "system", "content": synth_system},
                {"role": "user", "content": (
                    f"QUESTION: {user_text}\n\n"
                    f"DOMAIN: {domain.upper()}\n\n"
                    f"EXPERT OPINIONS:\n{expert_section}\n\n"
                    "Synthesize into one definitive clinical answer:"
                )},
            ]

            # 4. Stream synthesis tokens immediately
            try:
                async with client.stream(
                    "POST", f"{OLLAMA_BASE}/api/chat",
                    json={"model": SYNTHESIZER, "messages": synth_messages,
                          "stream": True,
                          "options": {"temperature": 0.2, "num_predict": SYNTH_TOKENS}},
                    timeout=httpx.Timeout(120.0),
                ) as resp:
                    async for line in resp.aiter_lines():
                        if not line.strip():
                            continue
                        try:
                            data = json.loads(line)
                            token = data.get("message", {}).get("content", "")
                            if token:
                                yield _chunk(token)
                            if data.get("done"):
                                break
                        except json.JSONDecodeError:
                            continue
            except Exception as e:
                logger.error(f"Synthesis stream error: {e}")
                yield _chunk(expert_responses[0][1])

            yield _chunk("", done=True)

    if do_stream:
        return StreamingResponse(_generate(), media_type="application/x-ndjson")

    # Non-streaming: collect all
    full = ""
    async for chunk_str in _generate():
        try:
            data = json.loads(chunk_str)
            full += data.get("message", {}).get("content", "")
        except Exception:
            pass

    return JSONResponse({
        "model": MOE_MODEL_ID,
        "created_at": time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        "message": {"role": "assistant", "content": full},
        "done": True, "done_reason": "stop",
    })


@app.post("/v1/chat/completions")
async def openai_compat(request: Request):
    body = await request.json()
    messages   = body.get("messages", [])
    temperature = body.get("temperature", 0.3)
    user_text  = _get_user_text(messages)
    domain, selected_experts = classify_domain(user_text)

    async with httpx.AsyncClient() as client:
        tasks = [query_expert(client, m, messages, temperature) for m in selected_experts]
        expert_results = await asyncio.gather(*tasks)
        expert_responses = [(m, r) for m, r in zip(selected_experts, expert_results) if r]

        full = ""
        async for token in stream_synthesis(client, domain, expert_responses,
                                             user_text, temperature):
            full += token

    return JSONResponse({
        "id": f"chatcmpl-{uuid.uuid4().hex[:8]}",
        "object": "chat.completion", "created": int(time.time()),
        "model": MOE_MODEL_ID,
        "choices": [{"index": 0,
                     "message": {"role": "assistant", "content": full},
                     "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 0, "completion_tokens": len(full.split()), "total_tokens": 0},
    })


if __name__ == "__main__":
    import uvicorn
    logger.info(f"Medical MoE Router v2 starting on port {PROXY_PORT}")
    logger.info(f"Synthesizer: {SYNTHESIZER} ({SYNTH_TOKENS} tok cap)")
    logger.info(f"Expert token cap: {EXPERT_TOKENS} tok")
    uvicorn.run(app, host="0.0.0.0", port=PROXY_PORT, log_level="warning")
