"""Record interview answers into the round files and rebuild the question bank.

Usage: python docs/ui/questions/record_answers.py answers.json
answers.json: {"R01-Q01": {"answer": "label or labels", "own_words": "", "status": "Answered", "notes": ""}, ...}
status defaults to "Answered"; use "Skipped" (with notes saying why) for a question an earlier answer settled.
New questions: {"R01-Q14": {"new": {question object as in the round files}, "answer": ...}} adds it to its round.
"""
import json, subprocess, sys
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main(path):
    answers = json.loads(Path(path).read_text(encoding="utf-8"))
    files = {p: json.loads(p.read_text(encoding="utf-8")) for p in sorted((HERE / "rounds").glob("R*.json"))}
    by_id = {q["id"]: (p, q) for p, r in files.items() for q in r["questions"]}
    today = date.today().strftime("%d/%m/%Y")
    for qid, a in answers.items():
        if "new" in a:
            rnd = int(qid[1:3])
            p = next(p for p, r in files.items() if r["round"] == rnd)
            q = dict(a["new"], id=qid)
            files[p]["questions"].append(q)
            by_id[qid] = (p, q)
        p, q = by_id[qid]
        q["status"] = a.get("status", "Answered")
        for k in ("answer", "own_words", "notes"):
            if a.get(k):
                q[k] = a[k]
        q["answered_on"] = today
    for p, r in files.items():
        answered = sum(1 for q in r["questions"] if q.get("status") in ("Answered", "Skipped"))
        active = sum(1 for q in r["questions"] if q.get("status") != "Dropped")
        r["status"] = "Done" if answered == active else ("In progress" if answered else r.get("status", "Not started"))
        p.write_text(json.dumps(r, ensure_ascii=False, indent=1), encoding="utf-8")
    subprocess.run([sys.executable, "-I", str(HERE / "build_bank.py")], check=True)


if __name__ == "__main__":
    main(sys.argv[1])
