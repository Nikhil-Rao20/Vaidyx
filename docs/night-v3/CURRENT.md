# The item in progress (checkpoint)

Item: 9.2 Whole-run review (Phase 9, session 12; 9.1 committed 14:47).

State: four reviews done (runs/briefs/9-review-A.md: 1 serious, 5 important; B: 0 serious, 7 important; C: 3 serious, 7 important; D: 2 serious, 6 important). Fixers running in the background on disjoint files: A (brief 9.2_fixes_A.md, launched 14:40), B (9.2_fixes_B.md, 14:41), D (9.2_fixes_D.md, 14:46). C (9.2_fixes_C.md, the website) launches when A finishes (both touch the messages feature and mock).

Next: read each fixer's report and diff; run the touched tests; when all four are in: full unit suite, tsc, build, the mocked suite, restart the app (:7000), the real checks (phase8_real_check.mjs for messages, phase6_real_check.mjs for agents, a treating and coordinator subset of baseline_shots.sh), the security audit again; commit N3-9.2 (also fill 9.1's hash in PLAN.md); log [REVIEW] and [DONE] 9.2; then 9.3 HOW_TO_TRY.md, 9.4, 9.5.
