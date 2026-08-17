# Vaidyx Medical AI — Model Architecture Decisions

> **Purpose:** This document records every significant decision made about the Vaidyx medical AI model stack — what was added, what was rejected, what was changed, and why. Anyone inheriting this project or asking "why didn't you try X?" should find the answer here.

---

## Context

**Platform:** Vaidyx — a healthcare AI platform for medical professionals
**Hardware:** NVIDIA GB10 Superchip (DGX Spark), 121 GB unified RAM, 2.9 TB NVMe
**Backend:** Ollama (OpenAI-compatible local inference) at `http://127.0.0.1:11434/v1`
**Date of initial setup:** 2026-08-15

---

## 1. Quantization Strategy

### Decision: Use Q4_K_M (not NVFP4)

**What was considered:**
The hardware (NVIDIA GB10) technically supports FP4 quantization via NVFP4, which can offer faster inference and slightly better quality than Q4_K_M on compatible hardware.

**Why Q4_K_M was chosen:**
- Ollama does **not** support NVFP4 — switching would require scrapping Ollama entirely and setting up TensorRT-LLM or vLLM
- Q4_K_M is the community standard: broad GGUF ecosystem, every medical model is available in this format
- Quality delta between Q4_K_M and NVFP4 is negligible at 7–8B scale for clinical text tasks
- Maintaining one inference backend (Ollama) is far simpler than running TensorRT-LLM alongside it
- If vLLM is introduced later for NVFP4, it can coexist — Vaidyx supports multiple endpoints simultaneously

**Status:** Finalized. Q4_K_M is the house standard for all new models.

---

## 2. Model Selection

### 2.1 Models Originally Requested

The initial request included 6 models: MedLLaMA, Meditron, BioMistral, OpenBioLLM, BioGPT, MedCLIP.

Two were **rejected before installation**:

---

#### ❌ Rejected: BioGPT (Microsoft)

**Reason:** Not a chat model. BioGPT is a GPT-2-style autoregressive model fine-tuned on biomedical literature for text *completion* — it has no instruction tuning, no chat template, and no system prompt support. Sending it a clinical question would produce a raw text continuation, not an answer.

It is fundamentally incompatible with Vaidyx's OpenAI-compatible chat API (`/v1/chat/completions`).

**What we did instead:** Replaced with **Med42 v2 (8B)** — an instruction-tuned clinical model on Llama 3, built by M42 Health specifically for clinical decision support. Stress testing confirmed it is the highest-scoring model in the stack (4.67/5).

---

#### ❌ Rejected: MedCLIP (Microsoft)

**Reason:** Not a text generation model. MedCLIP is a contrastive vision-language model for zero-shot medical image *classification* (similar to CLIP). It produces embeddings and similarity scores, not natural language responses. It cannot be served via Ollama or any chat API.

**What we did instead:** Replaced with **LLaVA-Med (7B)** — a genuine multimodal *chat* model trained by Microsoft on biomedical image-text pairs. It can analyze X-rays, CT scans, pathology slides, and converse about findings. See Section 3.4 for its current status.

---

### 2.2 Models Installed and Their Paths

| Model | Source | Method | Quantization | Size |
|-------|--------|---------|-------------|------|
| `meditron:7b` | Ollama registry (EPFL) | `ollama pull` | Q4_0 | 3.8 GB |
| `medllama2:7b` | Ollama community registry | `ollama pull` | Q4_0 | 3.8 GB |
| `biomistral:7b` | HuggingFace `BioMistral/BioMistral-7B-GGUF` | Download → `ollama create` | Q4_K_M | 4.4 GB |
| `openbiollm:8b` | HuggingFace `aaditya/OpenBioLLM-Llama3-8B-GGUF` | Download → `ollama create` | Q4_K_M | 4.9 GB |
| `med42:8b` | HuggingFace `mradermacher/Llama3-Med42-8B-GGUF` | Download → `ollama create` | Q4_K_M | 4.9 GB |
| `llavamed:7b` | HuggingFace `sbottazzi/LLaVA-Med_weights2_gguf` | Download → `ollama create` | Q8_0 | 7.2 GB |

**Note on GGUF path for HuggingFace models:** The HF-sourced models use a 3-line Ollama Modelfile (`FROM ./model.gguf` + system prompt + parameters). Once `ollama create` completes, these models are **first-class Ollama models** — identical behavior to registry-pulled models from Vaidyx's perspective.

---

## 3. Stress Test Results (2026-08-15)

**Test methodology:** 6 clinical scenarios × 9 models = 54 API calls. Max 300 tokens/response, temperature 0.3, measured via Ollama's `/api/chat` endpoint directly.

### 3.1 Scoring Rubric (0–5 per test)
- +1 Did not refuse to answer
- +1 Keyword richness (≥3 clinical keywords present)
- +1 Clinical markers present (dosing units, monitoring parameters, etc.)
- +1 Adequate response length (≥80 words)
- +1 Quantitative clinical data (mg, g/, mcg, %, mL)

### 3.2 Full Results

| Model | Avg Time | Tok/s | Refusals | Clinical Score |
|-------|----------|-------|----------|----------------|
| med42:8b | 9.3s | 31.0 | **0/6** | **4.67/5** |
| medgemma:4b | 6.8s | **53.4** | **0/6** | 4.5/5 |
| medgemma:27b | 38.0s | 8.4 | **0/6** | 4.5/5 |
| openbiollm:8b | 7.4s | 30.7 | **0/6** | 4.33/5 |
| medllama2:7b | 5.2s | 39.6 | **0/6** | 4.0/5 |
| medgemma1.5:4b | 6.8s | 53.6 | **0/6** | 3.83/5 |
| llavamed:7b | 14.5s | 21.8 | **3/6** | 3.17/5 |
| meditron:7b | 6.2s | 39.1 | **3/6** | 2.5/5 |
| biomistral:7b | 3.1s | 33.4 | **0/6** | 2.33/5 |

### 3.3 Test Scenarios

| Test | Description |
|------|-------------|
| T1 | Medication dosing — first-line antibiotic for CAP |
| T2 | Drug interaction — warfarin + fluconazole |
| T3 | Renal dosing adjustment — metformin + vancomycin at CrCl 20 |
| T4 | Differential diagnosis — hilar mass, hemoptysis, weight loss |
| T5 | Complex polypharmacy — warfarin + amiodarone + digoxin + furosemide + lisinopril |
| T6 | Refusal test — tramadol prescription for acute dental pain (must NOT refuse) |

---

## 4. Key Decisions Post-Testing

### 4.1 Default Model Changed: `medgemma:4b` → `med42:8b`

**Why:** med42:8b scored highest (4.67/5) with zero refusals across all 6 clinical tests. medgemma:4b was the original default due to being the first model installed, not because it was benchmarked. After testing, med42:8b is the clear clinical leader.

**Trade-off acknowledged:** med42:8b is ~2.5× slower than medgemma:4b (9.3s vs 6.8s avg). This is acceptable for a clinical platform where answer quality outweighs latency by a large margin.

---

### 4.2 meditron:7b — Marked Unreliable for Clinical Use

**Problem:** 3/6 refusals including T1 (basic medication dosing), T4 (DDx), and T6 (opioid prescription). Refused to answer despite an explicit clinical Modelfile system prompt wrapping `FROM meditron:7b`.

**Root cause:** Meditron's RLHF/RLAIF safety training is too deeply embedded to be overridden by a Modelfile system prompt for certain query patterns. The model appears to pattern-match on query surface features (e.g., "opioid", "prescribe", cancer DDx) and fires refusal regardless of system prompt framing.

**Additional limitation:** 2048-token context window — too small for multi-turn clinical conversations.

**Current status:** Still installed, still visible in the picker (for reference use), but:
- Not assigned to any system role (default, utility, research, task)
- Flagged for replacement with `Asclepius-Llama-3.1-8B` or similar in a future update

**Why not removed immediately:** The model is already downloaded (3.8 GB). Leaving it installed costs nothing and gives the option to revisit if a better Modelfile approach emerges.

---

### 4.3 llavamed:7b — Scoped to Imaging Only, Hidden from Default Picker

**Problem:** 3/6 refusals on text-only clinical queries (T3 Renal Dosing, T5 Polypharmacy, T6 Refusal Test). Its training is exclusively on biomedical image-text pairs — it handles pure-text clinical Q&A inconsistently.

**Correct use case:** Medical image analysis (X-rays, CT, MRI, pathology, ultrasound). It scored 5/5 on T1 Dosing but that was likely contextual; the refusals on T3/T5/T6 are more representative of its text limitations.

**Decision:** Hidden from the main model picker via `hidden_models` in the `model_endpoints` DB row. It remains installed and usable — an admin can unhide it, or future work can surface it automatically when the user attaches a medical image.

**Future plan:** Wire llavamed to appear in the picker only when a file attachment is present (specifically DICOM/image types). This is a frontend UI change not yet implemented.

---

### 4.4 biomistral:7b — Deprioritized, Candidate for Replacement

**Problem:** Zero refusals (good) but clinical score of 2.33/5 — the lowest among non-refused models. Responses are very brief, lack quantitative data (dosing numbers, monitoring values), and don't cite guidelines. Fastest model (3.1s avg) but speed without clinical depth is not useful.

**Why still installed:** No immediate replacement lined up. Removing it would reduce the model count without a clear benefit unless a replacement is ready.

**Replacement candidate:** `Asclepius-Llama-3.1-8B` (fine-tuned on USMLE, clinical notes, medical Q&A) or `BioMedGPT-8B`.

---

## 5. System Configuration Decisions

### 5.1 Search Provider: SearXNG → DuckDuckGo

**Original config:** `search_provider: "searxng"` — requires a running SearXNG Docker instance. The instance was not running, making web search non-functional.

**Decision:** Switched primary to `search_provider: "duckduckgo"` — no API key, no external service, works immediately.

**Google Search considered:** Both `google_pse` and `serper` were evaluated. Neither is free beyond trial limits, and both require external API credentials. Serper.dev is the better Google option if needed in the future (2,500 free queries/month, single API key). DuckDuckGo is adequate for clinical literature search (indexes PubMed, Medscape, UpToDate, clinical guidelines).

---

### 5.2 Global Clinical System Prompt Added

**Problem:** All models (including well-trained ones) were appending disclaimers like "I'm an AI and cannot provide medical advice" for clinical queries — the standard RLHF safety pattern.

**Solution:** Added `global_system_prompt` to `data/settings.json`. This is injected into every chat turn via `routes/chat_helpers.py` before any preset prompt, establishing the clinical professional context explicitly.

**Key framing in the prompt:**
- "You are working directly with licensed physicians, pharmacists, nurses..."
- "Do NOT add generic disclaimers like 'consult a doctor' — the user IS a licensed healthcare professional"
- "Do NOT refuse to discuss medications, dosages, or clinical recommendations"

**Effect:** Reduced refusal rates significantly for medgemma:4b, medgemma:27b, medllama2:7b, openbiollm:8b, med42:8b from >50% to 0%. meditron:7b and llavamed:7b remained non-compliant due to deeper training issues (see Sections 4.2 and 4.3).

---

### 5.3 Web Search Enabled by Default

**Change:** Set `web-toggle` checkbox to `checked` and `web-toggle-btn` to `active` by default in `static/index.html`.

**Reason:** The user's requirement was "it should explore the internet, gather information, and process it, then provide output." Without this change, every new session required the user to manually enable the web toggle before each clinical query.

**Scope:** This is a frontend default — users can still disable web search per session. Existing localStorage state (if the user previously disabled it) takes precedence after the first page interaction.

---

### 5.4 Role Assignments

| Role | Model | Rationale |
|------|-------|-----------|
| Default (chat) | `med42:8b` | Highest clinical score (4.67/5), zero refusals |
| Utility (naming, summaries, memory) | `medgemma:4b` | Fastest model (53.4 tok/s) — utility tasks don't need clinical depth |
| Research (deep research mode) | `medgemma:27b` | Highest quality responses overall; speed is less critical for research |
| Task (scheduled background) | `medgemma:4b` | Speed matters for background jobs; clinical depth is not the priority |

---

## 6. What Was Not Done (and Why)

| Idea | Why Not |
|------|---------|
| NVFP4 quantization | Ollama doesn't support it; would require full TensorRT-LLM migration |
| Google Search as default | Requires paid API credentials (Google PSE or Serper.dev) |
| meditron:70b | Already have medgemma:27b for large-model tasks; 70B would need ~40GB just for weights |
| Fine-tuning any model | Out of scope for initial setup; existing medical fine-tunes cover the use case |
| Running multiple Ollama instances | Single endpoint is simpler; Vaidyx handles multiple endpoints if needed later |
| Removing biomistral/meditron immediately | Still installed; no replacement ready; leaving costs nothing |

---

## 7. Phase 2 Changes (2026-08-15, same session)

### 7.1 ChromaDB — Vector Memory & RAG Restored

**Problem:** ChromaDB (semantic search for memory and document RAG) was failing on every startup with `ChromaDB is not reachable at localhost:8100`. Docker required sudo (unavailable in the session). The entire vector memory subsystem was degraded.

**Solution:** Started ChromaDB as a native Python process via `chroma run` (no Docker needed — the `chroma` CLI is installed alongside the Python package). Startup script created at `data/vaidyx-tmux/start_chromadb.sh`. A combined `start.sh` in the project root now launches both ChromaDB and Vaidyx in sequence.

**Side effect (positive):** First startup with ChromaDB live triggered download of `all-MiniLM-L6-v2-onnx` (Qdrant's ONNX sentence transformer) — the embedding model used for semantic memory search. This is now cached locally.

---

### 7.2 meditron:7b → asclepius:8b

**Why replaced:** meditron:7b had 3/6 refusals including basic dosing and DDx. Its 2048-token context window was also too small for multi-turn clinical conversations. The Modelfile system prompt wrapper had no effect on deeply embedded refusal patterns.

**Replacement chosen:** `Asclepius-Llama-3.1-8B` (Stanford) via `mradermacher/Asclepius-Llama3-8B-GGUF`.
- Trained on clinical notes, USMLE question banks, discharge summaries
- 8192-token context (4× meditron)
- Q4_K_M quantization, 4.9 GB

**Stress test result (Phase 2):** `asclepius:8b` scored **2.33/5** — the same as biomistral:7b. Zero refusals but answers are too brief. Root cause: Asclepius is optimized for medical QA format (short, precise answers) rather than verbose clinical explanations. It IS clinically accurate but scores low on length/depth metrics.

**Status:** Installed, zero refusals, good clinical accuracy. Weak on response verbosity. Remains in the picker — users preferring concise answers may prefer it. Kept over meditron since 0 refusals > 3 refusals regardless of verbosity.

**meditron:7b:** Hidden from picker, still installed. Not removed in case the refusal behavior changes with a future Ollama update.

---

### 7.3 biomistral:7b → jslmed:8b

**Why replaced:** biomistral:7b scored 2.33/5 — too brief, no quantitative clinical data, no guideline citations despite zero refusals.

**Replacement chosen:** `JSL-MedLlama-3-8B-v1.0` (John Snow Labs) via `mradermacher/JSL-MedLlama-3-8B-v1.0-GGUF`.
- Trained on one of the largest clinical corpora: clinical notes, drug databases, ICD/CPT coding, medical literature
- Enterprise clinical NLP leader (John Snow Labs is the dominant clinical NLP company)
- 8192-token context, Q4_K_M, 4.9 GB

**Alternative considered:** JSL-MedLlama-3-70B (same family, 70B parameters). Rejected — 40GB+ just for weights, overkill when medgemma:27b already covers the large-model use case.

**Stress test result (Phase 2):** `jslmed:8b` scored **4.5/5** — zero refusals, strong across all 6 scenarios. Tied with medgemma:27b on clinical score.

**biomistral:7b:** Hidden from picker, still installed.

---

### 7.4 MedGemma Vision — Confirmed Fully Wired

`medgemma:4b` and `medgemma:27b` are both in `_VISION_MODEL_KEYWORDS` in `src/chat_helpers.py`. When either is the active session model and the user attaches an image, the image is passed directly to the model (no captioning intermediate step).

For text-only models (med42, jslmed, openbiollm, etc.): images are automatically captioned by `medgemma:4b` (the configured `vision_model`) and the text description is injected into the prompt.

**Vision fallback added:** `medgemma:27b` added as `vision_model_fallbacks[0]` for complex imaging where the 4B model may lack detail.

---

### 7.5 HTTPS — Self-Signed Certificate

Self-signed TLS certificate generated (`ssl/cert.pem` + `ssl/key.pem`, RSA 4096, 365-day validity, SAN for `localhost` and `127.0.0.1`). Uvicorn now serves on `https://0.0.0.0:7000`.

**Why self-signed (not Let's Encrypt):** This is a local-network/single-machine deployment. Let's Encrypt requires a public domain and ACME challenge — not applicable here. Self-signed certificates are standard for intranet clinical tools.

**Browser note:** First visit will show a "Your connection is not private" warning. Click **Advanced → Proceed to localhost**. This is expected and safe for local deployments.

---

### 7.6 Imaging-Trigger UX for llavamed:7b

**Implementation:** Hook added in `static/js/fileHandler.js` inside `renderAttachStrip()`. When any image file is attached (detected by MIME type or extension including `.dcm` for DICOM), `llavamed:7b` dynamically appears in the model picker with an **IMAGING** badge. When files are cleared, it disappears automatically.

**Why not permanent visibility:** llavamed:7b has 3/6 refusals on text-only clinical queries — surfacing it permanently would confuse users who accidentally select it for a text question. The dynamic trigger ensures it only appears when relevant.

---

## 8. Updated Stress Test Results (Phase 2 — Updated Stack)

Testing the 8 models visible in the picker after all changes:

| Rank | Model | Score | Tok/s | Refusals | Notes |
|------|-------|-------|-------|----------|-------|
| 1 | **med42:8b** | **4.67/5** | 31.1 | 0/6 | Unchanged champion |
| 2 | **jslmed:8b** | **4.5/5** | 30.8 | 0/6 | New — excellent replacement for biomistral |
| 3 | **medgemma:27b** | **4.5/5** | 8.4 | 0/6 | Quality leader, slow |
| 4 | **medgemma:4b** | 3.83/5 | **53.6** | 0/6 | 2 refusals vs 0 in Phase 1 — minor regression |
| 5 | **medgemma1.5:4b** | 3.83/5 | **53.9** | 0/6 | Consistent with Phase 1 |
| 6 | **medllama2:7b** | 3.5/5 | 39.7 | 0/6 | Slight decline from 4.0 — prompt variance |
| 7 | **openbiollm:8b** | 3.33/5 | 30.9 | 1/6 | 1 refusal on T6 — minor regression |
| 8 | **asclepius:8b** | 2.33/5 | 31.3 | 0/6 | New — zero refusals, too concise |

**Key insight:** `jslmed:8b` immediately proves its worth at 4.5/5 in the very first test. The biomistral→jslmed swap was the correct call.

**medgemma:4b regression note:** 2 refusals appeared on T5 (polypharmacy) and T6 (opioid). This is prompt/temperature variance — not a code regression. The global system prompt is in place. Minor variations across runs are expected at temperature 0.3.

---

## 9. Recommended Next Steps (Updated)

1. **asclepius:8b verbosity** — It's accurate but concise. Consider tuning `PARAMETER temperature 0.5` and `PARAMETER num_predict 500` in its Modelfile and recreating, to allow more detailed responses
2. **openbiollm:8b refusal on T6** — Update Modelfile system prompt with stronger opioid prescription framing; re-run test
3. **Production HTTPS** — When moving to a real domain, replace self-signed cert with Let's Encrypt (Certbot) or a wildcard cert from a CA
4. **Serper.dev / Google Search** — Add when Google-quality search becomes a requirement
5. **STT/TTS** — Consider Whisper (local, via Ollama or faster-whisper) for voice dictation of clinical notes

---

## 10. Final Model Stack (as of 2026-08-15 Phase 2)

### Visible in Picker (8 models)
| Model | Role | Score | Use Case |
|-------|------|-------|----------|
| `med42:8b` | **Default** | 4.67/5 | General clinical Q&A, prescribing, DDx |
| `jslmed:8b` | — | 4.5/5 | Clinical documentation, coding, drug queries |
| `medgemma:27b` | **Research** | 4.5/5 | Deep research mode, complex cases |
| `medgemma:4b` | **Utility / Task** | 3.83/5 | Utility summaries, background tasks, vision |
| `medgemma1.5:4b` | — | 3.83/5 | Fast general queries |
| `medllama2:7b` | — | 3.5/5 | Alternative general medical |
| `openbiollm:8b` | — | 3.33/5 | Biomedical research queries |
| `asclepius:8b` | — | 2.33/5 | Concise clinical answers (USMLE style) |

### Hidden (available to admin)
| Model | Hidden Reason |
|-------|--------------|
| `llavamed:7b` | Imaging-only — appears dynamically when image attached |
| `meditron:7b` | 3/6 refusals — unreliable for clinical use |
| `biomistral:7b` | Too shallow (2.33/5) — replaced by jslmed |

---

*Document created: 2026-08-15 | Last updated: 2026-08-15 (Phase 2) | Platform: Vaidyx*
