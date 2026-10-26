# Voice wiring (research for Phase 4)

Plan item 0.9, written 27/10/2026. Read-only research: nothing was started, downloaded or installed. Sources are file and line in this repository, commands run on this server on 27/10/2026, or the URLs listed at the end of each fact. "Oct note" means `docs/tumour-board/audio_feature.md` (the October research, 12 to 15/10/2026).

## 1. Summary

1. Voice is allowed by owner decision D1 and D2 (`docs/night-v3/PLAN.md:35-36`): local models only, audio never stored, speech to text only fills a text box the person edits and sends, text to speech only reads text already on screen or an agent's grounded answer.
2. The October choice stands: faster-whisper large-v3-turbo fp16 with Silero VAD for speech to text, Kokoro-82M for text to speech, one small service on 127.0.0.1:7120 in `/data/vaidyx/venv/audio`, proxied by the app (Oct note lines 37-56, 205-226).
3. GPU budget now, with both model servers up: 125,789 of 143,771 MiB used, so about 17,980 MiB free. Default voice engines need about 3.5 GB (2,289 + about 1,200 MiB measured in October); Cohere on top adds 4.7 GB. It fits with at least 9 GB to spare.
4. Missing in the audio venv, and a plan-changing fact: **no FastAPI, uvicorn or python-multipart** (neither the venv nor the shared mlenv has them). `aiohttp` 3.14.5 is installed and does multipart, so the service is written with aiohttp, with no install. Also missing there: librosa, sentencepiece, accelerate, which Cohere Transcribe needs (they exist in the `audio3` venv).
5. espeak-ng is not on PATH, but October's open item is nearly closed: espeak-ng 1.53.0 is built at `/data/vaidyx/tools/espeak-ng`, and `phonemizer` works with it when `PHONEMIZER_ESPEAK_LIBRARY` is set (tested today). misaki overwrites the library path at import with a wheel that fails on this glibc, so the service must set it again after the import (section 3.4).
6. No ffmpeg on PATH is fine: PyAV 17.1.0 is installed and decodes browser audio (webm/opus, mp4/aac, ogg, wav) from memory; faster-whisper uses it.
7. One app finding: the Tumour Board guard refuses any non-multipart POST body over 1 MB (`routes/tumour_board_routes.py:94-111`), so the browser must upload audio as multipart, or 60 s of WAV would be refused (section 5).
8. Text to speech is bound to the screen: the app resolves what to say from a reference (an answer or saved text) or from short on-screen text, never free text from a script; the audit line holds who, screen, seconds, engine and time, never the text.
9. The microphone and speaker buttons match `ActionButton`, `Field` (its `trailing` slot) and the tokens in `index.css`; every box that takes sentences gets a `MicButton`, boxes that take names, IDs, dates or numbers do not (section 7).
10. Open questions for the owner are in section 9 (Cohere now or later, one voice or one per agent, whether the call microphone is muted while dictating, a token on port 7120, and others).

## 2. What the October research settled

From the Oct note, with line numbers.

| Topic | Settled | Numbers |
|---|---|---|
| In scope | STT fills the box (like OCR, a reading layer); TTS reads text already shown; push to talk; first audio under a second. Out: speech-to-speech models, Web Speech API, voice commands that change records (lines 8-17) | none |
| Why not the Web Speech API | Chrome sends the audio to a web service and it does not work offline (MDN: https://developer.mozilla.org/en-US/docs/Web/API/SpeechRecognition ; the Oct note line 14 and 97) | not used |
| GPU at the time | 143,771 MiB card, 128,759 in use, 14.4 GB free; audio budget under 4 GB (lines 26-30) | now 17,980 MiB free |
| STT default | faster-whisper large-v3-turbo, CTranslate2 float16, Silero VAD, `language="en"`, `condition_on_previous_text=False`, beam 5, clinical initial prompt (lines 49-51, 205-209) | 2,289 MiB; 0.18 to 0.20 s per 10 s; WER 0.079 on six clinical sentences (0.110 without the prompt); Svarah WER 0.050 (0.053 with the prompt, 40 Indian-English clips); Common Voice Indian accent 0.176 with the prompt (16 clips) (lines 165-166, 185-187) |
| STT second engine | Cohere Transcribe 03-2026, switchable, off by default, gated weights (lines 210-212) | 4,725 MiB bf16; 0.4 to 1.5 s; clinical WER 0.102; Svarah 0.064; Common Voice 0.115 (lines 173, 188) |
| STT CPU fallback | Parakeet-TDT-0.6B-v2 ONNX with number clean-up (lines 213-214) | 0 GB GPU; 0.42 to 0.62 s on CPU; Svarah 0.114; writes numbers as words |
| Not chosen | large-v3, Granite 2B, MedASR, Chatterbox, Pocket TTS (lines 215-217) | see lines 147-148, 172, 174 |
| TTS | Kokoro-82M, 24 kHz, voices af_heart, bf_emma, am_michael tested; sentence by sentence; CPU fallback (lines 52-53, 218-219) | 810 to 1,209 MiB; first audio 63 to 78 ms; RTF 0.007; 30 s answer in 0.25 s; CPU first sentence 1.0 to 3.3 s (line 145-146) |
| TTS weak point | numbers, units, abbreviations, dates, drug names; Kokoro reads "g/dL" as letters, drops "mg", "SUVmax", "Reg.", "Kavita", "decilitre", "immunohistochemistry", every drug name when espeak-ng is absent; "mrT3b" becomes "mister t three b"; "14/09/2026" reads poorly (lines 124-129, 150-159) | fix: a deterministic normaliser plus a lexicon in front of the TTS, espeak-ng as catch-all for unknown words |
| STT clean-up | "MRT3BN1" to "mrT3b N1"; spelling left as spoken; the clinician reads and submits (lines 220-223) | none |
| Architecture | browser records, app checks the session and proxies, audio service on 127.0.0.1:7120, empty `TB_AUDIO_URL` means off, buttons hidden when the service fails, audit with seconds, characters, model, by; no audio stored (lines 37-56) | none |
| Secure context | `getUserMedia` needs https or localhost; `http://<lan-ip>:7000` is not secure (line 34) | doc for Eswar |
| CSP | `media-src 'self' blob:` and `connect-src 'self'` already allow posting audio and playing a same-origin blob (line 35); confirmed today in `core/middleware.py:131,136` |  |
| Caveat | the 15/10 runs were on an idle card: latencies must be re-measured with both LLMs loaded (lines 224-226) | item 4.5 does this |
| Not recorded in the Oct note | the exact 20-word clinical prompt and the lexicon file are not in the note (they lived in the old scratchpad); section 4.4 proposes a new prompt and lexicon to be rebuilt and tested | |

Naming differences: the October plan called the files `tumour_board/audio_service.py` and `serve_audio.sh` with `/transcribe` and `/speak` (lines 242-243); PLAN item 4.1 says `tumour_board/audio_service/` (a package), `scripts/audio.sh` and `/stt`, `/tts`, `/health`. Follow the plan.

Precision (the "no lossy layer" rule, `CLAUDE.md`, and the plan's allowance of fp16 for voice): Whisper runs as shipped in float16 (the converted checkpoint `model.bin` of `mobiuslabsgmbh/faster-whisper-large-v3-turbo`, `compute_type="float16"`); Cohere in bf16; Kokoro uses the shipped `kokoro-v1_0.pth` unchanged; Parakeet is the fp32 ONNX. No int8, no GGUF, no quantised path anywhere. Say "fp16" for Whisper in the model card.

## 3. The environment now (27/10/2026)

### 3.1 Installed in `/data/vaidyx/venv/audio` (Python 3.10.21; `include-system-site-packages = true`, home is the shared mlenv)

| Package | Version | Note |
|---|---|---|
| faster-whisper | 1.2.1 | `transcribe(... vad_filter=True ...)` is the default in this version (`faster_whisper/transcribe.py:289`); `hotwords` (line 296) and `initial_prompt` (line 279) exist |
| ctranslate2 | 4.8.2 | needs CUDA 12 cuBLAS and cuDNN 9 |
| nvidia-cublas-cu12 / nvidia-cudnn-cu12 | 12.9.2.10 / 9.27.0.42 | wheels present beside the CUDA 13 ones; the start script must put their `lib` directories on `LD_LIBRARY_PATH` (Oct note lines 92-94) |
| torch / torchaudio | 2.14.0+cu130 / 2.11.0+cu130 | shared with mlenv |
| kokoro / misaki | 0.9.4 / 0.9.4 | |
| spacy and `en_core_web_sm` | 3.8.16 / 3.8.0 | present, so no first-run download |
| phonemizer-fork, espeakng-loader | 3.3.2, 0.2.4 | the loader wheel does not run on this glibc (Oct note lines 155-157) |
| onnx-asr, onnxruntime, onnxruntime-gpu | 0.12.0, 1.23.2 | Parakeet |
| transformers | 5.19.0 | Cohere needs >= 5.4 (model README) |
| av (PyAV) | 17.1.0 | decodes browser audio without an ffmpeg binary; `faster_whisper/audio.py:19-22` `decode_audio` takes a path or a binary file object, so an in-memory buffer works |
| soundfile, numpy, scipy, jiwer, num2words, aiohttp, httpx, pydantic, loguru | 0.14.0, 2.2.6, 1.15.3, 4.0.0, present, 3.14.5, 0.28.1, 2.14.1, 0.7.3 | `pip list` and `import` checks |
| Silero VAD | bundled | `faster_whisper/assets/silero_vad_v6.onnx`; no separate package needed. Silero: about 2 MB, 8 and 16 kHz, under 1 ms per 30 ms chunk on one CPU thread, MIT (https://github.com/snakers4/silero-vad) |

### 3.2 Missing, and the fallback (no new installs are allowed)

| Missing | Effect | Fallback |
|---|---|---|
| fastapi, uvicorn, starlette, python-multipart in the audio venv (`pip list` shows none; the app venv `/data/vaidyx/venv/app` has fastapi 0.142.2, uvicorn 0.54.0, python-multipart 0.0.32 but no torch) | the Oct plan's FastAPI service cannot start as written | write the service with **aiohttp 3.14.5** (installed; has multipart reading, streaming responses, a body size cap). Do not add the app venv's site-packages to the audio venv |
| librosa, sentencepiece, accelerate in the audio venv | Cohere Transcribe cannot load there | the `audio3` venv has transformers 5.19.0, torch 2.14.0+cu130, librosa 0.11.0, sentencepiece 0.2.2, accelerate 1.15.0, soundfile 0.14.0 (checked today). Run Cohere as a separate worker process in `audio3` (own CUDA libraries, avoiding the cuDNN clash of Oct note line 172), started by the audio service on demand. Until then `engine=cohere` answers 503 `engine_unavailable` |
| espeak-ng and ffmpeg on PATH | none for us | espeak-ng is built at `/data/vaidyx/tools/espeak-ng` (version 1.53.0, `bin/espeak-ng`, `lib64/libespeak-ng.so`, data in `share/espeak-ng-data`); PyAV replaces ffmpeg |
| Kokoro voices | only `af_heart`, `bf_emma`, `am_michael` are in `~/.cache/huggingface/hub/models--hexgrad--Kokoro-82M/snapshots/*/voices` | Kokoro has 54 voices (https://huggingface.co/hexgrad/Kokoro-82M), but fetching more is a download: not allowed in this run without the owner |
| The October test scripts and clinical prompt/lexicon | not in the repository | rebuilt in item 4.1 and 4.5 from the sentences described in the Oct note |

### 3.3 Model caches in `~/.cache/huggingface/hub` (names only)

`mobiuslabsgmbh/faster-whisper-large-v3-turbo` (config, model.bin, vocabulary), `hexgrad/Kokoro-82M` (config, kokoro-v1_0.pth, voices), `CohereLabs/cohere-transcribe-03-2026` (3.9 GB, safetensors, Apache-2.0 per its README header and line 552, gated download, already accepted, 14 languages), `istupakov/parakeet-tdt-0.6b-v2-onnx` and `-v3-onnx` (CC-BY-4.0, English only for v2, https://huggingface.co/istupakov/parakeet-tdt-0.6b-v2-onnx), also `Systran/faster-whisper-large-v3`, `Systran/faster-distil-whisper-large-v3`, `ibm-granite/granite-speech-4.1-2b`, `google/MedASR`, `kyutai/pocket-tts-without-voice-cloning`, `ResembleAI/chatterbox-turbo`, `maya-research/maya1`, `hubertsiuzdak/snac_24khz`, datasets `ai4bharat/Svarah`, `ishands/commonvoice-indian_accent`, `jdh-algo/MedDocBench`. The service sets `HF_HUB_OFFLINE=1` so nothing is ever fetched.

### 3.4 GPU, ports, espeak-ng

- `nvidia-smi` (27/10/2026): 125,789 MiB used of 143,771 MiB; two processes, 24,358 MiB (reader) and 101,414 MiB (reasoner); about 17,980 MiB free (a second reading minutes later: 17,368 MiB free).
- Budget: default engines about 3.5 GB (Whisper 2,289 MiB + Kokoro 810 to 1,209 MiB, Oct note 145, 165); with Cohere about 8.2 GB; leaves 9 GB or more. vLLM pre-allocates its cache, so it does not grow into this space. Rule: if free memory is under 3 GB at load time the service loads on CPU and says so in `/health`.
- Listening now: 7000 (app), 7130 (mock HIS), 8100, 8101 (models), 7880 (LiveKit), 8042 (Orthanc). 7120 is free; no `tumour_board/audio_service/` and no `scripts/audio.sh` yet (checked).
- espeak-ng test today: with `PHONEMIZER_ESPEAK_LIBRARY=/data/vaidyx/tools/espeak-ng/lib64/libespeak-ng.so`, `phonemizer`'s `EspeakBackend("en-us")` phonemised "capecitabine 11.8 g/dL" (output "kˈeɪpsɪtˌæbaɪn ɪlˈɛvən.ˈeɪt dʒˈiː slˈæʃ dˈiː ˈɛl"). `misaki/espeak.py:5-8` sets the library and data path from `espeakng_loader` at import time, which overrides the variable; the service must call `EspeakWrapper.set_library("/data/vaidyx/tools/espeak-ng/lib64/libespeak-ng.so")` and `EspeakWrapper.set_data_path(".../share/espeak-ng-data")` right after importing `misaki.espeak`, then build `KPipeline` with the fallback on (`misaki/en.py:664-700` uses it for out-of-dictionary words). Item 4.1 must verify this end to end (not run today: it loads Kokoro). If it fails, the lexicon alone carries the clinical words and unknown words are skipped (the October behaviour).

## 4. The audio service (item 4.1)

Where: `tumour_board/audio_service/` (package: `__main__.py` server, `stt.py`, `tts.py`, `text_norm.py` normaliser and lexicon, `limits.py`), run as `/data/vaidyx/venv/audio/bin/python -m tumour_board.audio_service` (`tumour_board/__init__.py` is 109 bytes, a docstring only, so the import is light). It imports nothing else from `tumour_board/`. Binds `127.0.0.1:7120` only; never tunnelled (`CLAUDE.md`, Mock hospital ports). Web framework: aiohttp (section 3.2).

### 4.1 `GET /health`

No model load, answers in under 50 ms. JSON:

```
{"status":"ok","version":"1","limits":{"stt_seconds":60,"stt_bytes":4194304,"tts_chars":2000},
 "stt":{"engine":"whisper-large-v3-turbo","state":"ready|loading|not_loaded|error","device":"cuda|cpu","precision":"float16","fallback":"parakeet-v2-cpu"},
 "tts":{"engine":"kokoro-82m","state":"...","device":"cuda|cpu","sample_rate":24000,"voices":["af_heart","bf_emma","am_michael"]},
 "engines":{"cohere":"unavailable|ready","parakeet":"ready"},
 "gpu_free_mib":17980}
```
`not_loaded` means "will load on first use" (lazy). A flag `?warm=1` loads both models now (the start script uses it once at start so the first dictation is fast; 12.7 s first Kokoro load, 4 s after, Oct note line 145).

### 4.2 `POST /stt`

- Request: `multipart/form-data` with part `audio` (the file) and optional text parts `engine` (`whisper` default, `parakeet`, `cohere`), `language` (`en` only in the first cut), `context` (`question|decision|note|reason`, picks a prompt variant), `words` (`0|1`, word times, default 0). A raw body with `Content-Type: audio/*` is also accepted for scripts and the evaluation.
- Accepted types: the header is not trusted; the service sniffs the first bytes (EBML for webm, `ftyp` for mp4/m4a, `OggS`, `RIFF....WAVE`, `ID3` or MPEG sync for mp3, `fLaC`) and lets PyAV decode. Chrome and Firefox give `audio/webm;codecs=opus`, Safari `audio/mp4`; probe with `MediaRecorder.isTypeSupported` (https://developer.mozilla.org/en-US/docs/Web/API/MediaRecorder/isTypeSupported_static; per-browser support is not on that page, so probe at run time and read `recorder.mimeType`). `video/webm` and `video/mp4` containers with only audio are accepted too.
- Caps: body 4 MiB (`client_max_size`), 60 s of audio after decoding (a 61 s tolerance for encoder padding); longer returns 413 `too_long`. Sixty seconds of opus is about 0.3 to 0.5 MB, of 16 kHz mono WAV 1.9 MB.
- Pipeline: decode to float32 mono 16 kHz from the in-memory buffer, then VAD, then the engine, then the light clean-up.
  - Engine `whisper`: `WhisperModel("large-v3-turbo" local path, device="cuda", compute_type="float16")`, `transcribe(audio, language="en", beam_size=5, condition_on_previous_text=False, vad_filter=True, vad_parameters={"threshold":0.5,"min_silence_duration_ms":500,"min_speech_duration_ms":250,"speech_pad_ms":400}, initial_prompt=<section 4.4>, word_timestamps=<words>, no_speech_threshold=0.6, log_prob_threshold=-1.0)`. The library default for `min_silence_duration_ms` is 2000 and for `speech_pad_ms` 400 (`faster_whisper/vad.py`, `VadOptions`); 500 ms cuts a dictation into sensible segments. The README says the default beam size is 5 and that audio is decoded with PyAV so no ffmpeg is needed (https://github.com/SYSTRAN/faster-whisper). `language="en"` is the setting for Indian English: Whisper has no separate Indian-English code; accent robustness comes from the model and the prompt (Svarah WER 0.050 to 0.053, Oct note lines 185-187).
  - Silence and hallucination guard: if VAD finds under 0.3 s of speech, return empty text with `code: "no_speech"` without running the model (the "Careless Whisper" finding of invented text on silence, Oct note lines 95-98). Drop any segment with `no_speech_prob > 0.6` and `avg_logprob < -1.0`. Drop a result whose text is a known filler repeated (the same 3-gram four times).
  - Engine `parakeet`: `onnx_asr.load_model("nemo-parakeet-tdt-0.6b-v2")` from the cache with the CPU provider (CC-BY-4.0, English only), plus inverse normalisation of spoken numbers ("eleven point eight" to "11.8"); used automatically when the GPU load fails or free GPU memory is under 3 GB, and when `engine=parakeet` is asked.
  - Engine `cohere`: worker in the `audio3` venv, bf16, `language="en"` (README quick start uses `processor(audio, sampling_rate=16000, return_tensors="pt", language="en")`); off unless the worker is present.
- Response 200:
```
{"text":"...","segments":[{"start":0.0,"end":3.2,"text":"..."}],"language":"en","duration":7.4,
 "speech_seconds":6.1,"engine":"whisper-large-v3-turbo","device":"cuda","took_ms":210,"code":null}
```
 `text` is the whole transcript joined, after the clean-up of 4.4. `took_ms` covers decode, VAD and the engine.
- Errors (all JSON `{"code","message"}`, plain words, never echoing text): 400 `bad_request` (no `audio` part); 413 `too_big` or `too_long`; 415 `unsupported_audio` (cannot decode); 429 `busy` (more than 4 waiting, or waited over 10 s for the one STT slot); 503 `loading` (model still loading, retry in a few seconds) or `engine_unavailable`; 500 `failed`.

### 4.3 `POST /tts`

- Request JSON: `{"text":"...","voice":"af_heart","speed":1.0,"normalise":true,"format":"wav"}`. `text` up to 2,000 characters; the service splits it into sentences and renders each (Kokoro takes at most 510 phonemes per call, Oct note line 128; `KPipeline.__call__` has `split_pattern` default `\n+` and a `speed` argument, `kokoro/pipeline.py:351-358`). Voices are the three cached ones; speed 0.8 to 1.25.
- The clinical normaliser (4.4) runs first; `normalise:false` is for tests only.
- Response, whole clip (default): `200 audio/wav`, mono, 24,000 Hz, 16-bit PCM (Kokoro's sample rate, https://huggingface.co/hexgrad/Kokoro-82M), header `X-Took-Ms`. The app calls it once per sentence (decided in `05_board_agents.md` section 5, recommendation (a)), so each response is a small complete WAV that plays from a blob. A raw `?stream=1` mode (chunked `audio/L16;rate=24000`, one chunk per sentence, header `X-Sample-Rate: 24000`) is kept for later; not needed for Phase 4.
- Errors as in STT: 400 (empty text), 413 `text_too_long`, 415 voice unknown (400), 429 `busy`, 503 `loading` or `engine_unavailable`, 500.
- CPU fallback: if the GPU load fails or free GPU memory is under 1.5 GB, Kokoro loads on CPU (first sentence 1.0 to 3.3 s, Oct note line 146). `/health` shows `device`.

### 4.4 The clinical prompt, the clean-up and the lexicon (proposed; to be rebuilt and tested in 4.1)

STT initial prompt (Whisper allows at most 224 tokens of prompt; keep it near 80). Draft, plain English with the vocabulary the sentences use:

> "Tumour board clinical note. Haemoglobin 11.8 g/dL, platelets 245,000 per microlitre, cT3 N2 M0, mrT3b N1, ER positive, PR positive, HER2, PD-L1 TPS 60%, ECOG 1, SUVmax, HPE, IHC, MRI, UHID, PM-JAY, NCG, ICMR. Capecitabine, oxaliplatin, trastuzumab, pembrolizumab."

Variants per `context` add nothing patient-specific. The prompt never contains patient data (the engine would otherwise echo it). The `hotwords` parameter of faster-whisper 1.2.1 (`transcribe.py:296`) is an alternative to test; the prompt is the October-tested route.

STT clean-up (after the engine, before the box): only token reshaping that cannot invent content: a staging token written run together or with spaces is reshaped by a pattern ("MRT3BN1" to "mrT3b N1", "c t 3 n 2" to "cT3 N2"); "per cent" to "%"; "g d l" to "g/dL". Spelling stays as spoken; numbers keep the engine's digits ("245,000"). The clean-up is a pure function with unit tests.

TTS normaliser `text_norm.py` (deterministic, in front of Kokoro): units to words ("g/dL" to "grams per decilitre", "mg" "milligrams", "mL", "mcL", "cm", "mm", "%" "percent"); decimals ("11.8" to "eleven point eight", with `num2words`, installed); thousands ("245,000" to "two hundred forty-five thousand"); dates DD/MM/YYYY ("14/09/2026" to "fourteenth of September, twenty twenty-six", fixing Oct note line 152); staging strings spelled ("mrT3b N1" to "m r T 3 b, N 1"; "cT3 N2 M0" "c T 3, N 2, M 0"); abbreviations expanded or spelled ("SUVmax" "S U V max", "ECOG", "HER2" "H E R 2", "ER" "E R", "UHID" "U H I D", "PM-JAY" "P M jay", "Reg." "registration"); "Dr" to "Doctor"; a lexicon of histology terms, drug names and Indian names given to misaki as phonemes (`pipeline.g2p.lexicon.golds`, the route measured in October, Oct note lines 154-155), with espeak-ng as the catch-all (section 3.4). The words that vanished in October must be in the first lexicon: mg, SUVmax, Reg., Kavita, decilitre, microlitre, immunohistochemistry, capecitabine, oxaliplatin, trastuzumab, pembrolizumab. Spoken form never changes the on-screen text.

### 4.5 Loading, memory, concurrency

- Lazy and once: each engine loads on first use under an `asyncio.Lock` and stays loaded (about 3.5 GB total). `--warm` at start loads both. No unload, so the cost is paid once.
- One STT job and one TTS job run at a time (a `Semaphore(1)` each, work in a thread executor); more wait up to 10 s, then 429 `busy`. This protects the GPU shared with vLLM (CLAUDE.md: single H200, one GPU job at a time for evaluations).
- The model load uses `HF_HUB_OFFLINE=1` and `TRANSFORMERS_OFFLINE=1`.

### 4.6 The "nothing stored" rule, in code

- Audio lives in an `io.BytesIO` / `bytes` object for the length of the request: PyAV and `decode_audio` take a binary file object (`faster_whisper/audio.py:19-22`); `onnx-asr` and Kokoro take arrays. No `tempfile`, no `open(..., "wb")`, no cache directory for audio, no disk spill (aiohttp reads multipart parts into memory under the 4 MiB cap).
- The server logs one line per request with: time, route, status, audio seconds, engine, device, `took_ms`, byte count. Never text, never a filename, never an error message that quotes content. `access_log=None` on aiohttp (it would log the path only, but one rule is simpler). No debug dumps; no crash dump of the request body.
- Tests prove it: a test patches `tempfile.*`, `open` for writing and `os.open` to fail inside the service module and passes; a test runs a request with a unique sentence and asserts the log file and the working directory contain no trace of it (item 4.1 "nothing stored").
- Optional guard (to confirm with the owner, section 9): a random shared token read from a mode-600 file by both the app and the service (as `scripts/livekit.sh` does for its keys), sent as `X-Audio-Token`, because 127.0.0.1:7120 is reachable by any local user on this shared server. Never printed.

### 4.7 `scripts/audio.sh start|stop|status|restart`

After `scripts/demo_services.sh` (`port_pid` using `ss -ltnp` and the pid of the listener, `LOGS=~/vaidyx/logs`, `setsid nohup ... &`, a loop waiting up to 60 s for `curl http://127.0.0.1:7120/health`, `stop` by `kill` of the port's pid, `status` printing "audio: listening on :7120" or "not running"). Specifics:

- `PY=/data/vaidyx/venv/audio/bin/python`; the working directory is the repository so `-m tumour_board.audio_service` resolves.
- Environment: `LD_LIBRARY_PATH` with the `nvidia/cublas/lib` and `nvidia/cudnn/lib` directories of the audio venv's cu12 wheels (Oct note lines 92-94), `PHONEMIZER_ESPEAK_LIBRARY` and `ESPEAK_DATA_PATH` for the espeak build, `HF_HUB_OFFLINE=1`, `TRANSFORMERS_OFFLINE=1`.
- Log: `~/vaidyx/logs/audio.log` (metadata only). Add `audio:7120` to the status pairs and `start_audio` / `stop_audio` to `scripts/demo_services.sh` (a small change to a script, not app code), as `video` was added there.
- Start the service after the model servers, since the load-time free-memory check reads the card.

### 4.8 Tests (item 4.1)

`tumour_board/tests/test_audio_service.py` (models stubbed so it also runs in the app venv): size, type and duration caps (a generated 61 s tone gives 413); sniffing; silence and white noise give empty text and no model call; a generated tone is not text; error JSON shape; 429 under load; the log and the no-temp-file checks; `text_norm` cases from the Oct note (g/dL, mg, SUVmax, mrT3b, 14/09/2026, "245,000", drug names, "Kavita"); the STT clean-up cases ("MRT3BN1"). Round trip (GPU, run alone, audio venv): Kokoro speaks the six clinical sentences, the service transcribes them, WER at most 0.12 (October measured 0.079). Small audio is generated with numpy (sine, silence, noise) and `soundfile` into `BytesIO`; no fixture audio is committed beyond a few seconds.

## 5. The app routes (item 4.2)

New module `tumour_board/api/audio.py` registered like the others in `tumour_board/api/` (see `api/helpers.py`, which defines its limiters at lines 10-11), served under `/api/tb/audio/`.

How an existing side service is proxied and guarded (`tumour_board/pacs.py`): a `check()` before forwarding, refusal as JSON `{"detail": ...}` with a status (`pacs.py:277-285`); one shared `httpx.AsyncClient`, timeout 60 s and connect 10 s, `follow_redirects=False` (`pacs.py:263-269`); a short header allow-list both ways, never cookies or `Authorization` (`pacs.py:40-41`, `296-299`); an audited event written through `store.audit` (`pacs.py:288-291`). The login: `routes/tumour_board_routes.py:179-181` `_user`, `_roles` (just below), `_need_known` (line 211: a placed account, not disabled). The route guard wrapper (lines 125-170) already does the cross-site Origin check for POST (lines 128-133), the 8 hour idle logout, the forced password change and the disabled check. The rate limiter is `tumour_board/api/common.py:85-108` `RateLimit(limit, window)` with `check(key, message)` raising 429 `{"message","code":"rate_limited"}`, key from `common.client_key(request)` (the login, else the host); examples `PREPARE_LIMIT = common.RateLimit(10, 600)` and `ASK_LIMIT = common.RateLimit(20, 600)` in `api/helpers.py:10-11`; the front end already shows a wait message on 429 (`AskPanel.tsx`, `askErr`). Audit helpers: `common.audit(case_id, kind, by, **fields)` (`api/common.py:80-83`, the Case File's hash-chained log, `store.py:220`) and `org.audit(kind, by, **fields)` (`tumour_board/org.py:259`, `org_audit.jsonl`).

### 5.1 Routes

| Route | Behind | What it does |
|---|---|---|
| `GET /api/tb/audio/status` | login + `_need_known` | `{"enabled":bool,"stt":"ready|loading|down|off","tts":"...","limits":{...},"cohere":bool}`. `enabled` is false when `TB_AUDIO_URL` is empty (no call made). Otherwise asks `/health` (timeout 1.5 s) and caches the answer 15 s, so a page of buttons does not hit the service. Never fails: down gives `"down"` |
| `POST /api/tb/audio/stt` | same | multipart `audio` + `screen` (a short id such as `ask`, `question`, `decision`, `reason`, `note`, `helper-radiology`, `meeting-q`, `message`) + optional `case_id` and `context`. Forwards to `/stt`, returns `{text, segments, duration, engine, took_ms}` |
| `POST /api/tb/audio/tts` | same | body below; returns the WAV |

TTS body, two modes, so the app can prove the speaker only reads allowed text (D1): (a) a **reference**: `{"ref":{"kind":"chat","case_id":"TB-...","id":"<thread id>","index":2}}` (kinds: `chat` Case File answers, `agent` helper answers, `meeting_answer`, `summary`, `points`); the server loads that saved statement and speaks it, so the request carries no text and the audit line holds the reference; (b) **on-screen text**: `{"text":"...","screen":"decision"}` up to 1,000 characters, for text the person just typed or dictated (a "read back" button); rate limited tighter, audited by length only. The meeting's live agent answer is saved by `board.log_answer` as it is shown (`05_board_agents.md` section 5, "Audit"), so mode (a) covers agents. Whether mode (b) is allowed is open question 4.

Who may hear or dictate into a Case File (rules for item 4.2; the routes never widen what a screen shows):

- **`/tts` with a reference** (`{"kind":"chat|agent|summary|points|meeting_answer","case_id":...}`) runs the same check as the screen that shows the statement, before the statement is loaded: for `chat`, `agent`, `summary` and `points`, `access.scope(roles, case)` (`tumour_board/access.py:308`) must be `FULL`; for `meeting_answer` (the reference also carries the meeting id), the meeting is loaded with `meetings.need(mid)` and `meetings.may_view(roles, meeting)` (`tumour_board/meetings.py:202`, the check of the meeting page and its WebSocket) must be true. Otherwise the route answers 404 (the same as an unknown id, so it does not tell which ids exist) and nothing is spoken; the refusal is audited without the reference text.
- **`/stt` with `case_id`**: the id is kept for the audit line only when `access.scope(roles, case)` is not None (`FULL` or `REQUESTS`). Otherwise the id is dropped and the request is audited without a Case File (the `org.audit` line only, no `common.audit`), so nobody can write audit lines into a Case File they cannot open or probe which ids exist. The transcription itself is returned either way (it only fills the person's own text box).
- **Tests** (`tumour_board/tests/test_audio_routes.py`, service stubbed): a reference to a Case File the user cannot open (scope None, and scope `REQUESTS` for `chat`, `agent`, `summary`, `points`) gives 404, the stubbed service is never called and no statement is loaded; a `meeting_answer` reference by a user for whom `meetings.may_view` is false gives 404; an allowed reference speaks. `/stt` with the `case_id` of a Case File the user cannot open writes no line into that Case File's audit and an `org.audit` line without `case_id`; with an allowed id it writes both.

### 5.2 Limits (proposed)

- STT: 40 requests per 10 minutes per user (`RateLimit(40, 600)`), body at most 4 MiB, at most 60 s. Multipart is required from the browser because the guard refuses any non-multipart body over 1 MB (`_json_too_big`, `routes/tumour_board_routes.py:94-111`: it skips only `multipart/`, line 98); a raw WAV of 60 s is 1.9 MB.
- TTS: 240 sentences per 10 minutes per user (`RateLimit(240, 600)`; an answer of six sentences x 20 questions is 120; the room screen's account fetches every sentence of every answer), at most 2,000 characters per request (1,000 in mode (b)).
- Status: 60 per minute.
- Concurrency is bounded in the service (4.5), so a flood returns 429 `busy` and the front end falls back to text.
- Roles: any placed account may dictate and listen; the meeting room screen account too. No new permission is added to `org.py`.

### 5.3 The audit line (no content)

`org.audit("audio_transcribed", by=user, screen="decision", case_id="TB-...", seconds=7.4, engine="whisper-large-v3-turbo", took_ms=210, chars=164)` and `org.audit("audio_spoken", by=user, screen="meeting", ref="meeting_answer:...", sentences=3, chars=240, voice="af_heart", took_ms=95)`. When `case_id` is given and passes the check in 5.1 (scope not None), also `common.audit(case_id, "audio_transcribed", by, screen=..., seconds=..., engine=...)` so the Case File's log shows that a voice box was used. Never the text, never the audio, never a filename. (The October note audited seconds, characters, model and by, Oct note line 54; this keeps that.) One line per request, not per sentence, for TTS: the app sums a batch with a `batch` id the front end sends.

### 5.4 Start script and config

- `~/vaidyx/start_vaidyx_app.sh` today sets `TB_STAGING=preview APP_BIND=127.0.0.1 APP_PORT=7000` inline before `python app.py`; item 4.2 adds `TB_AUDIO_URL=http://127.0.0.1:7120` there (and `TB_AUDIO_TOKEN_FILE` if the token is accepted). `scripts/demo_services.sh start_app` sets only `APP_BIND` and `APP_PORT`: add the variable there too, or voice would silently be off when the app is started that way.
- `tumour_board/config.py` reads URLs with `os.getenv` (lines 25-27 for the models): add `AUDIO_URL = os.getenv("TB_AUDIO_URL", "").rstrip("/")`. Empty means off.
- The proxy client: a shared `httpx.AsyncClient`, connect 2 s, read 30 s, redirects off, no cookies forwarded, response header allow-list `content-type`, `content-length`, `x-took-ms`.

### 5.5 Degrading to text

- Off by design (empty `TB_AUDIO_URL`): `status.enabled=false`; the front end renders no microphone or speaker at all, and the page looks as it does today.
- On but the service is down or loading: `enabled=true`, `stt:"down"`; `MicButton` is shown disabled with the reason "Voice is not running on this server. You can type instead." and `SpeakButton` is shown disabled with "Voice is not running. The text is on screen."; both re-check on the next focus or after 30 s. A 502 or 503 from a route during use shows a toast and leaves the box untouched.
- A TTS failure never blocks the text: the answer is already on screen; the agent tile shows "Voice unavailable, text only" (`05_board_agents.md` section 5, point 5), never "speaking".
- The Content Security Policy needs no change: `core/middleware.py:131` `media-src 'self' blob:` plays a blob made from the response, and `connect-src 'self' ws://127.0.0.1:7880 http://127.0.0.1:7880` (line 136) allows same-origin posts; `Permissions-Policy: camera=(self), microphone=(self), geolocation=()` (line 86) already lets the page record. A `data:` URL would not play (not in `media-src`): always `URL.createObjectURL`. Not verified: that the `/tb-nik` shell is served through the same default branch of this middleware (the `else` at line 111); check with a curl of the headers in item 4.2.

## 6. The components (item 4.3)

Files: `web/tb-nik/src/components/MicButton.tsx`, `SpeakButton.tsx`, a hook `web/tb-nik/src/hooks/useAudioStatus.ts` (react-query, `staleTime` 30 s, `retry: false`, refetch on window focus, as `AskPanel` queries do), and a module `web/tb-nik/src/lib/voice.ts` (recorder, player queue, error mapping, the agent-voice setting). They match what exists:

- Buttons: the `Button` of `components/ui/button` with `variant="ghost"` and `size="icon-xs"` or `icon-sm`, the same as the Pin button in `AskPanel.tsx` and the remove buttons in `DecisionForm.tsx`; the `ActionButton` states (idle, loading with `aria-busy`, done with a tick and a spoken "role=status" word, `components/ActionButton.tsx`) are the model for the transcribing and "Added" states. Icons are lucide (`Mic`, `Square`, `Loader2`, `Volume2`, `VolumeX`, `Check`), as elsewhere.
- Placement: for a single-line control, `Field`'s `trailing` slot ("a small button inside the control on the right", `components/Field.tsx`); for a textarea, a `relative` wrapper with the button at the bottom right, the same idea. The level meter reuses the five-bar `MicLevel` of `features/meetings/components/PreJoin.tsx:12-34` (move it to `components/MicLevel.tsx`; it already has `role="meter"` and an `aria-label`).
- Tokens from `index.css`: idle uses `text-muted-foreground`, hover `bg-accent`; listening uses `--bad` on `--bad-soft` (the recording colour, with a slow pulse that stops under `useReducedMotion`); transcribing uses `--primary`; "Added" flashes `--ok` on `--ok-soft`; hints use `--warn`; focus ring `--ring`. Light and dark values exist at `index.css:15-48` and from line 59. State is never colour alone: each state has an icon and a word.

### 6.1 `MicButton`

Props: `screen` (audit id), `target` (a ref to the textarea or input, or `value` and `onInsert`), `context` (`question|decision|note|reason`), `caseId?`, `size`, `label?`.

- States (all true, driven by the browser and the request, never faked): `idle`; `asking` (permission prompt open); `listening` (shown only while `MediaRecorder.state === "recording"` and the track is live, with the level meter and elapsed seconds, "Listening 0:07 of 1:00"); `transcribing` (request in flight, "Transcribing"); `added` (a one-second tick, "Added, check it"); `error` (plain words below). The call to `/stt` starts only after recording stops.
- How: tap to start, tap again to stop (a toggle, so it works with a phone's thumb and with a screen reader). `getUserMedia({audio:{channelCount:1, echoCancellation:true, noiseSuppression:true}})`, `MediaRecorder` with the first supported of `audio/webm;codecs=opus`, `audio/webm`, `audio/mp4`, `audio/ogg;codecs=opus`; chunks are held in memory only (never IndexedDB, never disk); the stream's tracks are stopped as soon as recording ends, so the browser's microphone light goes off. Uploaded once at stop as multipart to `/api/tb/audio/stt`. Auto stop at 55 s with a count-down from 50 s ("5 seconds left"), matching the service's 60 s cap.
- The text goes in at the cursor: the selection range is remembered at the start; on arrival the text is inserted there (replacing a selected range), with one space added where needed, no change of capital letters; the cursor lands after it and the inserted range is briefly highlighted; it is a normal edit (undo works, `onChange` fires, so the Case File and meeting live strips behave as if typed). It is never sent: the Ask, Save or Send button remains a person's click. The line under the box says "Heard this. Check it before you send." (`05_board_agents.md` 4.3 wording, with "asking" in the agent boxes).
- Esc while listening or transcribing cancels and discards the audio (no request, or the reply is ignored); Esc otherwise does nothing new. A cancelled request is aborted with `AbortController`.
- Keyboard: the button is a real `button` with `aria-pressed` and `aria-keyshortcuts="Control+Alt+M"`. `Ctrl+Alt+M` toggles dictation in the focused box that has a mic (the meeting plan's shortcut table, `04_meeting_experience.md` 6.10, uses Ctrl+D, Ctrl+E, Ctrl+Alt+H, C, P, A, T and says plain shortcuts never fire in a text box; Ctrl+Alt+M is free and does not collide). Optional hold-Space push to talk stays off by default (as 04 6.10 says).
- Phone: a 44 px tap target; the same toggle; `audio/mp4` on Safari; iOS needs the tap to start capture (it is a tap anyway). If the page is hidden while recording (`visibilitychange`), recording stops and the audio is discarded with "Recording stopped because you left the page." (a locked screen would otherwise give a half clip). Insecure address: `navigator.mediaDevices` is undefined and `getUserMedia` throws `TypeError` outside https or localhost (https://developer.mozilla.org/en-US/docs/Web/API/MediaDevices/getUserMedia), so it says the connection message below.
- In the call: when the person is in the LiveKit call with the microphone on, dictation would be heard by the room. The proposed rule: the call microphone is muted while dictating and restored after (open question 3); the dictation stream is a separate `getUserMedia` capture.
- Errors, by exception name (MDN `getUserMedia` exceptions), in plain words:

| Cause | Text shown |
|---|---|
| `NotAllowedError` (denied, or Permissions Policy) | "The microphone is blocked. Allow the microphone for this site in the address bar, then try again." |
| `NotFoundError` | "No microphone found. Plug one in or choose one in your system settings." |
| `NotReadableError` | "The microphone is in use or not working. Close other apps that use it and try again." |
| `OverconstrainedError`, `AbortError`, other | "The microphone could not start. Try again." |
| `TypeError` or no `mediaDevices` (insecure address) | "The microphone needs a secure connection. Open Vaidyx through localhost or https." |
| no `MediaRecorder` | "This browser cannot record sound. You can type instead." |
| level flat for 3 s while listening | "No sound heard. Check that the right microphone is selected." |
| `no_speech` | "No speech heard. Try again closer to the microphone." |
| 413 `too_long` | "That was longer than one minute. Record in shorter parts." |
| 429 | "Too many voice requests. Wait a minute, or type." |
| 502, 503, network | "Voice is not available right now. You can type instead." |
| status `off` | the button is not drawn |
| status `down` | disabled, "Voice is not running on this server. You can type instead." |

### 6.2 `SpeakButton` and the agent-voice setting

Props: `ref` (a saved-statement reference) or `text` (on-screen text, mode (b)), `screen`, `label`, `autoplay?`.

- States: `idle` ("Read aloud"), `preparing` ("Preparing the voice", only until the first sentence audio is ready), `speaking` ("Reading aloud", the button becomes "Stop reading"), `error` ("Voice unavailable, text only"). The text being read can be highlighted sentence by sentence (the front end splits on the same rule it sends).
- Playback: one shared `HTMLAudioElement` with `playsInline`, used for the whole page. Sentences are fetched one by one from `/api/tb/audio/tts`, turned into `blob:` URLs with `URL.createObjectURL` (allowed by `media-src 'self' blob:`), queued and played in order; the next is fetched while the current plays. Stop aborts the fetches, pauses, and revokes the URLs. One voice at a time on the page: starting another stops the first.
- The user-gesture rule: audible playback is blocked until the user has interacted with the page, and `play()` then rejects with `NotAllowedError` (https://developer.mozilla.org/en-US/docs/Web/Media/Guides/Autoplay). A click on `SpeakButton` or on a talk-mode "Ask" counts; `play()` is called in the same handler stack (the first sentence may have to be fetched first, so the element is "primed" by playing a silent 0.1 s WAV inside the click, then reused). For speech that starts without a click (agent answers in the meeting), the page shows a one-time chip "Tap to allow agent voices" if `play()` rejects, and uses `navigator.getAutoplayPolicy("mediaelement")` where it exists (values `allowed`, `allowed-muted`, `disallowed`). The "Join now" click on the meeting's join page is a gesture, so a member who joined normally is usually allowed. The MDN page does not describe iOS beyond Safari's `playsinline`; test on a real iPhone (section 8).
- Agent voices (D2: spoken aloud by default, per-person mute): a switch "Agent voices" (`components/SwitchRow.tsx` exists) in the meeting's More menu ("Mute agent voices (for me)", `04_meeting_experience.md` 6.8) and a small speaker icon on the agent panel and on each agent tile. Stored per person in `localStorage` key `vx.agentVoice` (a per-viewer convenience; wrap reads and writes in try/catch, default on). Default for a member admitted as in the room is muted, to prevent echo with the room screen (`05_board_agents.md` section 5, point 2; owner to confirm). A muted device never fetches audio, so it costs nothing. The setting covers agents only: the "Read aloud" button on a Case File answer always works when pressed.
- Words: "Read aloud", "Stop reading", "Preparing the voice", "Reading aloud", "Voice unavailable, text only", "Agent voices on", "Agent voices muted", "Tap to allow agent voices", "Sources are on the screen." (spoken once at the end of an agent answer instead of reading references, `05_board_agents.md` section 5, point 3). No em dashes anywhere.
- Only the verified statements as shown are read (D1). Dates are read from the DD/MM/YYYY the screen shows (the normaliser, 4.4). Out-of-scope or "not found in the records" messages are read as shown.

## 7. Every screen where a microphone or a speaker goes

Single-line boxes for names, IDs (UHID, MRN, IP/OP numbers, ABHA), dates, numbers and values get **no** microphone: a mis-heard digit in an identifier or a dose is costly and the person types it faster (`Input` for "Responsible doctor", "By date", the HIS ID field `StepPatient.tsx:61`, the minutes box). Boxes that take sentences do.

| Screen | Component file (line) | Field | Mic or speaker | Phase |
|---|---|---|---|---|
| Ask about this patient (Case File) | `web/tb-nik/src/features/casefile/components/AskPanel.tsx` (`Textarea id="ask-input"`, form around it; thread `article` per answer) | the question, max 600 | Mic. Talk mode: tap the mic, speak, the text appears in the box and stays editable, "Heard this. Check it before you send.", then Ask. Speaker: "Read aloud" on every answer thread (its statements only); in talk mode the answer is read aloud automatically after it arrives (and "Stop reading" is shown). Same box on `GuidedCaseFilePage.tsx` and `CaseFilePage.tsx` since they render `AskPanel` | 4.4 |
| Question for the board (guided Case File) | `features/casefile/steps/QuestionStep.tsx:82` (`Textarea`, `aria-label="The question for the board"`, max 1000) | the question | Mic | 4.4 |
| Facts in the same step | `QuestionStep.tsx:52` (`Textarea`, comorbidity and patient preference rows) | free text, max 1000 | Mic | 4.4 |
| Question for the board (New Case File) | `features/newcase/StepLogistics.tsx:135` (`Textarea`, `boardQuestion`, max 600) | the question | Mic | 4.4 |
| Decision form (meeting and Case File) | `features/meetings/components/DecisionForm.tsx:70` `d-text` (max 4000), `:74` `d-rat` (rationale, 2000), the concern text `Input` at about `:109` (max 1000); the Phase 3 text fields (alternatives discussed, divergent views, communication plan, referral reasons) are added by item 3.1 with the same `MicButton` from the start | free text | Mic. `d-text` also drives the room screen's live strip; dictated text goes through the same `onChange`. A "Read back" speaker (mode (b), on-screen text) on `d-text` so the coordinator can hear what will be recorded. Not on `d-intent`, `d-resp`, `d-next`, `d-date`, `d-await`, `d-from`, `d-ref` (short, structured, or names) | 4.4 (Phase 3 fields: 3.1 uses it) |
| Reasons: not needed, correction | `features/casefile/components/ReviewPanel.tsx:58,75` (reason `Input`; "Give a short reason: it is recorded with your name."), `features/casefile/steps/CheckStep.tsx:29,45` (`Input` "Why", max 200), `features/casefile/steps/PreAuthStep.tsx:52-53` ("Why is it not needed?" and the fill-in `Input`, max 200) | reason text | Mic on the reason inputs (the sentence is the point); not on the "correct value" input in `CheckStep.tsx` (a value is typed) | 4.4 |
| Request notes | `features/requests/RequestCard.tsx:107-108` (`Textarea id=note-...`, "Note (optional)"), `features/meetings/components/CardDialog.tsx:35` (`Textarea id="card-note"`, max 500) | note | Mic | 4.4 |
| Specialty agent chat on the Case File | `features/casefile/components/HelpersPanel.tsx:205-210` (`Textarea id=helper-q-{role}`, max 1000; "Ask the {name} helper about the records") | question to one agent | Mic with "Heard this. Check it before asking."; Speaker: "Read aloud" on each agent answer | 4.4 (Phase 6.5 reshapes this area into "Specialty agents" and keeps the buttons) |
| Meeting question box (member) | `features/meetings/MemberViewPage.tsx:188` (`Textarea id="member-q"`, max 500, shown on the room screen with the name) | question to the board | Mic. A mic in a call: see the call-microphone rule in 6.1 | 4.4 (meetings), 5.x placement |
| Meeting: questions to the agents | the Agents panel in the one in-call shell (`04_meeting_experience.md` 6.9: each department has an "Ask" input, "mic button in Phase 4") and the agent tile (`05_board_agents.md` 4.3: tap the microphone on the agent's tile, state `listening` only while recording, 60 s expiry, then the editable box under the tile) | question to a chosen agent | Mic on the tile and in the panel; Speaker: agent answers spoken aloud by default on the room screen and in the call, per-person mute; "Stop" for the speaking agent | 6.1, 6.3 (uses the 4.3 components) |
| Meeting: agent answers in the Questions list | `QuestionsList` / answer cards (`MemberViewPage.tsx` around `:183-195`, `ControlView.tsx`) | none | Speaker: "Read aloud" per answer | 6.3 |
| Case summary and Points for review | `features/casefile/steps/SummaryStep.tsx`, `features/meetings/components/shared.tsx` (slides) | none (reading only) | Speaker: "Read aloud" on the summary and on Points for review, as the October note listed (Oct note line 244). Reads the text on screen via reference mode (b) of 5.1 or `summary` refs | 4.4 (optional) |
| Messages composer | not built (Phase 8 item 8.4, "a composer with voice") | message text | Mic only (dictation fills the composer; the person sends). Reading aloud received messages: not planned | 8.4 |
| People, names, IDs, dates | `StepPatient.tsx:61`, `DateInput`, `SearchBox` | structured | none | none |

## 8. The voice check (item 4.5)

### 8.1 `tumour_board/eval/audio_eval.py`

Follows the other eval scripts in `tumour_board/eval/` (a CLI, logs a JSON, called from `gate.sh <label>` at phase end; GPU work one job at a time, CLAUDE.md). Inputs: `tumour_board/eval/audio_sentences.json`, about 40 sentences in the system's own words, each with a `category` and `must_keep` tokens.

- Categories and examples (synthetic; no real patient data): histology with a date and a size; lab lines with three values and units ("Haemoglobin 11.8 g/dL, platelets 245,000 per microlitre"); staging ("mrT3b N1", "cT3 N2 M0"); dates (14/09/2026); receptor lines (ER positive, PR positive, HER2 equivocal, PD-L1 TPS 60%); Pre-Authorization and PM-JAY; Points for review (ECOG 1 versus 2); questions to the file and to the agents ("which department should clear the fitness"); an agent-style answer with a date lead-in.
- Indian drug and place names to include (they were the October weak points; Svarah's proper-name errors, Oct note lines 198-199): capecitabine, oxaliplatin, trastuzumab, pembrolizumab, osimertinib, letrozole, tamoxifen, paclitaxel, docetaxel, carboplatin, bevacizumab, temozolomide, imatinib; hospitals and places: Tata Memorial, Kidwai Memorial, Adyar, AIIMS, PGIMER, Thiruvananthapuram, Visakhapatnam, Bengaluru, Guwahati, Bhubaneswar, Coimbatore; Kathua, Rajouri, Poonch; first names such as Kavita, Venkatesh, Priya (Kavita was dropped by Kokoro in October).
- Flow: for each sentence call the service `/tts` (voice af_heart, and bf_emma for a second pass), take the WAV, send it to `/stt` (engine whisper; also `parakeet` on CPU, and `cohere` when present), compare with `jiwer`. Two WERs are logged, as the October note did: strict (lower-case and punctuation removal only) and equivalence-normalised (British and American spelling pairs, "245,000" and "245 thousand", "mrT3b N1" spacing), so a spelling convention does not hide a real error. Also: **exact-token score** (every number, unit, date and staging token in `must_keep` must appear exactly: this is the clinical metric), a silence and noise test (10 s of silence, 10 s of white noise, a 60 s tone: text must be empty, and over 60 s must give 413), latency p50 and p95 per engine **with both LLMs loaded** (the re-measure the Oct note asked for, lines 224-226), GPU memory before and after, and the CPU fallback path.
- Output: a JSON under the same results folder the other evals use, with per-category WER and the engine, plus a one-line summary for `gate_summary.py`. Pass marks to propose: strict WER at most 0.12 overall on the Kokoro set (October: 0.079 on six sentences), exact-token score at least 0.90, no text on silence or noise, no regression from the last logged run. These are thresholds on a synthetic set, not accuracy claims about real speech; the UI and reports make none.
- Optional `--real` mode: the 40 Svarah clips and the 16 Common Voice clips from the caches listed in 3.3 (Svarah is gated CC-BY-4.0, accepted by the owner on 15/10/2026; the clips are public research data and never leave this server), WER per engine must not rise (Oct note lines 234-235).

### 8.2 The Playwright check with a fake microphone

Browser: the repository's UI tests already launch Chromium with Playwright (`tumour_board/eval/ui_test.py:1142`, `p.chromium.launch(env=...)`; run with the pdf venv and `LD_LIBRARY_PATH`, CLAUDE.md "How to run"). Chromium flags (passed in `args`): `--use-fake-ui-for-media-stream` (accepts the permission prompt), `--use-fake-device-for-media-stream`, and `--use-file-for-fake-audio-capture=/abs/path/question.wav`. By default the file loops; adding `%noloop` after the path plays it once (a Chromium change, https://codereview.chromium.org/2043353002; a usage example with the three flags on one command line is in the W3C WebRTC mailing list, https://lists.w3.org/Archives/Public/public-webrtc-logs/2020Jan/0058.html). The flag takes a local file, not a URL, and Chrome has been fragile with unreadable files (https://codereview.chromium.org/1018293002). The exact WAV encoding is not documented officially (a Stack Overflow answer used 44.1 kHz stereo 16-bit): use **PCM 16-bit little-endian WAV, mono, 48,000 Hz** (Chrome's usual capture rate), with about 1 s of silence before and after the speech so the recording start does not cut a word, and confirm on the first run; if Chrome rejects it, fall back to 44.1 kHz stereo. The file is made by the audio service from a fixed sentence (Kokoro at 24 kHz, resampled with scipy to 48 kHz, written with `soundfile` as PCM_16), so no recording of a person is ever used.

Checks (each a named step in the script, with screenshots at 1366 x 768 and 390 x 844, light and dark, as plan item 9.1 requires):
1. Mocked service off (`/api/tb/audio/status` returns `enabled:false`): no mic or speaker drawn anywhere.
2. Service on: the Ask box shows the mic. Click it: "Listening" appears with the level meter moving (the fake device feeds the file); click again: "Transcribing", then the text appears in `#ask-input` containing the expected key words (at least 80 percent of tokens; exact for numbers), "Heard this. Check it before you send." is visible, and **no** `POST .../ask` has been made until the Ask button is clicked (a `page.route` counter).
3. Esc while listening: no `POST /api/tb/audio/stt` is made (counter stays 0) and the box is unchanged.
4. Permission errors: an init script replaces `navigator.mediaDevices.getUserMedia` with a rejection of `NotAllowedError`, then `NotFoundError`, `NotReadableError`; each shows its sentence from 6.1. A run without `mediaDevices` shows the secure-connection sentence.
5. Edit-then-send: type into the box after dictation and send; the request carries the edited text.
6. Speaker: `page.route` answers `/api/tb/audio/tts` with a small WAV; a spy on `HTMLMediaElement.prototype.play` sees one call per sentence in order; "Stop reading" aborts the rest; a rejected `play()` (`NotAllowedError`) shows "Tap to allow agent voices".
7. Rate and service errors: 429 and 503 replies show the plain messages and leave the typed text.
8. Real run (`tumour_board/eval/e2e_api.py --only audio`, as the October plan, with the real service up): the dictated sentence is transcribed through the app with the login and the audit line exists without any text in it (a grep of `org_audit.jsonl` for the sentence returns nothing).
9. A manual phone check (iPhone Safari, Android Chrome) over https for autoplay and recording; listed in `HOW_TO_TRY.md` of item 9.3, since headless Chromium cannot test iOS rules.

## 9. Open questions for the owner

1. Cohere Transcribe as a second engine: wire the `audio3` worker process in Phase 4, or leave it off (not installed in the audio venv; 4.7 GB more GPU; better on noisy Indian-accent clips, Oct note line 188)?
2. One voice (`af_heart`) for every agent, or a different cached voice per department (`bf_emma`, `am_michael`; only three voices are on disk, fetching more is a download)? One voice with the department named in the tile is simplest.
3. While a member in the call dictates a question, mute the call microphone for the length of the dictation and restore it after (proposed), or leave it as it is so the room may hear?
4. May text-to-speech read short text the person typed or dictated (a "Read back" button, up to 1,000 characters), or only saved answers, summaries and points by reference?
5. The in-memory two-minute cache of rendered sentences that lets every device in a meeting fetch the same audio (`05_board_agents.md` section 5, open point): allowed under "audio is never stored", or no cache at all?
6. Agent voices default: on for remote members and muted for members admitted as in the room (the echo rule); is that the right default?
7. A shared token between the app and the audio service on 127.0.0.1:7120 (other users on this server could otherwise call it): accept?
8. Keyboard: is `Ctrl+Alt+M` for dictation acceptable, and should hold-Space push to talk stay off?
9. Dictation only for sentence boxes (not names, IDs, dates, numbers): accepted as the rule in section 7?
10. Languages: English only in the first cut (Whisper and Cohere cover Hindi and others; the October note put them "later"); is that still right?
11. The voice evaluation may use the public Svarah and Common Voice clips already on disk (`--real`): confirm, as Svarah is gated.
12. Reading answers aloud on a shared room screen can be heard by people not in the meeting: should the coordinator have a one-click "Silence agent voices for everyone" (the plan gives each person their own mute only)?

## Sources

- Repository: `docs/tumour-board/audio_feature.md`; `docs/night-v3/PLAN.md:7-30,35-36,126-134`; `docs/night-v3/research/00_current_state.md` section 6; `05_board_agents.md` sections 4, 5, 7; `04_meeting_experience.md` sections 6.6 to 6.11; `tumour_board/pacs.py:263-300`; `routes/tumour_board_routes.py:94-111,125-170,179-215`; `tumour_board/api/common.py:80-108`; `tumour_board/api/helpers.py:10-11`; `tumour_board/org.py:259`; `tumour_board/store.py:220`; `core/middleware.py:86,96-137`; `~/vaidyx/start_vaidyx_app.sh`; `scripts/demo_services.sh`; `scripts/livekit.sh`; `tumour_board/config.py:25-27`; `web/tb-nik/src/components/ActionButton.tsx`, `Field.tsx`, `index.css`; the screen files named in section 7.
- Installed code read: `faster_whisper/transcribe.py`, `vad.py`, `audio.py` (1.2.1); `kokoro/pipeline.py` (0.9.4); `misaki/espeak.py`, `en.py` (0.9.4).
- Web (fetched 27/10/2026): https://github.com/SYSTRAN/faster-whisper ; https://huggingface.co/hexgrad/Kokoro-82M ; https://github.com/snakers4/silero-vad ; https://developer.mozilla.org/en-US/docs/Web/API/MediaRecorder/isTypeSupported_static ; https://developer.mozilla.org/en-US/docs/Web/API/MediaDevices/getUserMedia ; https://developer.mozilla.org/en-US/docs/Web/Media/Guides/Autoplay ; https://developer.mozilla.org/en-US/docs/Web/API/SpeechRecognition ; https://huggingface.co/istupakov/parakeet-tdt-0.6b-v2-onnx ; https://huggingface.co/CohereLabs/cohere-transcribe-03-2026 (README on disk) ; https://codereview.chromium.org/2043353002 ; https://lists.w3.org/Archives/Public/public-webrtc-logs/2020Jan/0058.html ; https://codereview.chromium.org/1018293002 .
- What the pages did not say: the faster-whisper page lists neither `initial_prompt` nor the VAD defaults (read from the installed source instead); the Kokoro card does not describe `split_pattern` or an espeak fallback (read from the installed source); the MDN MediaRecorder page has no per-browser table; the MDN autoplay page has no iOS detail; the Chromium fake-audio WAV format is not officially documented.
