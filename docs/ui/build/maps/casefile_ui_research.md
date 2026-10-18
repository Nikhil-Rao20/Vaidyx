# Case File UI research: next-step actions and page layout

17 Oct 2026. Research only, no repo changed.

- **"Not verified"** means I saw it only in a search snippet, a secondary write-up or vendor material, not in a primary page I could open.
- **Pages I read in full:** NN/g, Baymard, GOV.UK, NHS, the GitHub changelog, Stripe docs, UNMC, Blecker 2019, MedWISE 2016, AWARE 2010, Goddard 2012 and the 2022 care-gap paper.
- **Taken from abstracts seen in search results:** all other paper figures (Senathirajah 2020, LifeLines, HARVEST, Lamb 2013, Hammer 2020, van der Sijs, Ancker, Kim 2025).

## Summary

- **Seven tabs work against this task.**
  - NN/g: tabs are wrong when users must compare across them.
  - Baymard: users repeatedly missed content hidden in tabs. On desktop it recommends expanded sections with a sticky index.
  - In lab studies, one composed clinical display cut screen changes from 43 to 14 (Senathirajah 2020). It also cut the share of sessions where users re-viewed the same data, from 72.6% to 14.6% (2016).
- **Q1: use a ladder, not one pattern.**
  - Small reversible steps: act inline on the row, with Undo rather than a confirm dialog.
  - Steps that need evidence: open a non-modal right inspector.
  - Final, irreversible sign-off: a modal.
  - Jump-and-highlight: only for "show me in the document".
  - Ctrl+K: an extra, never the only route.
- **After any action, keep the doctor's place.**
  - Update the row in place, and keep scroll position and focus.
  - The inspector moves on to the next item, as Gmail auto-advance and Linear J/K do.
- **Q2: the best simple frame for 1366 to 1920 px** has three parts:
  - a slim patient strip,
  - one scrolling work column,
  - a right inspector that opens on demand.

  This is Material's "supporting pane" layout plus Epic Storyboard's always-visible patient summary.
- **Status words: copy GOV.UK task lists.** Use few statuses, written as adjectives, and include "Cannot start yet". Show completed items as plain text and make the whole row clickable.
- **Say "not found in the file", not "missing".** An Epic care-gap report misclassified 18% of patients flagged as overdue. Often the result existed but sat outside the structured fields.
- **Flags must be few and quiet.**
  - Clinicians override drug alerts 49 to 96% of the time.
  - Each extra reminder per encounter cut acceptance by 30%.
  - But a quiet sidebar alert was missed by 7 of 12 clinicians.
  - So flags are passive by default, and only what blocks the board date escalates.
- **Supervising "over the loop" needs evidence beside every AI value.**
  - Wrong decision-support advice is followed more often (risk ratio 1.26).
  - Showing sources reduced reliance on wrong LLM answers.
  - Best invented concept: the "Fill-in summary", where the board summary is itself the checklist.

## Q1. What should happen when the doctor acts on a next step

| Pattern | Works when | Fails when | Evidence and real examples |
|---|---|---|---|
| (a) Inline expansion in place | Short, reversible, one-item steps where the row already holds everything needed. Examples: confirm a date that is already quoted, send a prepared request | Content is long or needs the source. Opening it pushes the page down and loses the doctor's place | GitHub merge box: checks listed in place, failing first. GOV.UK check answers: after a change, return to the same page. NN/g: in-page boxes for less critical content. Collapsed content is easy to miss |
| (b) Side sheet / inspector (right, non-modal) | The doctor needs the evidence and the case visible together, or works through several items in a row | It is wider than about 40% of a 1366 px screen. It has a scrim (modal). It grows its own navigation | Material 3: standard side sheets sit beside content on large screens. Apple HIG: the inspector follows the selection. NN/g: non-modal is "less offensive". Examples: Linear peek; Epic In Basket (messages open right or below, with QuickActions and Done); Abridge Linked Evidence side panel; Stripe Apps drawer, bound to the page's object |
| (c) Modal dialog | Irreversible, high-stakes steps: sign and lock the decision record, or remove a case from the board list | Used for routine steps, or when the decision needs information the modal hides. Frequent use breeds habitual clicking | NN/g: modals "cause users to forget what they were doing". Confirmations lose value when overused, so prefer Undo. Blecker 2019: an interruptive alert was noticed but "annoying" |
| (d) Jump and highlight | "Show me where": open the exact report line or section that a gap refers to | Used as the main action route. The doctor lands far away, Back behaves oddly, and the place is lost | Cerner Workflow MPage navigator jumps to stacked components (hospital guides). NotebookLM citation jumps to the highlighted passage (secondary sources). Nielsen: within-page links confuse |
| (e) Command palette (Ctrl+K) | Frequent keyboard users repeating actions they already know | New or occasional users. The palette is invisible, so it cannot be the only way | Linear and Superhuman use Cmd+K. NN/g: hidden navigation hurts discoverability, more on desktop. No palette usability study found (not verified) |

**Recommendation: act where you see it, review beside it, sign in a modal.**

1. **One verb button per row.** Each next step has one button that does the routine part (for example "Send 2 requests").
   - The row changes in place to "Sent 15 Oct, waiting on Radiology".
   - An Undo toast stays up for about 10 seconds, and there is no confirmation dialog.
   - Why: NN/g prefers Undo to confirmations for reversible steps. Microsoft's human-AI guidelines G8 and G9 ask for quick dismissal and correction.
2. **"Review" opens the right inspector.** It is non-modal: about 420 px wide at 1366, 520 px at 1920, and the page stays scrollable behind it.
   - It shows the draft beside the verbatim source quote, with three buttons: Approve, Edit, Not needed.
   - After Approve, it moves to the next item that needs the doctor.
   - Why: Material, Apple and NN/g all favour non-modal panels. Gmail auto-advance moves to the next item after an action. GitHub "Add suggestion to batch" shows people approving many small items as one act.
3. **Modals only for two steps:** "Sign and lock decision record" and "Remove from board list". Each modal's buttons name the outcome.
4. **"Show in document" lives inside the inspector.** It scrolls the source to the quote, highlights it, and offers a "Back to case" chip. The main page never scrolls by itself.
5. **Ctrl+K and J/K are optional extras** for residents who use the tool all day.

## Q2. Layouts that replace seven tabs

On a 1366x768 laptop, about 1366x650 px is usable (my estimate). Three full columns fit only at 1920.

### 1. Two-pane: patient column plus work area

A fixed left column (about 240 px) always shows who the patient is and where the case stands.

- **Examples:** Epic Storyboard, a vertical left column that replaced the old header. UNMC piloted it with 180+ users; one said they "no longer need to click around the chart". NAVIFY patient summary (layout not verified).
- **Strengths:** identity and the board date are always in view, which also guards against working on the wrong patient.
- **Weaknesses:** it costs width, and it does not organise the work area by itself. One doctor took "three days to adjust".
- **Evidence:** hospital reports only. No study found (not verified).

```
+----------------------+------------------------------------------------------------+
| R. Kumar, M, 58      |  Work area                                                 |
| UHID 10-2231         |                                                            |
| Referral: tongue     |  (requests, documents, summary, decision: whatever the     |
|  ulcer (as written)  |   doctor has open)                                         |
| Board: Thu 24 Oct    |                                                            |
| Ready 14 of 17       |                                                            |
| Waiting: Radiology   |                                                            |
| Needs you: 2         |                                                            |
+----------------------+------------------------------------------------------------+
```

### 2. Three-pane, mail-like: list, item, inspector

A list of items (gaps, requests, documents), the selected item, and an action pane.

- **Examples:** Gmail and Outlook reading panes, Epic In Basket, Linear, Superhuman split inbox.
- **Strengths:** fast to work through items in a row, by keyboard.
- **Weaknesses:** cramped at 1366. It turns the case into messages, so the overall picture is lost.
- **Evidence:** Material 3 list-detail guidance: give the list a fixed width and let the detail flex. Apple advises at most two sidebar levels.

```
+-------------------+--------------------------------+-------------------------------+
| ITEMS (9)         | CECT neck report               | Request to Radiology          |
| > CECT neck  gap  | Not found in the file          | "Please share the CECT neck   |
|   HPE        ok   | Needed by: board checklist     |  report for UHID 10-2231"     |
|   LFT        gap  | Mentioned: OPD note 03 Oct     |                               |
|   Consent    ok   | "CECT neck advised"  (q)       | [Send]  [Edit]  [Not needed]  |
|   History    new  |                                |                               |
|   ...             | j / k to move                  | Drafted by assistant 08:12    |
+-------------------+--------------------------------+-------------------------------+
```

### 3. Checklist rail (task list)

A left rail lists sections as tasks, each with a status. Clicking one opens it in the work area.

- **Examples:** GOV.UK and NHS task lists, GitHub merge box, Vercel deployment checks (required checks block promotion), Stripe account checklist.
- **Strengths:** "what is left" is very clear, sections can be done in any order, and the status wording is well researched.
- **Weaknesses:** GOV.UK says not to use it to show answers. The number of states creeps up; one government team needed more than two.
- **Evidence:** in 2023, GOV.UK users kept clicking the status tags, so the whole row became the link and "Completed" became plain text.

```
+-----------------------------+------------------------------------------------------+
| Case File        14 of 17   |  Pathology                                           |
|                             |  HPE report        final, signed        (q)          |
| Identity         Ready      |  Biopsy date       12 Oct 2026          (q)          |
| Pathology        Ready      |  Block ID          26-H-4411            (q)          |
| Imaging          Waiting    |                                                      |
| Labs             1 to do    |                                                      |
| Specialty briefs 2 to check |                                                      |
| Board decision   Cannot     |                                                      |
|                  start yet  |                                                      |
+-----------------------------+------------------------------------------------------+
```

### 4. Dated timeline spine

Outpatient visits and admissions are nodes on a vertical spine, newest at the top. Reports, requests and replies hang off the nodes.

- **Examples:** LifeLines (University of Maryland), HARVEST (Columbia, built into its EHR), NAVIFY Tumor Board timeline screen (vendor).
- **Strengths:** matches how records arrive. Loop-backs are natural, because a new report is simply a new node.
- **Weaknesses:** weak at showing gaps unless they are drawn in. Long histories mean long scrolling. HARVEST gave no speed gain.
- **Evidence:** in a 36-person study, LifeLines beat tables on speed and on later recall (p<.004). HARVEST users reported high satisfaction.

```
 today 17 Oct ------o
                    |  Radiology reply 16 Oct: "report by 18 Oct"        new
 IP 10 to 13 Oct ---o  Biopsy 12 Oct, left lateral tongue               (q)
                    |   +-- HPE report 14 Oct, final, signed             (q)
                    |   +-- Discharge summary 13 Oct                     (q)
 OPD 03 Oct --------o  "CECT neck advised"                               (q)
                    |   +-- CECT neck report .... not found in the file [Request]
 OPD 28 Sep --------o  First visit, referral letter, CBC                 (q)
```

### 5. Dashboard of cards with progressive disclosure

One card per domain, each showing 2 to 4 values and a status. A card expands in place, at most two levels deep.

- **Examples:** MedWISE (a research EHR built from widgets), AWARE ICU dashboard (Mayo, sold by Philips).
- **Strengths:** an overview at a glance.
- **Weaknesses:** NN/g finds cards less scannable than lists, weak at showing order, and poor for comparison. Expanding a card reflows the grid, so the page jumps.
- **Evidence:** AWARE pilot with 6 providers: task load (NASA-TLX) fell from 47 to 26, errors from 24 to 13, and tasks took about half the time.

```
+----------------------+ +----------------------+ +----------------------+
| Pathology     Ready  | | Imaging     Waiting  | | Labs         1 gap   |
| HPE final, signed    | | CECT neck: not found | | CBC 28 Sep    (q)    |
| Biopsy 12 Oct  (q)   | | Requested 15 Oct     | | LFT: not found       |
| [open]               | | [remind]             | | [ask lab]            |
+----------------------+ +----------------------+ +----------------------+
+----------------------+ +----------------------+ +----------------------+
| Identity      Ready  | | Specialty briefs 6   | | Board decision       |
| Name, UHID match     | | 2 need your approval | | Cannot start yet     |
+----------------------+ +----------------------+ +----------------------+
```

### 6. Split: "not ready" and "ready"

Two columns: gaps with their actions on the left, verified items folded on the right.

- **Examples:**
  - GitHub merge box (failing checks first) and Vercel required checks.
  - Epic Health Maintenance shows "Overdue: never done" (one hospital's note).
  - NAVIFY lets teams reschedule a case when information is missing (vendor).
- **Strengths:** answers "can this go to the board?" at once.
- **Weaknesses:** related items get split (biopsy date ready, HPE report pending). The "ready" column gets skimmed and trusted, which is automation bias.
- **Evidence:** the care-gap report above misclassified 18%. Lamb 2013: an MDT checklist plus training raised the share of cases that reached a decision from 82.2% to 92.7%.

```
+------------------------------------------+-------------------------------------------+
| NOT READY (3)                            | READY (14)                       [expand] |
| CECT neck report   not found in the file | HPE report, final, signed      (q)        |
|   Requested 15 Oct, waiting on Radiology | Biopsy date 12 Oct             (q)        |
|   [Remind]                               | Name and UHID match on 9 of 9 documents   |
| LFT   not found   [Ask lab] [Not needed] | CBC 28 Sep                     (q)        |
| Resident history draft   [Review]        | ... 10 more                               |
+------------------------------------------+-------------------------------------------+
```

### 7. Document viewer with evidence pane

Extracted values on the left. The source page on the right, with the quote highlighted. Clicking a value scrolls the source to it.

- **Examples:**
  - Abridge Linked Evidence: highlight note text and the transcript lights up in a side panel, with audio.
  - NotebookLM citations.
  - Hebbia Matrix: each cell links to its source passage (secondary source).
  - Harvey (not verified).
- **Strengths:** directly serves the verbatim-quote rule.
- **Weaknesses:** a readable source page needs about 600 px, scanned PDFs are hard, and it is heavy for routine items. It works best as the inspector, not the home page.
- **Evidence:**
  - Kim et al., CHI 2025 (308 people): showing sources reduced reliance on wrong answers.
  - Goddard 2012: presenting information instead of commands is linked to less automation bias.

```
+---------------------------------------+-----------------------------------------------+
| EXTRACTED                             | SOURCE: HPE report 14 Oct, page 1 of 2        |
| Biopsy date    12 Oct 2026      (1)   |                                               |
| Specimen       left lateral tongue (2)|  Specimen: punch biopsy from [left lateral    |
| Report status  final, signed    (3)   |  border of tongue] (2) ...                    |
|                                       |  Date of biopsy: [12/10/2026] (1)             |
| Click a value to see its source       |                                               |
| [Approve section]  [Wrong value]      |  Signed: pathologist, 14/10/2026 (3)          |
+---------------------------------------+-----------------------------------------------+
```

### 8. One long page with a sticky section index

All sections in a fixed order on one page. A sticky index on the left shows each section's status.

- **Examples:** Cerner Workflow MPage, whose left navigator jumps to stacked components that can be reordered and collapsed (hospital guides). Baymard's "expanded sections plus sticky table of contents".
- **Strengths:** nothing is hidden, Ctrl+F works, and it prints well.
- **Weaknesses:** it is today's long page with a better index. In-page jumps can disorient.
- **Evidence:** Baymard: on desktop, expanded sections matched how users expect to find content.

```
+------------------+-------------------------------------------------------------------+
| ON THIS PAGE     |  1 Ready for board?   14 of 17                                    |
| 1 Ready? 14/17   |    rows ...                                                       |
| 2 Documents (23) |  2 Documents by visit: OPD 28 Sep | OPD 03 Oct | IP 10 to 13 Oct  |
| 3 Briefs  2 new  |  3 Specialty briefs                                               |
| 4 Summary        |    ...                                                            |
| 5 Board decision |  (index stays fixed; the current section is highlighted)          |
| 6 History        |                                                                   |
+------------------+-------------------------------------------------------------------+
```

### Supporting guidance

- **Tabs or one page.** NN/g: use tabs only when users will not need content from two tabs at once, and "the fewer tabs, the better". Keep at most one two-way view switch (Summary or Timeline). Never put workflow steps in tabs.
- **Keeping place.**
  - Re-render only the changed row, and keep scroll position and focus. NN/g suggests restoring position within a session, for 30 to 60 minutes.
  - When a loop-back adds a new report, do not move the page. Show a "1 new since you looked" indicator with a "Show" link (NN/g's rule for frequently changing content).
- **Showing what is missing.**
  - Use at most four statuses: Ready, Not found in the file, Waiting on (department), Cannot start yet.
  - Put each status on its own row: NN/g says indicators should be contextual, conditional and passive. List gaps first.
  - State where the system looked, and when.
  - Siemens AI-Pathway Companion also flags missing data, but it goes on to suggest treatment options. That is outside Vaidyx scope, so do not copy it.
- **Alert fatigue.**
  - Sort flags into three tiers: Blocks board date, Should fix, Information.
  - Never repeat a flag. Ancker: repeated reminders lowered acceptance.
  - Send each flag to the role that can act on it. PSNet's summary of Hussain 2019: tailoring alerts to the clinician's role worked best (not verified).
  - Escalate a passive flag only as the board date nears, as Blecker suggests.

## Invented concepts

### I1. Fill-in summary (recommended main page)

**Pitch: the board summary is the checklist. Every required value is a slot, blanks are the gaps, and closing a gap fills the summary.**

It mixes four ideas:

- GOV.UK check answers (a summary with change actions),
- the evidence pane,
- gaps shown where they belong,
- batch approval.

The assistant fills each slot with a quote, and the doctor approves section by section.

```
+ R. Kumar M 58 . UHID 10-2231 . Board Thu 24 Oct . Ready 14 of 17 . Needs you 2 ----+
| BOARD SUMMARY (draft)                         | SOURCE                             |
| Presenting  "ulcer left tongue, 3 months" (q) | HPE report 14 Oct, page 1          |
| Biopsy      12 Oct 2026                   (q) | "... Date of biopsy: 12/10/2026"   |
| HPE         final, signed                 (q) |      ^^^^^^^^^^^^^^^^^^^^^^^^      |
| CECT neck   [ ____ ]  requested 15 Oct,       | [Looks right]  [Wrong value]       |
|             waiting on Radiology  [Remind]    |                                    |
| LFT         [ ____ ]  [Ask lab] [Not needed]  | Ask the Case File                  |
| History     6 lines drafted [Review] [Approve]| [ type a question ...     ] [Ask]  |
| Specialty briefs (6), 2 new          [Open]   |                                    |
| Board decision: opens at 17 of 17 (MDT coord) | Documents by visit (23)    [Open]  |
+-----------------------------------------------+------------------------------------+
```

Where today's seven tabs go:

| Today's tab | In the fill-in summary |
|---|---|
| Pre-Authorization | The slots and the header count |
| Documents | "Documents by visit" in the source pane |
| Ask the Case File | A question box in the source pane |
| Specialty support | A folded section |
| Case File summary | The page itself, with Print and Export |
| Board and follow-up | The last section, unlocked when ready |
| Audit log | A "History" link on each slot, plus one global link |

### I2. Patient inbox (top band of I1)

**Pitch: inbox zero for one patient. The assistant drafts every routine step, and the doctor clears them like email.**

Three lanes: Needs you, Waiting on others, Done today. Enter approves the item and moves to the next, and Undo stays available. Show at most 3 rows, with the summary below.

```
+ R. Kumar M 58 . UHID 10-2231 . Board Thu 24 Oct ----------------------------------+
| NEEDS YOU (2)   WAITING ON OTHERS (3)  DONE TODAY (5) | Resident history draft    |
| > Approve resident history draft        6 lines       | 1 "Ulcer left tongue,     |
|   Confirm biopsy date 12 Oct            1 quote       |   3 months" OPD 28 Sep ok |
| ----------------------------------------------------- | 2 "Chews tobacco 20 yrs"  |
|   Radiology: CECT neck report           asked 15 Oct  |   OPD 28 Sep           ok |
|   Lab: LFT                              asked 16 Oct  | [Approve 6] [Edit]        |
| ----------------------------------------------------- | Enter = approve, next     |
| Board summary, documents and briefs continue below                                |
+-----------------------------------------------------------------------------------+
```

### I3. Case spine with ghost slots

**Pitch: the patient's story on one line of dates, with records not found drawn as empty slots where they belong.**

A required record that is not in the file shows as a dashed placeholder beside its event. Clicking it opens the request in the inspector. When the report arrives, the slot turns solid and is marked "new".

```
+ R. Kumar M 58 . UHID 10-2231 . Board Thu 24 Oct . Ready 14 of 17 -----------------+
|  today 17 Oct ------o                                   | INSPECTOR               |
|                     |  new  Radiology reply 16 Oct      | Request to Radiology    |
|  IP 10 to 13 Oct ---o  Biopsy 12 Oct               (q)  | "Please share CECT neck |
|                     |  +- HPE report 14 Oct       (q)   |  report, UHID 10-2231"  |
|                     |  +- [ Discharge summary:          | [Send] [Edit]           |
|                     |       not found in the file ]     |                         |
|  OPD 03 Oct --------o  "CECT neck advised"         (q)  |                         |
|                     |  +- [ CECT neck report:           |                         |
|                     |       not found in the file ]     |                         |
|  OPD 28 Sep --------o  Referral letter, CBC        (q)  |                         |
+-----------------------------------------------------------------------------------+
```

**Suggested pick:** I1 as the page, with I2's "Needs you" lane (3 rows at most) as its top band and I3 as a "Timeline" view inside Documents.

## Sources

| Title | Publisher | URL | Supports |
|---|---|---|---|
| Tabs, Used Right | NN/g | https://www.nngroup.com/articles/tabs-used-right/ | Tabs fail when users must compare |
| Accordions on Desktop | NN/g | https://www.nngroup.com/articles/accordions-on-desktop/ | Show all content when most of it is needed |
| Modal and Nonmodal Dialogs | NN/g | https://www.nngroup.com/articles/modal-nonmodal-dialog/ | Modals interrupt; non-modal panels for switching |
| Overuse of Overlays | NN/g | https://www.nngroup.com/articles/overuse-of-overlays/ | Overlays only for user-started or urgent steps |
| Confirmation Dialogs | NN/g | https://www.nngroup.com/articles/confirmation-dialog/ | Habituation; provide Undo |
| Saving Scroll Position | NN/g | https://www.nngroup.com/articles/saving-scroll-position/ | Interaction cost; 30 to 60 minute window |
| Progressive Disclosure | NN/g | https://www.nngroup.com/articles/progressive-disclosure/ | Two levels at most |
| Indicators, Validations, Notifications | NN/g | https://www.nngroup.com/articles/indicators-validations-notifications/ | Contextual, passive indicators |
| Cards Component | NN/g | https://www.nngroup.com/articles/cards-component/ | Cards are less scannable than lists |
| Hamburger menus and hidden navigation | NN/g | https://www.nngroup.com/articles/find-navigation-mobile-even-hamburger/ | Hidden navigation hurts |
| Avoid Horizontal Tabs | Baymard | https://baymard.com/blog/avoid-horizontal-tabs | Tabbed content overlooked; sticky table of contents |
| Task list component | GOV.UK Design System | https://design-system.service.gov.uk/components/task-list/ | When to use; whole row is the link |
| Complete multiple tasks | GOV.UK Design System | https://design-system.service.gov.uk/patterns/complete-multiple-tasks/ | Status words, "Cannot start yet" |
| Check answers | GOV.UK Design System | https://design-system.service.gov.uk/patterns/check-answers/ | Return to the summary after a change |
| Iterating the task list pattern | GOV.UK Design Notes | https://designnotes.blog.gov.uk/2023/12/15/working-as-a-community-to-iterate-the-task-list-pattern/ | Users clicked the status tags |
| Task list | NHS digital service manual | https://service-manual.nhs.uk/design-system/components/task-list | NHS use of the pattern |
| Side sheets | Material Design 3 | https://m3.material.io/components/side-sheets/guidelines | Standard vs modal sheets (search snippet) |
| Canonical layouts | Android Developers | https://developer.android.com/develop/adaptive-apps/guides/canonical-layouts | List-detail and supporting pane |
| Panels; Sidebars | Apple HIG | https://developer.apple.com/design/human-interface-guidelines/panels | Inspector follows the selection (search snippet) |
| Improved PR merge experience | GitHub Changelog | https://github.blog/changelog/2024-12-03-improved-pull-request-merge-experience-now-in-public-preview | Checks grouped, failing first |
| Incorporating feedback in your PR | GitHub Docs | https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/reviewing-changes-in-pull-requests/incorporating-feedback-in-your-pull-request | Batch-apply suggestions |
| Deployment Checks | Vercel Docs | https://vercel.com/docs/deployment-checks | Required checks gate promotion |
| Viewports reference | Stripe Docs | https://docs.stripe.com/stripe-apps/reference/viewports | Drawer bound to the page object |
| Peek preview | Linear Docs | https://linear.app/docs/peek | Space-bar preview (search snippet) |
| In Basket overview | TriHealth | https://bridge.trihealth.com/-/media/bridge/public/our-stories-images/2022/october/in-basket-overview.pdf | Panes, QuickActions (not verified) |
| One Chart changes (Storyboard) | UNMC | https://www.unmc.edu/newsroom/2019/11/27/coming-soon-changes-to-one-chart-patient-workspace/ | Storyboard pilot and quotes |
| QRG 1025 Workflow MPages | Northern Light Health | https://hi.northernlighthealth.org/Flyers/Quick-Reference-Guides-(QRGs)/Back-to-Basics/QRG-1025-Use-the-Workflow-MPages.aspx | Cerner navigator (not verified) |
| Health Maintenance display change | Houston Methodist IT | https://it.houstonmethodist.org/some-health-maintenance-topics-now-appear-without-overdue-date/ | "Overdue: never done" |
| EHR report for HbA1c delays | Jt Comm J Qual Patient Saf (PMC) | https://pmc.ncbi.nlm.nih.gov/articles/PMC9216238 | 18% of care-gap flags misclassified |
| NAVIFY Tumor Board brochure | Roche | https://assets.roche.com/f/198420/x/96d7d8297a/navify-tumor-board-brochure-en.pdf | Reschedule when info missing (vendor) |
| Digital tumor board solutions (Hammer 2020) | JCO Clin Cancer Inform (ASCO) | https://ace.asco.org/content/371942/abstract/206436 | 30% less prep time; Roche co-authors |
| OncoLens for providers | OncoLens | https://www.oncolens.com/providers/ | Questions to departments before conference (not verified) |
| AI-Pathway Companion | Siemens Healthineers | https://www.siemens-healthineers.com/press/releases/pr-aipathwaycomp-ce.html | Flags missing data, also recommends (out of scope) |
| Improving MTB decision making (Lamb 2013) | J Am Coll Surg | https://www.em-consulte.com/article/829134/improving-decision-making-in-multidisciplinary-tum | Decisions 82.2% to 92.7% |
| Display fragmentation (Senathirajah 2020) | JMIR Human Factors | https://humanfactors.jmir.org/2020/4/e18484/PDF | Screen changes 43 to 14 |
| User-composable EHR (2016) | eGEMs (PMC) | https://pmc.ncbi.nlm.nih.gov/articles/PMC4862763 | Repeat viewing 72.6% to 14.6% |
| LifeLines vs tabular | Univ. of Maryland | https://drum.lib.umd.edu/items/c92aa8c0-478d-491a-b2da-68b0a1ffbd3e/full | Faster, better recall |
| HARVEST | JAMIA (PMC) | https://pmc.ncbi.nlm.nih.gov/articles/PMC4394965 | Timeline summariser, high satisfaction |
| AWARE (Pickering 2010) | Applied Clinical Informatics (PMC) | https://pmc.ncbi.nlm.nih.gov/articles/PMC3632280 | Task load 47 to 26, errors 24 to 13 |
| Interruptive vs noninterruptive CDS (Blecker 2019) | JMIR Human Factors (PMC) | https://pmc.ncbi.nlm.nih.gov/articles/PMC6492060/ | 7 of 12 missed the sidebar alert |
| Repeated alerts (Ancker 2017) | BMC Med Inform Decis Mak | https://bmcmedinformdecismak.biomedcentral.com/articles/10.1186/s12911-017-0430-8 | Each extra reminder: 30% lower acceptance |
| Overriding drug alerts (van der Sijs 2006) | JAMIA (PMC) | https://pmc.ncbi.nlm.nih.gov/articles/PMC1447540 | 49 to 96% overridden |
| Alert fatigue primer | AHRQ PSNet | https://psnet.ahrq.gov/primer/alert-fatigue | Tiering; non-interruptive for low severity |
| Automation bias (Goddard 2012) | JAMIA (PMC) | https://pmc.ncbi.nlm.nih.gov/articles/PMC3240751 | Risk ratio 1.26; information over commands |
| Guidelines for Human-AI Interaction | Microsoft Research, CHI 2019 | https://www.microsoft.com/en-us/haxtoolkit/library/ | G8 dismissal, G9 correction |
| Appropriate reliance on LLMs (Kim 2025) | CHI 2025 (arXiv) | https://arxiv.org/abs/2502.08554v1 | Sources reduce reliance on wrong answers |
| Verify a note with Linked Evidence | Abridge | https://support.abridge.com/hc/en-us/articles/30235128433811-Verify-a-Note-With-Linked-Evidence | Note text linked to source in a side panel |
| Hebbia review | Data Studios | https://www.datastudios.org/post/hebbia-ai-document-research-for-finance-matrix-workflows-and-pricing | Cells link to source (secondary) |
| Gmail auto-advance | Official Gmail Blog | https://gmail.googleblog.com/2011/05/how-to-set-up-gmail-to-power-through.html | Next item after archive (not verified) |
| Inbox Zero in 7 steps | Superhuman blog | https://blog.superhuman.com/inbox-zero-in-7-steps/ | Split inbox; inbox as a to-do list |
| Imaging at MDT audit | Royal College of Radiologists | https://www.rcr.ac.uk/career-development/audit-quality-improvement/auditlive-radiology-templates/availability-of-imaging-material-images-and-reports-at-multi-disciplinary-team-mdt-meetings-qsi-refs-xr-703-xr-704/ | Target: 100% of imaging available before the MDT |

**Not verified:**

- Epic Storyboard usability numbers (none found)
- Harvey's evidence UI
- A Stripe Dashboard setup-guide drawer
- Syapse and Varian tumour-board screens
- Any controlled study of command palettes
