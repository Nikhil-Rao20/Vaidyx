# Ask PubMed: how to try it (3 Nov 2026)

Open `http://localhost:7000/tb-nik` through your usual SSH tunnel. Logins by username (passwords in `~/vaidyx/.tb_v2_demo_logins`).

| Where | Try |
|---|---|
| Case File | Sign in as `tb-gynonc-doc`, open Rekha Sharma `TB-2026-0011`, press **Ask about this patient**. Two tabs: **This patient's records** and **PubMed**. In PubMed ask "What did trials report about induction chemotherapy before chemoradiation in locally advanced cervical cancer?". Watch the steps, open a numbered quote chip (the exact words, the section, Open on PubMed), look at the papers (cited, read, not read), **Save** one to the Published list, change the search words or the years and **Search again**. |
| The offer | In **This patient's records** ask a general question, for example "What did trials report about pembrolizumab with chemoradiotherapy in locally advanced cervical cancer?". The records have no answer, so it offers **Ask PubMed?**: one click asks it. |
| A refused question | In PubMed ask "Should we give her chemoradiation?": refused with the reason and Change the question. |
| Home | **PubMed** in the top bar (the Dock on the phone) and the **Ask PubMed** card on Case Files: general questions with no patient, your own history. |
| Meeting | As `tb-mdt` start a meeting with a Case File on the floor: **PubMed** on the meeting bar opens the Ask PubMed panel for that Case File. |
| Voice | The mic fills the question box; the speaker button reads an answer aloud ("From PubMed. ..."). |

Who may use it: doctors, residents, the MDT Coordinator and outside experts (Home); in a Case File the treating team and the coordinator,
and the admitted members of a running meeting for the Case File on the floor. Admin-only and department-admin-only logins do not see it.
Save to Published: the owning department's consultants. Checks: `docs/pubmed-ask/PROOF.md`, `LIVE_EVAL.md`, the live screen run
`docs/pubmed-ask/tools/live_screens.mjs` (screenshots in /data/vaidyx/pubmed-ask/shots), the mocked shots `e2e/shots/pubmed.spec.ts`.
