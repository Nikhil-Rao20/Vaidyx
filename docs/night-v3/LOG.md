# Night-v3 run log

## Morning summary
_Updated by the orchestrator at the end of every phase._

| | |
|---|---|
| Phases done | none yet |
| Last commit | |
| Blocked | |
| Decisions for the owner | |
| How to try | see the phase entries below (logins by username only) |

## Decisions for the owner
_Judgement calls taken during the run (`[DECISION]`), newest last._

## Parking lot
_Ideas not done tonight._

## Entries

### Phase 0 (session 1, 27 Oct 2026)
- `[START]` 0.1 2026-10-27 00:52 Pre-flight: branch night-v3, tree clean, reasoner :8100 and reader :8101 up, app :7000, demo HIS :7130, Orthanc :8042, LiveKit :7880 up; audio :7120 not built yet (Phase 4). Backup of data/tumour_board (without the real case) and data/his_mock started to /data/vaidyx/night-v3/backup/. Unit-test gate started.
- `[START]` 0.2 2026-10-27 00:57 research agents (GI and thoracic; gynae, urology, head and neck, thyroid; then haematology, paediatric, sarcoma, CNS when a lane frees up), each writing one part file under docs/night-v3/research/. The unit-test gate at the start: 2964 passed, 9 deselected (test_agents_live), 3 min 06 s. The backup needed tar (no rsync on this server).
- `[DECISION]` 2026-10-27 00:57 Research agents write their note files themselves (general-purpose agents on Sonnet with the explorer brief) instead of returning the whole note as text: keeps the orchestrator's context lean (ORCHESTRATION.md "Lean orchestrator context"); the orchestrator reads and checks each note before the item is marked done.
- `[GATE]` 2026-10-27 01:01 Phase 0 start (the baseline the later phases compare with): unit tests 2964 passed, 9 deselected (test_agents_live), 3 min 06 s; `tsc -b --noEmit` clean; `vite build` clean and identical to the committed static/tb-nik; mocked screenshot tests 58 passed, 20 skipped (the real-mode spec skips in mock mode), 3.1 min. Logs under /data/vaidyx/night-v3/gate/phase0_*.log. Backup done 00:58: /data/vaidyx/night-v3/backup/tumour_board (1.3G, the real case excluded) and his_mock (2.2G).
- `[DONE]` 0.3 2026-10-27 01:25 `docs/night-v3/research/02_board_decision_dataset.md` (341 lines): NHS England 2020 (p.12 minimum core data), Victoria 2018 Part 2 (live data entry fields, Appendix 3 and 4), PM-JAY HBP 2.2 (3.9, 3.23, 3.24: no decision form defined, only that a board decides and pre-authorization is per step), the NCG VTB template (an input form; no outcome fields), CRUK 2017, Greater Manchester MDT Standards v3 2023; ACS CoC 2.5 and the ESMO molecular board paper (Westphalen 2025) read from secondary sources only (marked unverified in the note). Today's record mapped: eight mismatches found (outcome labels differ between postboard and meetings; no "noted" outcome in postboard; UI and backend limits differ on five fields; intent flag fires wrongly; seven fields accepted but never asked; "missing actions" flag on every decision; versions only for flag corrections; VTB export without the board record). Proposal: 36 fields in six steps, only outcome and decision text required to save, every present field kept, 14 backend rules. Ten open questions for the owner (in the note, section 7). Commit hash in the next line.
