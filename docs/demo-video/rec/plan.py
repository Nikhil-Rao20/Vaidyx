"""The edit plan of the Vaidyx-TB demo video: chapters, segments cut from the raw recording (by the marks the recorder left),
layouts and narration. `python plan.py` writes edit/plan.json with absolute source times; edit.py builds the video from it.

Segment keys: layout full | split | phone | still | pip; src (session) or left/right (split) or images (still);
a, b: source window as (mark label, occurrence, offset seconds) - occurrence -1 is the last one; speed; lines: [(at, text)] with
`at` in source seconds after `a` (the narration may push a line later; the segment then holds its last frame).
"""
import json
import os

RUN = os.environ.get("DEMO_RUN", "run2")
RAW = f"/data/vaidyx/demo_video/raw/{RUN}"
OUT = "/data/vaidyx/demo_video/edit/plan.json"

TITLE = "Vaidyx Tumour Board"
DECK = "/data/vaidyx/demo_video/assets/deck/hd-{:02d}.png"


def m(label, occ=-1, off=0.0):
    return (label, occ, off)


CHAPTERS = [
    dict(id="c00", kind="intro", segments=[
        dict(layout="title", dur=4.0, lines=[(0.3, "Vaidyx Tumour Board: a complete walkthrough, recorded live on the development server. "
                                                   "Every patient and every value you will see is synthetic.")]),
        dict(layout="agenda", dur=4.0, lines=[(0.2, "We follow one patient from her first visit in the hospital system to a decision at the Tumour Board, "
                                                   "with every role signing in and doing its own part.")]),
        dict(layout="full", src="site", a=m("site:start", -1, 0.3), b=m("site:hero", -1, 1.5), speed=1.0,
             lines=[(0.5, "This is the platform's entrance.")]),
    ]),
    dict(id="c01", title="At the hospital", subtitle="Registration and the OPD visit, in the hospital system", segments=[
        dict(layout="full", src="his", a=m("start:reception", -1, 0.2), b=m("reception:visit-opened", -1, 4.0), speed=1.6,
             label="Hospital system · Registration desk",
             lines=[(0, "Our patient is Anjali Nair, forty-nine, with a lump in the right breast. The registration desk signs in to the hospital system."),
                    ("reception:register", "Registration gives a permanent UHID, with the ABHA number and the PM-JAY ID."),
                    ("reception:open-visit", "Reception then opens an OPD visit in Breast Surgery.")]),
        dict(layout="full", src="his", a=m("start:opd", -1, 0.0), b=m("end:opd", -1, 0.0), speed=2.2,
             label="Hospital system · OPD consultant, Breast Surgery",
             lines=[(0, "The breast surgeon writes the OPD note: the complaint, the examination and the question for the Board, and signs it."),
                    ("opd:orders", "Then the work-up is ordered: blood tests, a mammogram, a core biopsy with IHC, and a CT of the chest, abdomen and pelvis."),
                    ("opd:orders-placed", "Every order gets its own accession number.")]),
    ]),
    dict(id="c02", title="The departments report", subtitle="Laboratory, Radiology and Pathology, each in its own module", segments=[
        dict(layout="full", src="his", a=m("start:lab"), b=m("end:lab"), speed=3.0, label="Hospital system · Laboratory consultant",
             lines=[(0, "The laboratory collects the samples, enters the results, and signs the blood count, liver and kidney tests.")]),
        dict(layout="full", src="his", a=m("start:radiology"), b=m("end:radiology"), speed=3.0, label="Hospital system · Radiologist",
             lines=[(0, "The radiologist schedules the mammogram, writes the findings and the impression, and signs."),
                    ("rad:CECT chest, abdomen and pelvis", "The CT is reported and signed the same way: no distant disease.")]),
        dict(layout="full", src="his", a=m("start:pathology"), b=m("end:pathology"), speed=2.5, label="Hospital system · Pathologist",
             lines=[(0, "The pathologist signs the biopsy: invasive breast carcinoma, grade 2."),
                    ("path:sign-hpe", "The IHC is left unreported on purpose. Vaidyx will find it missing.")]),
    ]),
    dict(id="c03", title="A Case File in Vaidyx", subtitle="From the hospital system to a Board brief, in seconds", segments=[
        dict(layout="full", src="doc", a=m("start:casefile", -1, 0.0), b=m("v-entrance:doc", -1, 10.5), speed=1.0, label="Vaidyx · Dr Breast Surgery",
             lines=[(0.3, "Now Vaidyx. The breast surgeon signs in.")]),
        dict(layout="full", src="doc", a=m("casefile:lookup", -1, -1.0), b=m("casefile:create", -1, 3.0), speed=1.25, label="Vaidyx · New Case File",
             lines=[(0, "A new Case File starts from the UHID. Vaidyx looks the patient up in the hospital system and shows the registration first."),
                    ("casefile:cancer", "The doctor picks the cancer and the setting as recorded. Vaidyx never works out a stage."),
                    ("casefile:logistics", "Then the board date, an urgency tag, and a read-back of what will be created.")]),
        dict(layout="full", src="doc", a=m("casefile:create", -1, 3.0), b=m("casefile:processed", -1, 1.0), speed=1.0, label="Vaidyx · Case File",
             lines=[(0, "Vaidyx fetches every report from the hospital system and reads them, in a few seconds.")]),
        dict(layout="full", src="doc", a=m("casefile:processed", -1, 1.0), b=m("casefile:end", -1, 0.0), speed=1.0, label="Vaidyx · Board brief",
             lines=[(0, "The Board brief comes first: the question for the Board, and what is still open, each with its next step."),
                    ("casefile:source", "Every value carries its quote. One click opens the source document at that line.")]),
    ]),
    dict(id="c04", title="Asking Pathology", subtitle="Vaidyx on the left, the hospital system on the right", segments=[
        dict(layout="split", left="doc", right="his2", active="left", a=m("split:start", -1, 0.0), b=m("split:head-login", -1, 0.0), speed=1.0,
             llabel="Vaidyx · Dr Breast Surgery", rlabel="Hospital system · DemoHIMS",
             lines=[(0, "The receptor results are not in the file: the IHC was ordered, but no report has come back. One click asks Pathology.")]),
        dict(layout="split", left="pathhead", right="his2", active="left", a=m("split:head-login", -1, 0.0), b=m("split:open-his", -1, 1.0), speed=1.25,
             llabel="Vaidyx · Head of Pathology", rlabel="Hospital system · DemoHIMS",
             lines=[(0, "The head of Pathology signs in to Vaidyx and finds the request in the department's inbox, with its accession number."),
                    ("split:ack", "Acknowledge tells the surgeon it is in hand. Open order in HIS jumps to the order in the hospital system.")]),
        dict(layout="split", left="pathhead", right="his2", active="right", a=m("split:open-his", -1, 1.0), b=m("split:his-signed", -1, 1.5), speed=1.3,
             llabel="Vaidyx · Head of Pathology", rlabel="Hospital system · Pathologist",
             lines=[(0, "The deep link asks the pathologist to sign in, then opens the order."),
                    ("split:his-order", "The pathologist enters ER, PR, HER2 and Ki-67, and signs the report.")]),
        dict(layout="split", left="doc", right="his2", active="left", a=m("split:refetch", -1, -1.0), b=m("split:refetched", -1, 7.0), speed=1.0,
             llabel="Vaidyx · Dr Breast Surgery", rlabel="Hospital system · Pathologist",
             lines=[(0, "Back in Vaidyx, Re-fetch brings the signed report in. The receptor results arrive with their quotes, and the open item closes by itself.")]),
        dict(layout="split", left="pathhead", right="his2", active="left", a=m("split:inbox-again", -1, 0.0), b=m("split:end", -1, 0.0), speed=1.0,
             llabel="Vaidyx · Head of Pathology", rlabel="Hospital system · Pathologist",
             lines=[(0, "In the Pathology inbox, the request is done.")]),
    ]),
    dict(id="c05", title="Ready for the Board", subtitle="Confirm, complete, ask, and mark ready", segments=[
        dict(layout="full", src="doc", a=m("prep:start", 1, 0.0), b=m("prep:ask", 1, 0.0), speed=1.0, label="Vaidyx · Dr Breast Surgery",
             lines=[(0, "Two items still need the doctor. The tumour size differs between two reports: Vaidyx shows both quotes, and the doctor confirms which one is used."),
                    (("prep:menopausal", 1), "Menopausal status is in no report, so the doctor enters it. It is shown as entered by the doctor, never as a finding.")]),
        dict(layout="full", src="doc", a=m("prep:ask", 1, 0.0), b=m("prep:ready", 1, 0.0), speed=1.0, label="Vaidyx · Ask this Case File",
             lines=[(0, "Ask this Case File answers in plain words. Every sentence carries its source, and the team sees every answer.")]),
        dict(layout="full", src="doc", a=m("prep:ready", 1, 0.0), b=m("prep:marked", 1, 2.0), speed=1.0, label="Vaidyx · Mark ready",
             lines=[(0, "Mark ready reads back anything still open, and leaves a note for the coordinator.")]),
        dict(layout="full", src="doc", a=m("prep:marked", 1, 2.0), b=m("prep:summary-ready", -1, 0.0), speed=50.0, label="Vaidyx · Preparing",
             lines=[(0, "Marking ready starts the summary and the specialty briefs, on the hospital's own server.")]),
        dict(layout="full", src="doc", a=m("brief:start", -1, 0.0), b=m("brief:helpers", -1, 0.0), speed=1.0, label="Vaidyx · Summary",
             lines=[(0, "The summary is written only from verified lines. Each sentence has its quote, and points for review are listed for the Board.")]),
        dict(layout="full", src="doc", a=m("brief:helpers", -1, 0.0), b=m("brief:end", -1, 0.0), speed=1.0, label="Vaidyx · Specialty helpers",
             lines=[(0, "Specialty helpers prepare a brief for each board head. Here, Pathology: records and guideline points only, never an opinion.")]),
    ]),
    dict(id="c06", title="The Tumour Board meeting", subtitle="Agenda, video, the room screen and the decision", segments=[
        dict(layout="full", src="mdt", a=m("meet:new", 1, -2.5), b=m("meet:created", 1, 2.5), speed=1.0, label="Vaidyx · MDT Coordinator",
             lines=[(0, "The MDT coordinator creates the meeting: date, time, room, and video for the doctors who join remotely.")]),
        dict(layout="full", src="mdt", a=m("meet:add", -1, -0.5), b=m("meet:start", -1, 0.0), speed=1.0, label="Vaidyx · MDT Coordinator",
             lines=[(0, "Case Files marked ready are offered for the agenda. One click adds Anjali's for discussion."),
                    ("meet:code", "A six-digit join code is made, and the agenda goes out in the app.")]),
        dict(layout="full", src="mdt", a=m("meet:start", -1, 0.0), b=m("meet:doc-join", -1, 0.0), speed=1.0, label="Vaidyx · MDT Coordinator",
             lines=[(0, "Start meeting opens a pre-join check of the camera and microphone. Video runs on the hospital's own server.")]),
        dict(layout="full", src="doc2", a=m("meet:doc-join", -1, 0.0), b=m("meet:admit", -1, 1.0), speed=1.0, label="Vaidyx · Dr Breast Surgery, joining",
             lines=[(0, "A doctor joins from anywhere with the code.")]),
        dict(layout="full", src="mdt", a=m("meet:admit", -1, 1.0), b=m("meet:in-call", -1, 3.0), speed=1.0, label="Vaidyx · MDT Coordinator, conducting",
             lines=[(0, "The coordinator admits them. Everyone sees the same summary, and each member's camera. These are synthetic test cameras.")]),
        dict(layout="full", src="doc2", a=m("meet:in-call", -1, 0.0), b=m("meet:room", -1, 1.0), speed=1.0, label="Vaidyx · a member's view",
             lines=[(0, "This is a member's view of the same meeting.")]),
        dict(layout="pip", src="room", pip="mdt", a=m("meet:slide-2", -1, -1.0), b=m("meet:show-ihc", -1, 0.0), speed=1.25, label="Vaidyx · the room screen",
             piplabel="Coordinator's controls",
             lines=[(0, "The room screen joins under its own identity. From the conduct panel, the coordinator puts slides on it: the summary, the key values with their sources, and the gaps.")]),
        dict(layout="pip", src="room", pip="mdt", a=m("meet:show-ihc", -1, 0.0), b=m("meet:show-ihc", -1, 7.5), speed=1.0, label="Vaidyx · the room screen",
             piplabel="Coordinator's controls",
             lines=[(0, "Signed reports open on the shared screen, exactly as they were signed.")]),
        dict(layout="full", src="mdt", a=m("meet:decision", -1, 0.0), b=m("meet:save-decision", -1, 7.0), speed=1.4, label="Vaidyx · MDT Coordinator, decision",
             lines=[(0, "The decision is typed as the chair states it. It shows live on the room screen, marked not saved."),
                    ("meet:save-decision", "Once saved, it goes into the Case File, and each board head confirms it with a card.")]),
        dict(layout="full", src="mdt", a=m("meet:end", -1, 0.0), b=m("meet:closed", -1, 2.5), speed=1.0, label="Vaidyx · MDT Coordinator",
             lines=[(0, "Ending the meeting sends the outcome to the owner of each Case File.")]),
        dict(layout="still", images=[DECK.format(1), DECK.format(9), DECK.format(10), DECK.format(11)], per=3.4, label="Vaidyx · meeting deck with minutes",
             lines=[(0.2, "The meeting deck with minutes is built from the Case Files: the outcome, the decision in the board's words, the cards, and the members present.")]),
    ]),
    dict(id="c07", title="After the Board", subtitle="The record, the downloads and the images", segments=[
        dict(layout="full", src="doc", a=m("after:list", -1, -3.0), b=m("after:casefile", -1, 1.0), speed=1.0, label="Vaidyx · Dr Breast Surgery",
             lines=[(0, "Back in Case Files, Anjali's file now shows Decided.")]),
        dict(layout="full", src="doc", a=m("after2:boardform", -1, -1.0), b=m("after2:download", -1, 0.0), speed=1.0, label="Vaidyx · Board form",
             lines=[(0, "The Board form keeps the decision as recorded: the outcome, the rationale, the intent as stated, the responsible doctor and the members present.")]),
        dict(layout="full", src="doc", a=m("after2:download", -1, 0.0), b=m("after2:end", -1, 0.0), speed=1.0, label="Vaidyx · Download",
             lines=[(0, "Download gives the board deck and the NCG template.")]),
        dict(layout="full", src="images", a=m("after:images-shown", -1, 0.3), b=m("after:activity", -1, -0.3), speed=1.0, label="PACS viewer · for doctors",
             lines=[(0, "Images open in the hospital's PACS viewer, for the doctors to read. No model ever reads them.")]),
        dict(layout="full", src="doc", a=m("after:activity", -1, 0.0), b=m("after:end", -1, 0.0), speed=1.0, label="Vaidyx · Activity",
             lines=[(0, "And every action, by every role, is in the activity log.")]),
    ]),
    dict(id="c08", title="Running the platform", subtitle="Hospital set-up and people, for the root admin", segments=[
        dict(layout="full", src="root", a=m("v-entrance:root", -1, 8.5), b=m("admin:people", -1, 0.0), speed=1.3, label="Vaidyx · Root admin",
             lines=[(0, "The root admin sets up the hospital once: departments, people and roles, the link to the hospital system, and the board.")]),
        dict(layout="full", src="root", a=m("admin:people", -1, 0.0), b=m("admin:end", -1, 0.0), speed=1.0, label="Vaidyx · People",
             lines=[(0, "People lists every login and role. Admin rights are never granted by a Tumour Board action.")]),
    ]),
    dict(id="c09", title="On the phone", subtitle="The same Case Files, on a doctor's phone", segments=[
        dict(layout="phone", src="phone", a=m("phone:list", -1, -3.0), b=m("phone:end", -1, 0.0), speed=1.25, label="Vaidyx · phone",
             lines=[(0, "On a phone: the Case Files list, the brief first, and a dock to move between Case Files and Meetings.")]),
    ]),
    dict(id="c10", title="The public website", subtitle="What a hospital sees before signing in", segments=[
        dict(layout="full", src="site", a=m("site:hero", -1, 1.0), b=m("site:research", -1, 0.0), speed=1.8, label="Public website · Product",
             lines=[(0, "The public website explains the product: the problem it addresses, how it works, and the Tumour Board workflow."),
                    (40.0, "Further down: every value with its source, the Tumour Board workflow, and the design principles.")]),
        dict(layout="full", src="site", a=m("site:research", -1, 0.0), b=m("site:end", -1, 0.0), speed=1.3, label="Public website · Research",
             lines=[(0, "Research holds the benchmark of thirteen open models and Vaidyx's own grounded evaluations, with the paper to download.")]),
    ]),
    dict(id="c99", kind="outro", segments=[
        dict(layout="outro", dur=5.0, lines=[(0.3, "That is the whole cycle: from the hospital's records to a decision at the Tumour Board, with every fact tied to its source.")]),
    ]),
]


def load_marks():
    marks = {}
    for line in open(f"{RAW}/marks.jsonl"):
        x = json.loads(line)
        marks.setdefault(x["label"], []).append(x["t"])
    return marks


def resolve(marks, spec):
    label, occ, off = spec
    ts = marks[label]
    return (ts[occ - 1] if occ > 0 else ts[occ]) + off


def main():
    marks = load_marks()
    out = []
    numbered = [ch for ch in CHAPTERS if ch.get("title")]
    for ch in CHAPTERS:
        c = {k: v for k, v in ch.items() if k != "segments"}
        if ch.get("title"):
            c["number"] = numbered.index(ch) + 1
        c["segments"] = []
        segs = list(ch["segments"])
        if ch.get("title"):  # the chapter card, its title read out
            segs = [dict(layout="card", dur=3.4, nocaption=True, lines=[(0.5, f"{ch['title']}.")])] + segs
        for i, s in enumerate(segs):
            seg = dict(s)
            seg["id"] = f"{ch['id']}-s{i + 1:02d}"
            if "a" in s:
                seg["t0"] = resolve(marks, s["a"])
                seg["t1"] = resolve(marks, s["b"])
                assert seg["t1"] > seg["t0"], (seg["id"], seg["t0"], seg["t1"])
                del seg["a"], seg["b"]
            lines = []
            for j, (at, text) in enumerate(s.get("lines", [])):
                if isinstance(at, (str, tuple, list)):  # a mark (label or (label, occurrence)): seconds after the segment start
                    label, occ = (at, -1) if isinstance(at, str) else at
                    at = resolve(marks, (label, occ, 0.0)) - seg["t0"]
                lines.append({"id": f"{seg['id']}-l{j + 1}", "at": round(max(0.0, at), 2), "text": text})
            seg["lines"] = lines
            c["segments"].append(seg)
        out.append(c)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump(out, open(OUT, "w"), indent=1)
    n = sum(len(c["segments"]) for c in out)
    nl = sum(len(s["lines"]) for c in out for s in c["segments"])
    src = sum((s["t1"] - s["t0"]) / s.get("speed", 1) for c in out for s in c["segments"] if "t0" in s)
    print(f"{len(out)} chapters, {n} segments, {nl} narration lines, {src / 60:.1f} min of footage at the chosen speeds")


if __name__ == "__main__":
    main()
