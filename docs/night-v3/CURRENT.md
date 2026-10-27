# The item in progress (checkpoint)

Items 2.6, 2.7 and 2.8 (Phase 2), started 27 Oct 2026 07:05, three agents at once (briefs under /data/vaidyx/night-v3/runs/briefs/: 2.6_hn_thyroid.md (Sonnet), 2.7_blood.md (Opus; OCR of the adult haematolymphoid flow charts and the `ocr` branch of test_protocol_schema.py), 2.8_paed_sarcoma_cns.md (Sonnet; EANO 2021 download and licence check)). Items 2.1 to 2.5 are committed (0ea10f2, 43a10be, b111c9b, 9c6f1cf, 1dd5fd8).

Sub-steps:
1. [x] (returned 07:50; thyroid parked by the orchestrator: NICE terms do not allow it outside the UK) 2.6 larynx.json, thyroid.json (NICE NG230 text under guidelines/nice/, licence logged), test_phase2_hn_thyroid.py
2. [x] (returned 07:45; mrd_leukaemia moved to optional) 2.7 lymphoma.json, leukaemia.json, test_phase2_blood.py, the ocr branch in test_protocol_schema.py
3. [x] (returned 07:45; nephrectomy histopathology moved to optional; bone sarcoma label widened) 2.8 wilms, retinoblastoma, bone_sarcoma, soft_tissue_sarcoma, brain_cns (EANO under guidelines/eano/ with LICENCE.txt), test_phase2_paed_sarcoma_cns.py
4. [ ] (08:20: the full suite is rerunning; then the commits) Review each diff, run the schema test and the full suite, commit N3-2.6, N3-2.7, N3-2.8 (each with its log entry).

Then: 2.9 (generic_haem + the picker's solid-or-blood path), 2.10 (wiring: cancers.ts with colon/rectum and adult/child kidney choices, packs, the mismatch warning, glance), 2.12 (dose references), 2.11 (synthetic patients in the demo HIS, real-model run, screenshots), then the gate, the review and the Morning summary.

08:20: 2.9 backend done by the orchestrator (generic_haem.json; protocol.GENERIC_IDS; his_case uses it; tests green). Launched three agents: 2.10 wiring (brief 2.10_wiring.md, also the picker part of 2.9), 2.11 seed (brief 2.11_synthetic_patients.md; the orchestrator rebuilds the mock, creates the Case Files and runs the models after), 2.12 dose references (brief 2.12_dose_references.md).
