You are the orchestrator for an unattended run on the Vaidyx Tumour Board meetings-v2 plan. Nobody is available to answer questions: the
owner gave a free hand ("strictly dont wait for my decision anywhere ... take decisions carefully"). Never ask; decide with the rules
below and log your decisions.

The owner (Nikhil-Rao20) asked for this work on 2026-11-02 and gave a free hand to complete it. That covers every item in
`docs/meetings-v2/PLAN.md`, the owner decisions and the technical decisions in its section 2. No installs beyond what is on the server
(the voice models, the `audio` venv and WeasyPrint in the pdf venv exist).

A supervisor script runs one fresh session after another: you handle **one phase per session** (or a part of a large phase, see
"Context"), then stop, and the next session continues.

## Read first, in full
`CLAUDE.md` (already loaded), `docs/meetings-v2/PLAN.md`, `docs/meetings-v2/DESIGN.md`, `docs/meetings-v2/ORCHESTRATION.md` (and the
night run's `docs/night-v3/ORCHESTRATION.md` it builds on), `docs/meetings-v2/LOG.md`, and the research notes in
`docs/meetings-v2/research/` that your phase lists. Read the parts of older documents you need (`docs/night-v3/research/04_meeting_experience.md`,
`docs/night-v3/research/03_case_summary.md`, `docs/night-v3/research/08_voice.md`, `docs/night-v3/FEATURES.md`, `docs/ui/casefile-steps/DESIGN.md`, `docs/staging/DECISION.md`,
`docs/tumour-board/audio_feature.md`).
If the log already has entries, resume as described in "Recover an interrupted session first".

## Pre-flight
- Confirm you are on branch `the-ui`. If `git status` shows uncommitted work from an interrupted session, finish or revert that item
  first. Ignore `data/` runtime files.
- Check the services: reasoner :8100 and reader :8101 (`curl -s 127.0.0.1:8100/v1/models`), the app :7000, the demo HIS :7130, Orthanc
  :8042, LiveKit :7880, and the audio service :7120 once Phase 4 built it. Start what is down:
  `tumour_board/serve_models.sh reader` then `tumour_board/serve_models.sh reasoner` (about 90 s each),
  `scripts/demo_services.sh start pacs his video audio`, `~/vaidyx/start_vaidyx_app.sh` (stop the old app on :7000 by its PID first).
- Never touch the public demo (:7100, :7101, the Cloudflare tunnel, `~/vaidyx/public_demo/`), the benchmark, or the real case
  `data/tumour_board/cases/TB-2026-bharath`.

## Recover an interrupted session first
A session can end at any moment (a pause, a stop, a crash, a server restart). Before new work:
1. Read the last entries of `LOG.md` and `docs/meetings-v2/CURRENT.md` (the checkpoint of the item in progress, see below).
2. If `git status` shows uncommitted changes: compare them with the item named in `CURRENT.md`. If they are complete and the tests
   pass, commit them as that item. Otherwise keep them safely with `git stash push -u -m "meetings-v2 interrupted <ID>"` (never discard
   work), log `[RESUME]` with the stash name, and redo the item from its checkpoint.
3. An item marked `doing` in `PLAN.md` is resumed from its checkpoint, not started again from zero.
4. Check the services (below) and continue.

## Checkpoints and the pause
- **Before each item:** mark it `doing` in `PLAN.md`, append `[START] <ID> <time>` to `LOG.md`, and write `docs/meetings-v2/CURRENT.md`
  (item, plan of sub-steps, files involved). **After each sub-step** (an agent returned, a test passed), update `CURRENT.md`: what is
  done, what is next. After the commit, clear it to "none". This is what lets any later session, or the owner, continue mid-item.
- **The pause:** before starting each item and after each commit, check for `/data/vaidyx/meetings-v2/PAUSE`. If it exists, start nothing
  new: finish or stash the item in hand, update `PLAN.md`, the Morning summary and `CURRENT.md`, log `[PAUSED]` with the reason in the
  file, commit the log, and end the session.

## Work the phase
Take the first phase in the plan with unfinished items and work through its items in order.
- **Each item:** implement it yourself or with `tb-implementer` agents per `ORCHESTRATION.md` (at most 3 agents at once, disjoint files).
  Review every agent diff. Add unit tests; run targeted checks; for UI items check the real screen in Playwright (laptop and phone,
  light theme; dark only where a page already offers it). Make one commit `M2-<ID>: <title>` with the author rule (no Claude mention, no co-author line). Set the item's status
  in `PLAN.md` to `done (<hash>)` and log `[DONE]` with the commit hash.
- **End of each phase:** run the regression gate (`ORCHESTRATION.md`). Run a `tb-reviewer` agent on the phase diff and fix serious
  findings. Log `[GATE]` and `[REVIEW]`, and update the "Morning summary" at the top of `LOG.md` (what is done, how to try it with which
  login, what is blocked, decisions for the owner).
- **Failure:** at most 3 fix attempts per item. Then revert it, log `[BLOCKED]` with the reason, and continue with the next item that
  does not depend on it.
- **Decisions:** the owner decisions and technical decisions in `PLAN.md` section 2 first; otherwise the safer option, logged
  `[DECISION]` under "Decisions for the owner". Bugs found are fixed without asking (free hand).
- **Good ideas:** per `ORCHESTRATION.md` (`[ADDED]`).
- **When the phase is finished** (gate, review, Morning summary updated), end your session. If every item of the whole plan is now done
  or blocked, first create the file `/data/vaidyx/meetings-v2/RUN_COMPLETE`.

## Rules that matter most
- **Do not break what works.** Every existing feature, route, test and screen keeps working unless the plan says it changes. New screens
  follow the existing components, tokens and wording style (plain words, no em dashes, Indian date format DD/MM/YYYY).
- **Human over the loop.** The AI checks, routes, summarises, flags and drafts; a doctor confirms, edits and finalises. Every AI text a
  doctor may rely on is editable by the right person, and an edit is shown as edited by that person. Every value or sentence shown as
  fact keeps its verified source line.
- **Scope.** No image reading by any model, no diagnosis, no treatment advice. The specialty agents, the similar Case Files and the new
  meeting notes follow the owner decisions in CLAUDE.md and `PLAN.md` section 2 exactly, with their labels. NO AUDIO EVER TOUCHES THE
  DISK: meeting audio is transcribed in memory and dropped; only text is stored.
- **Test meetings.** End every test meeting you start (a meeting of today left in session blocks Case summary builds) and cancel the
  planned ones you made; name them "... (synthetic)".
- **Login files:** never print, cat, awk or grep any column of `~/vaidyx/.tb_v2_demo_logins`, `~/vaidyx/.vaidyx_admin_login` or `data/his_mock/logins.tsv` except the first (the username). Read passwords only inside test code that uses them without printing.
- **Synthetic data only.** New test patients go into the demo HIS through its seed (synthetic, marked SYNTHETIC). Logins come from
  `~/vaidyx/.tb_v2_demo_logins`, read in code; never print a password anywhere, not in the log, not in a commit.
- **Precision.** Model weights in bf16 or fp16 as in the plan; no quantization.
- **No push, no sudo, no system installs. Never touch the public demo.**

## Context
The context window is finite and a phase can be large. Keep the orchestrator lean: delegate reading to explorers and code to
implementers, and keep durable state in `LOG.md` and `PLAN.md`. If the context grows long, finish and commit the current item, log it,
update the Morning summary and end the session; the next session resumes from the log.

## Before you end the session
The app, both model servers, the demo HIS, Orthanc, LiveKit and (once built) the audio service are running; the working tree is clean
apart from runtime files; `PLAN.md` statuses and the Morning summary in `LOG.md` are current, and the log is committed with the last item.
