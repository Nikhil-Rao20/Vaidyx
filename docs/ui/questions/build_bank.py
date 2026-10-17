"""Build the Vaidyx-TB question bank (Excel) from the round files, and check the questions.

Source of truth: docs/ui/questions/rounds/R01.json ... R18.json (one round each; answers are written back into them).
Output: docs/ui/questions/Vaidyx_TB_Question_Bank.xlsx (sheets: How to use, Rounds, Questions, Resources, Settled, Decisions).

Usage:
  python docs/ui/questions/build_bank.py            # check, then build the workbook
  python docs/ui/questions/build_bank.py --check    # check only (prints problems, exit 1 if any hard error)
"""
import argparse, difflib, json, re, sys
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROUNDS = HERE / "rounds"
OUT = HERE / "Vaidyx_TB_Question_Bank.xlsx"
SETTLED = HERE / "settled.json"

DASHES = re.compile("[\u2013\u2014]")
SCOPE = re.compile(r"\b(diagnos(e|is|es)|recommend(s|ed)? (a )?treatment|treatment (plan|choice) by (the )?AI|predict(s|ion)? (survival|outcome|prognosis)|assign(s)? (the )?stage|interpret(s)? (the )?(image|scan))", re.I)
STATUS = ["To ask", "Asked", "Answered", "Skipped", "Dropped"]


def load_rounds():
    rounds = []
    for p in sorted(ROUNDS.glob("R[0-9][0-9].json")):
        r = json.loads(p.read_text(encoding="utf-8"))
        r["_file"] = p.name
        rounds.append(r)
    return rounds


def check(rounds):
    """Return (errors, warnings): errors break the format the question tool needs; warnings need a person's look."""
    errors, warnings, ids, texts = [], [], set(), []
    all_ids = {q["id"] for r in rounds for q in r.get("questions", [])}
    dropped = {q["id"] for r in rounds for q in r.get("questions", []) if q.get("status") == "Dropped"}
    for r in rounds:
        rn = r.get("round")
        qs = r.get("questions", [])
        if not qs:
            errors.append(f"{r['_file']}: no questions")
        if sum(1 for q in qs if q.get("core") and q["id"] not in dropped) > 3:
            warnings.append(f"R{rn:02d}: more than 3 core questions")
        for i, q in enumerate(qs, 1):
            qid = q.get("id", "?")
            where = f"{qid}"
            if not re.fullmatch(rf"R{rn:02d}-Q\d{{2}}", qid):
                errors.append(f"{where}: id must look like R{rn:02d}-Qnn")
            if qid in ids:
                errors.append(f"{where}: duplicate id")
            ids.add(qid)
            text = q.get("question", "")
            if not text.strip().endswith("?"):
                errors.append(f"{where}: question must end with '?'")
            hdr = q.get("header", "")
            if not hdr or len(hdr) > 12:
                errors.append(f"{where}: header must be 1 to 12 characters ({hdr!r})")
            opts = q.get("options", [])
            if not 2 <= len(opts) <= 4:
                errors.append(f"{where}: needs 2 to 4 options, has {len(opts)}")
            labels = [o.get("label", "") for o in opts]
            if len(set(labels)) != len(labels):
                errors.append(f"{where}: two options share a label")
            rec = [l for l in labels if l.endswith("(Recommended)")]
            if q.get("type", "decision") == "decision" and (len(rec) != 1 or not labels or not labels[0].endswith("(Recommended)")):
                warnings.append(f"{where}: the recommended option should be first and the only one marked")
            for o in opts:
                words = len(o.get("label", "").replace("(Recommended)", "").split())
                if words == 0 or words > 7:
                    warnings.append(f"{where}: option label of {words} words: {o.get('label')!r}")
                if o.get("label", "").strip().lower().startswith("other"):
                    errors.append(f"{where}: do not add an 'Other' option (the tool adds it)")
                if not o.get("description"):
                    errors.append(f"{where}: option without a description")
            blob = json.dumps(q, ensure_ascii=False)
            if DASHES.search(blob):
                errors.append(f"{where}: contains an em or en dash")
            if SCOPE.search(" ".join([text] + [o.get("label", "") + " " + o.get("description", "") for o in opts])):
                warnings.append(f"{where}: scope words (diagnose / treatment / stage / image): check the wording keeps the AI in scope")
            for d in q.get("depends_on", []):
                if d in dropped and qid not in dropped:
                    warnings.append(f"{where}: depends on dropped question {d}")
                elif d not in all_ids and qid not in dropped:
                    warnings.append(f"{where}: depends_on {d} is not a known question id")
            if q.get("type") == "resource" and not (q.get("resource") or {}).get("item"):
                errors.append(f"{where}: resource question without resource.item")
            if not q.get("why"):
                warnings.append(f"{where}: no 'why'")
            if qid not in dropped:
                texts.append((qid, text))
    for i, (a, ta) in enumerate(texts):
        for b, tb in texts[i + 1:]:
            if difflib.SequenceMatcher(None, ta.lower(), tb.lower()).ratio() > 0.72:
                warnings.append(f"{a} and {b}: very similar questions")
    return errors, warnings


def build(rounds):
    from openpyxl import Workbook
    from openpyxl.formatting.rule import FormulaRule
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.worksheet.datavalidation import DataValidation

    wb = Workbook()
    head = PatternFill("solid", fgColor="0B5D5A"); headf = Font(bold=True, color="FFFFFF")
    wrap = Alignment(wrap_text=True, vertical="top")

    def sheet(ws, cols, rows, widths):
        ws.append(cols)
        for c in ws[1]:
            c.fill, c.font, c.alignment = head, headf, Alignment(wrap_text=True, vertical="center")
        for r in rows:
            ws.append(r)
        for i, w in enumerate(widths, 1):
            ws.column_dimensions[ws.cell(1, i).column_letter].width = w
        for row in ws.iter_rows(min_row=2):
            for c in row:
                c.alignment = wrap
        ws.freeze_panes = "A2"
        ws.auto_filter.ref = ws.dimensions

    ws = wb.active; ws.title = "How to use"
    for line in [
        ["Vaidyx-TB question bank", ""],
        ["Built", date.today().strftime("%d/%m/%Y")],
        ["What it is", "Every question for the 18 interview rounds, asked in batches. Your answer (the option you chose, or your own words) is written into the Questions sheet."],
        ["Order", "Rounds 1 to 16 first; rounds 17 (screens) and 18 (look and feel) last, once everything else is settled."],
        ["Skip rule", "A question whose 'Skip if' condition is met by an earlier answer is marked Skipped, not asked."],
        ["Resources", "Some questions ask you to download a document. You tell me where you put it; I move it into the right folder (Resources sheet)."],
        ["Settled", "Things you already decided on the workflow page (Settled sheet). They are not asked again."],
        ["Source of truth", "docs/ui/questions/rounds/R01.json to R18.json; this workbook is rebuilt from them (build_bank.py)."],
        ["Status values", ", ".join(STATUS)],
    ]:
        ws.append(line)
    ws.column_dimensions["A"].width = 18; ws.column_dimensions["B"].width = 120
    ws["A1"].font = Font(bold=True, size=14)
    for row in ws.iter_rows(min_row=2):
        row[0].font = Font(bold=True); row[1].alignment = wrap

    rows = []
    for r in rounds:
        qs = r.get("questions", [])
        act = [q for q in qs if q.get("status") != "Dropped"]
        rows.append([r["round"], r.get("title", ""), r.get("intro", ""), len(act), len(qs) - len(act), sum(1 for q in act if q.get("core")),
                     sum(1 for q in qs if q.get("type") == "resource"), sum(1 for q in qs if q.get("status") == "Answered"),
                     r.get("status", "Not started")])
    sheet(wb.create_sheet("Rounds"), ["Round", "Title", "What it settles", "Questions", "Dropped", "Core", "Resource asks", "Answered", "Status"],
          rows, [8, 30, 80, 11, 9, 8, 12, 10, 14])

    qcols = ["Round", "Q ID", "Topic", "Core", "Type", "Question", "Header", "Multi", "Option 1", "Option 1: what happens",
             "Option 2", "Option 2: what happens", "Option 3", "Option 3: what happens", "Option 4", "Option 4: what happens",
             "Why it matters", "Depends on", "Skip if", "Status", "Your answer (option)", "Your own words", "Notes", "Answered on"]
    rows = []
    for r in rounds:
        for q in r.get("questions", []):
            opts = q.get("options", []) + [{}] * (4 - len(q.get("options", [])))
            flat = []
            for o in opts[:4]:
                flat += [o.get("label", ""), o.get("description", "")]
            rows.append([r["round"], q["id"], q.get("topic", ""), "yes" if q.get("core") else "", q.get("type", "decision"), q["question"],
                         q.get("header", ""), "yes" if q.get("multi") else "", *flat, q.get("why", ""), ", ".join(q.get("depends_on", [])),
                         q.get("skip_if", ""), q.get("status", "To ask"), q.get("answer", ""), q.get("own_words", ""), q.get("notes", ""),
                         q.get("answered_on", "")])
    wq = wb.create_sheet("Questions")
    sheet(wq, qcols, rows, [7, 10, 18, 6, 9, 60, 12, 6] + [22, 34] * 4 + [50, 14, 30, 11, 26, 40, 30, 12])
    n = len(rows) + 1
    dv = DataValidation(type="list", formula1='"' + ",".join(STATUS) + '"', allow_blank=True)
    wq.add_data_validation(dv); dv.add(f"T2:T{n}")
    for status, colour in [("Answered", "DFF3E4"), ("Skipped", "EEEEEE"), ("Asked", "FFF4D6"), ("Dropped", "F6DEDB")]:
        wq.conditional_formatting.add(f"A2:X{n}", FormulaRule(formula=[f'$T2="{status}"'], fill=PatternFill("solid", fgColor=colour)))

    rows = []
    for r in rounds:
        for q in r.get("questions", []):
            res = q.get("resource") or {}
            if q.get("type") == "resource" or res:
                rows.append([q["id"], res.get("item", ""), res.get("source_url", ""), res.get("why", ""), res.get("target_folder", ""),
                             q.get("resource_status", "Not asked"), q.get("resource_location", ""), q.get("resource_placed", "")])
    sheet(wb.create_sheet("Resources"), ["Q ID", "What", "Where to get it", "Why", "Goes to", "Status", "Where you put it", "Placed at"],
          rows, [10, 40, 45, 45, 40, 12, 35, 35])

    settled = json.loads(SETTLED.read_text(encoding="utf-8")) if SETTLED.exists() else []
    sheet(wb.create_sheet("Settled"), ["Topic", "Your decision", "Where you said it"], [[s["topic"], s["decision"], s["source"]] for s in settled],
          [26, 100, 30])

    rows = [[q["id"], q["question"], q.get("answer", ""), q.get("own_words", ""), q.get("answered_on", "")]
            for r in rounds for q in r.get("questions", []) if q.get("status") == "Answered"]
    sheet(wb.create_sheet("Decisions"), ["Q ID", "Question", "Answer", "Your own words", "Date"], rows, [10, 60, 30, 50, 12])
    wb.save(OUT)
    return OUT


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    rounds = load_rounds()
    errs, warns = check(rounds)
    for e in errs: print("ERROR  ", e)
    for w in warns: print("CHECK  ", w)
    print(f"{len(rounds)} rounds, {sum(len(r.get('questions', [])) for r in rounds)} questions, {len(errs)} errors, {len(warns)} to check")
    if a.check:
        sys.exit(1 if errs else 0)
    print("written", build(rounds))
