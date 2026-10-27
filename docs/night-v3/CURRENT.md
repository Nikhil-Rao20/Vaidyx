# The item in progress (checkpoint)

Items 2.6, 2.7 and 2.8 (Phase 2), started 27 Oct 2026 07:05, three agents at once (briefs under /data/vaidyx/night-v3/runs/briefs/: 2.6_hn_thyroid.md (Sonnet), 2.7_blood.md (Opus; OCR of the adult haematolymphoid flow charts and the `ocr` branch of test_protocol_schema.py), 2.8_paed_sarcoma_cns.md (Sonnet; EANO 2021 download and licence check)). Items 2.1 to 2.5 are committed (0ea10f2, 43a10be, b111c9b, 9c6f1cf, 1dd5fd8).

Sub-steps:
1. [x] (returned 07:50; thyroid parked by the orchestrator: NICE terms do not allow it outside the UK) 2.6 larynx.json, thyroid.json (NICE NG230 text under guidelines/nice/, licence logged), test_phase2_hn_thyroid.py
2. [x] (returned 07:45; mrd_leukaemia moved to optional) 2.7 lymphoma.json, leukaemia.json, test_phase2_blood.py, the ocr branch in test_protocol_schema.py
3. [x] (returned 07:45; nephrectomy histopathology moved to optional; bone sarcoma label widened) 2.8 wilms, retinoblastoma, bone_sarcoma, soft_tissue_sarcoma, brain_cns (EANO under guidelines/eano/ with LICENCE.txt), test_phase2_paed_sarcoma_cns.py
4. [ ] (the full suite reran green, 3606 passed; the commits followed) Review each diff, run the schema test and the full suite, commit N3-2.6, N3-2.7, N3-2.8 (each with its log entry).

Then: 2.9 (generic_haem + the picker's solid-or-blood path), 2.10 (wiring: cancers.ts with colon/rectum and adult/child kidney choices, packs, the mismatch warning, glance), 2.12 (dose references), 2.11 (synthetic patients in the demo HIS, real-model run, screenshots), then the gate, the review and the Morning summary.

06:35 (server time; the earlier guesses in this file were ahead): 2.9 backend done by the orchestrator (generic_haem.json; protocol.GENERIC_IDS; his_case uses it; tests green). Launched three agents: 2.10 wiring (brief 2.10_wiring.md, also the picker part of 2.9), 2.11 seed (brief 2.11_synthetic_patients.md; the orchestrator rebuilds the mock, creates the Case Files and runs the models after), 2.12 dose references (brief 2.12_dose_references.md).

06:55 (server time): items 2.6 to 2.10 and 2.12 committed (9298d82, 0a5f4c5, c9828c6, d5f96c4, 58a35c6, 55a8f95), the 2.11 seed committed (6201c34). In progress: the 2.11 end-to-end run: the app restarted on the new backend (06:58), data/his_mock backed up to /data/vaidyx/night-v3/backup/his_mock.before-2.11 and the mock rebuilt from the new seed (python -m his_mock.build --upload, running), then his_mock/serve.sh restart, then `OUT=/data/vaidyx/night-v3/shots/phase2 node docs/night-v3/tools/phase2_real_check.mjs` (creates the four Case Files as tb-mdt, waits for the model jobs, lists gaps and glance values, screenshots). The tb-reviewer runs on 5552bb3..HEAD in the background. After the e2e: log [DONE] 2.11, run the gate (tumour_board/eval/gate.sh night-v3-phase2 --v2 --skip-ui), fix serious review findings, update the Morning summary, commit the log.

07:05 (server time): the four Case Files exist (TB-2026-0005 ovary, 0006 prostate, 0007 stomach, 0008 lymphoma); their model jobs finished (8, 8, 9 and 12 documents); the e2e script is reading the steps and taking the screenshots; the two colliding PACS studies of the new patients were deleted and re-uploaded (verify OK). Next: read the e2e notes, log [DONE] 2.11, run the gate, apply the reviewer's serious findings, Morning summary, commit the log.
