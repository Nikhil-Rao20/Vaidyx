# Demo video: recording and editing

Scripts that record the platform live with Playwright and edit the footage into one narrated MP4. Version 1 (20 Oct 2026) is the full
walkthrough for the tech team, including the hospital-system (HIS) screens. **Version 2 is planned: see
[VAIDYX_CENTRIC.md](VAIDYX_CENTRIC.md)** (the owner's 20 Oct feedback; not recorded yet).

| Where | What |
|---|---|
| `rec/` (this folder) | the scripts, the source of truth |
| `/data/vaidyx/demo_video/raw/<run>/` | raw footage: one folder of JPEG frames per browser session, `frames.tsv` (time stamp, file), `marks.jsonl` (labelled moments), `state.json` (UHID, accessions, Case File id, meeting id). Run 1 is `run2` (11 GB) |
| `/data/vaidyx/demo_video/edit/` | plan, narration WAVs, overlay pages and PNGs, rendered chapters |
| `/data/vaidyx/demo_video/out/` | the final video `vaidyx-tb-demo.mp4` and `transcript-captions.srt` |

Nothing here is served over HTTP: the app's `static/` folder is also served by the public demo instance (:7100 behind the gate), so a
video placed there would be public.

## The scripts

| File | Does |
|---|---|
| `lib.cjs` | the recording kit: one browser per role, Chrome DevTools screencast at 1920 x 1080 (`--force-device-scale-factor=1.3333333` on a 1440 x 810 viewport), a drawn pointer with a click ripple, human-paced move / click / type / scroll, `mark()` for the edit. Passwords are read from the login files at run time and never printed; on screen the fields show dots |
| `his_chapters.cjs` | the hospital-system chapters: reception, OPD consultant, laboratory, radiologist, pathologist |
| `v_chapters.cjs` | the Vaidyx chapters: Case File, request (split screen), prepare, brief, meeting (test cameras, silent members, room screen), after, after2, admin, phone, site |
| `run.cjs` | runs chapters by name, keeps state between them |
| `make_cams.py` | synthetic test-camera feeds (initials and role, no faces), `.y4m` for Chromium's fake camera |
| `plan.py` | the edit plan: chapters, segments cut by marks, speed, layout, narration lines -> `edit/plan.json` |
| `tts.py` | narration with Kokoro-82M (`af_heart`, CPU), with a spoken-form table for words the voice drops (Vaidyx, UHID, ABHA, Ki-67...) |
| `maya_tts.py` | the same with Maya1 (maya-research/maya1, Apache-2.0). Works, but on the CPU it is about 19 times slower than real time; use it when the GPU has room |
| `edit.py` | `layout` (timeline, overlay pages), `render` (chapters in parallel), `final` (concat, loudness, chapters) |
| `overlays.cjs` | overlay pages (title, agenda, chapter cards, captions, labels, speed tags) -> PNGs |
| `frame_at.py` | the frame shown at a mark, for checking footage |

## Run it

```bash
cd ~/vaidyx/Vaidyx/web/tb-nik          # for the Playwright module
export PATH=/data/vaidyx/tools/node/current/bin:$PATH NODE_PATH=$PWD/node_modules LD_LIBRARY_PATH=/data/vaidyx/venv/pdf/lib
R=~/vaidyx/Vaidyx/docs/demo-video/rec
DEMO_RUN=run3 node $R/run.cjs reception opd lab radiology pathology casefile request prepare brief meeting after after2 admin phone site
/data/vaidyx/venv/app/bin/python $R/plan.py
HF_HUB_OFFLINE=1 CUDA_VISIBLE_DEVICES= /data/vaidyx/venv/audio/bin/python -I $R/tts.py
/data/vaidyx/venv/pdf/bin/python $R/edit.py layout && node $R/overlays.cjs
/data/vaidyx/venv/pdf/bin/python $R/edit.py render && /data/vaidyx/venv/pdf/bin/python $R/edit.py final
```

Recording takes about 50 minutes (the summary and the briefs are real model work); the edit about 6 minutes on 64 cores. Each chapter
can run on its own; `state.json` carries the patient and the Case File between them.

## Rules the recording follows

- Synthetic patients only. The real case is never opened; the demo logins do not list it.
- Every sign-in happens on screen; the password field shows dots; no password reaches a log or a file.
- Meeting video uses synthetic test cameras, never a real camera.
- Waits for the models are sped up and marked "N× faster" on screen; nothing is faked.
- What a recording creates stays on :7000 and the mock hospital (run 1: Case File TB-2026-0002, meeting S20261020-efa8, HIS patients
  VXH/26/004328 and VXH/26/004329). Clean up only with the owner's go.
