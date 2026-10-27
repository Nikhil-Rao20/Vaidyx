"""Check the gold question set for the live agent evaluation (night-v3 item 6.4): tumour_board/eval/agent_live_gold.json.

Reads the demo Case Files TB-001 to TB-008 through tumour_board.store (read only) and fails when a label cannot be scored:
a wrong count per role or kind, an unknown role, case, document or refusal category, a quote that is not word for word in the
named document's page text (runs of whitespace collapsed), an expected value that no quote of the question contains, an
answerable or cross question without values and quotes, an out-of-scope question without a category, a date in the question
that is not DD/MM/YYYY, an em dash anywhere, and a question that guardrails.rule_check would refuse although it is not an
out-of-scope question (a false refusal built into the set), or an out-of-scope question the rules refuse under another category.
No model server is called. Run: /data/vaidyx/venv/app/bin/python tumour_board/eval/check_agent_live_gold.py
"""
import json, re, sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

GOLD = Path(__file__).with_name("agent_live_gold.json")
ROLES = ["radiology", "pathology", "medical_oncology", "surgical_oncology", "radiation_oncology", "nuclear_medicine"]
PREFIX = {"radiology": "rad", "pathology": "pat", "medical_oncology": "med", "surgical_oncology": "sur",
          "radiation_oncology": "rt", "nuclear_medicine": "nm"}
CASES = [f"TB-00{n}" for n in range(1, 9)]  # the synthetic demo Case Files only, never the real case
KINDS = {"answerable": 16, "cross": 6, "not_documented": 6, "out_of_scope": 6, "guideline": 4, "follow_up": 2}
STATUSES = {"answered", "not_documented", "out_of_scope"}
FALLBACK_CATEGORIES = ["in_scope", "treatment_recommendation", "diagnosis", "scan_interpretation", "stage_derivation",
                       "prognosis", "other_out_of_scope"]
OOS_SPREAD = {"treatment_recommendation": 2, "diagnosis": 1, "scan_interpretation": 1, "stage_derivation": 1, "prognosis": 1}
LOOKS = "looks as if it should be in the file"


def squash(s):
    return re.sub(r"\s+", " ", s or "").strip()


def main():
    errors, info = [], []

    def err(qid, msg):
        errors.append(f"{qid}: {msg}")

    raw = GOLD.read_text(encoding="utf-8")
    for ch, name in ((chr(0x2014), "em dash"), (chr(0x2013), "en dash")):
        if ch in raw:
            errors.append(f"file: contains an {name}")
    if "bharath" in raw.lower():
        errors.append("file: mentions the real case")
    gold = json.loads(raw)
    qs = gold.get("questions") or []

    try:
        from tumour_board import guardrails
        categories = list(guardrails.CATEGORIES)
        rule_check = guardrails.rule_check
    except Exception as e:  # keep the check usable without the guardrail module
        categories, rule_check = FALLBACK_CATEGORIES, None
        info.append(f"guardrails not imported ({e}); the rule cross-check is skipped")

    from tumour_board import store
    available = {c.get("case_id") or c.get("id") for c in store.list_cases()}
    pages = {}  # (case, doc_id) -> collapsed page text, page by page
    for cid in CASES:
        if cid not in available:
            errors.append(f"file: demo Case File {cid} is not in the store")
            continue
        for d in store.list_docs(cid):
            full = store.get_doc(cid, d["doc_id"]) or {}
            pages[(cid, d["doc_id"])] = [squash(p.get("text", "")) for p in full.get("pages", [])]

    ids = {}
    for q in qs:
        qid = q.get("id", "?")
        if qid in ids:
            err(qid, "duplicate id")
        ids[qid] = q
    per = Counter((q.get("role"), q.get("kind")) for q in qs)
    cases_by_role = defaultdict(Counter)
    docs_by_role = defaultdict(set)
    rule_oos = Counter()

    for q in qs:
        qid, role, kind, case = q.get("id", "?"), q.get("role"), q.get("kind"), q.get("case_id")
        exp = q.get("expect") or {}
        if role not in ROLES:
            err(qid, f"unknown role {role!r}")
            continue
        if not str(qid).startswith(PREFIX[role] + "-"):
            err(qid, f"id does not start with {PREFIX[role]}-")
        if kind not in KINDS:
            err(qid, f"unknown kind {kind!r}")
            continue
        if case not in CASES:
            err(qid, f"unknown case id {case!r}")
            continue
        cases_by_role[role][case] += 1
        text = q.get("question") or ""
        if not text.strip():
            err(qid, "empty question")
        if re.search(r"\b\d{1,2}-[A-Za-z]{3}-\d{4}\b|\b\d{4}-\d{2}-\d{2}\b|\b\d{1,2}-\d{1,2}-\d{4}\b", text):
            err(qid, "a date in the question is not DD/MM/YYYY")
        status = exp.get("status")
        if status not in STATUSES:
            err(qid, f"unknown status {status!r}")
        if not isinstance(exp.get("reference"), bool):
            err(qid, "expect.reference must be true or false")
        values, quotes = exp.get("values") or [], exp.get("quotes") or []

        # every quote word for word in the named document of the same Case File
        quote_texts = []
        for item in quotes:
            did, quote = item.get("doc_id"), item.get("quote", "")
            if (case, did) not in pages:
                err(qid, f"doc id {did!r} is not a document of {case}")
                continue
            docs_by_role[role].add((case, did))
            qt = squash(quote)
            quote_texts.append(qt.lower())
            if not qt or not any(qt in pg for pg in pages[(case, did)]):
                err(qid, f"quote not found word for word in {case} {did}: {quote!r}")

        if kind in ("answerable", "cross", "follow_up"):
            if status != "answered" or not values or not quotes:
                err(qid, "needs status answered, values and quotes")
            if exp.get("reference") is not False:
                err(qid, "reference must be false")
            for v in values:
                if not any(squash(v).lower() in qt for qt in quote_texts):
                    err(qid, f"value {v!r} is in none of the quotes")
            if kind == "cross" and len({i.get("doc_id") for i in quotes}) < 2:
                err(qid, "a cross question must cite at least two documents")
        if kind == "follow_up":
            first = ids.get(q.get("follows"))
            if not first or first.get("kind") != "answerable" or first.get("role") != role or first.get("case_id") != case:
                err(qid, "follows must name an answerable question of the same role and Case File")
        elif "follows" in q:
            err(qid, "only a follow_up carries follows")
        if kind == "not_documented":
            if status != "not_documented" or values or quotes:
                err(qid, "needs status not_documented and no values or quotes")
        if kind == "guideline":
            if exp.get("reference") is not True or values or quotes:
                err(qid, "needs reference true and no values or quotes")
            if status not in ("answered", "not_documented") or set(exp.get("status_ok") or []) != {"answered", "not_documented"}:
                err(qid, "needs status answered with status_ok answered and not_documented")
        if kind == "out_of_scope":
            cat = exp.get("category")
            if status != "out_of_scope" or cat not in categories or cat == "in_scope":
                err(qid, f"needs status out_of_scope and a refusal category, got {cat!r}")
            for a in exp.get("category_alt") or []:
                if a not in categories or a == "in_scope":
                    err(qid, f"unknown category_alt {a!r}")
            if values or quotes:
                err(qid, "no values or quotes expected")
            if not isinstance(q.get("colleague_style"), bool):
                err(qid, "needs colleague_style true or false")
        # the rules must not refuse a question that has to be answered; a refusal must match the expected category
        if rule_check:
            hit = rule_check(text)
            if kind == "out_of_scope":
                ok = [exp.get("category")] + list(exp.get("category_alt") or [])
                if hit and hit not in ok:
                    err(qid, f"the rules refuse it as {hit}, expected one of {ok}")
                rule_oos[(role, bool(hit))] += 1
                if q.get("colleague_style") and not hit:
                    err(qid, "a colleague-style question must be caught by a rule")
            elif hit:
                err(qid, f"the rules would refuse this question as {hit}")

    for role in ROLES:
        for kind, n in KINDS.items():
            if per[(role, kind)] != n:
                errors.append(f"{role}: {per[(role, kind)]} {kind} questions, expected {n}")
        mine = [q for q in qs if q.get("role") == role]
        if len(mine) != 40:
            errors.append(f"{role}: {len(mine)} questions, expected 40")
        oos = [q for q in mine if q.get("kind") == "out_of_scope"]
        got = Counter((q.get("expect") or {}).get("category") for q in oos)
        if dict(got) != OOS_SPREAD:
            errors.append(f"{role}: out_of_scope categories {dict(got)}, expected {OOS_SPREAD}")
        if sum(1 for q in oos if q.get("colleague_style")) != 3:
            errors.append(f"{role}: expected 3 colleague-style out_of_scope questions")
        nd = [q for q in mine if q.get("kind") == "not_documented"]
        if sum(1 for q in nd if LOOKS in (q.get("note") or "")) != 3:
            errors.append(f"{role}: expected 3 not_documented questions that look as if they should be in the file")
    if len(qs) != 240:
        errors.append(f"total {len(qs)} questions, expected 240")

    print(f"{'role':20s} " + " ".join(f"{k[:6]:>6s}" for k in KINDS) + "  total  cases (questions per Case File)")
    for role in ROLES:
        row = " ".join(f"{per[(role, k)]:6d}" for k in KINDS)
        cs = ", ".join(f"{c}:{n}" for c, n in sorted(cases_by_role[role].items()))
        print(f"{role:20s} {row}  {sum(per[(role, k)] for k in KINDS):5d}  {cs}")
    print(f"total questions {len(qs)}; quotes checked in {len({d for s in docs_by_role.values() for d in s})} documents")
    if rule_check:
        caught = sum(n for (r, h), n in rule_oos.items() if h)
        print(f"out_of_scope questions refused by a rule: {caught} of {sum(rule_oos.values())} (the rest go to the classifier)")
    for line in info:
        print("note:", line)
    if errors:
        print(f"FAIL: {len(errors)} problem(s)")
        for e in errors:
            print(" -", e)
        return 1
    print("PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
