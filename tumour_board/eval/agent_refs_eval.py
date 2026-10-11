"""Guideline references of the specialty agents (V1 item 5.5): run every agent on the demo Case Files through the API and count the
points for review that cite an Indian source. A measurement, not a gate (the model writes the points; nothing here is a pass mark).

    python -m tumour_board.eval.agent_refs_eval --password "$(awk '{print $NF}' ~/vaidyx/.vaidyx_admin_login)" \\
        [--cases TB-001,TB-002,TB-003,TB-004,TB-005,TB-006] [--roles radiology,...] [--out DIR]

"Done when" of 5.5: each agent's review points cite an Indian source whenever one exists. For every point without an Indian
reference the script asks the agent's pack (Indian folders only) the point itself and lists what it found, so a reader can judge
whether an Indian passage existed. Needs the app (port 7000) and both model servers; demo Case Files only, never real ones.
"""
import argparse
import json
import sys
import time
from pathlib import Path

import httpx

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tumour_board import config  # noqa: E402

ROLES = ["radiology", "pathology", "medical_oncology", "surgical_oncology", "radiation_oncology", "nuclear_medicine"]


def run_brief(c, case_id, role):
    t0, brief, err = time.time(), None, None
    with c.stream("POST", f"/api/tb/cases/{case_id}/agents/{role}", json={"focus": ""}) as r:
        if r.status_code != 200:
            return None, f"HTTP {r.status_code}", time.time() - t0
        for line in r.iter_lines():
            if not line.strip():
                continue
            ev = json.loads(line)
            if ev.get("type") == "brief":
                brief = ev["brief"]
            elif ev.get("type") == "error":
                err = ev.get("message")
    return brief, err, time.time() - t0


def summarise(rows):
    pts = [p for r in rows for p in r["points"]]
    return {"briefs": len(rows), "errors": sum(1 for r in rows if r["error"]), "points": len(pts),
            "points_with_reference": sum(1 for p in pts if p["references"]),
            "points_with_indian_reference": sum(1 for p in pts if p["indian"]),
            "indian_by_agent": sum(1 for p in pts if p["indian"] == "agent"), "indian_by_search": sum(1 for p in pts if p["indian"] == "search"),
            "points_without_indian_reference": sum(1 for p in pts if not p["indian"]),
            "of_which_fitting_by_the_agents_rule": sum(1 for p in pts if not p["indian"] and p.get("indian_relevant")),
            "references_dropped": sum(r["references_dropped"] for r in rows),
            "references_out_of_scope": sum(1 for p in pts for x in p["references"] if not x["in_scope"]),
            "points_out_of_scope": sum(1 for p in pts if p["out_of_scope"])}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", default="http://127.0.0.1:7000")
    ap.add_argument("--password", required=True)
    ap.add_argument("--user", default="admin")
    ap.add_argument("--cases", default="TB-001,TB-002,TB-003,TB-004,TB-005,TB-006")
    ap.add_argument("--roles", default=",".join(ROLES))
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    out = Path(a.out or config.DATA_ROOT / "eval" / "v1" / "agent_refs"); out.mkdir(parents=True, exist_ok=True)
    c = httpx.Client(base_url=a.base, timeout=600)
    if c.post("/api/auth/login", json={"username": a.user, "password": a.password}).status_code != 200:
        sys.exit("login failed")
    from tumour_board import agents, packs  # the pack search for the "whenever one exists" column (the cached guideline index, CPU)
    rows = []
    for case_id in a.cases.split(","):
        protocol_id = (c.get(f"/api/tb/cases/{case_id}").json().get("case") or {}).get("protocol")
        for role in a.roles.split(","):
            brief, err, secs = run_brief(c, case_id, role)
            row = {"case": case_id, "role": role, "error": err, "seconds": round(secs, 1), "points": [],
                   "references_dropped": (brief or {}).get("references_dropped", 0), "checklist": ((brief or {}).get("pack") or {}).get("checklist")}
            for p in (brief or {}).get("points_for_review") or []:
                refs = p.get("references") or []
                ind = next((r for r in refs if r["region"] == "India"), None)
                item = {"text": p["text"], "references": [{**{k: r[k] for k in ("org", "title", "page", "region", "by", "quote")},
                                                           "in_scope": agents._in_scope(r["quote"])} for r in refs],
                        "indian": ind["by"] if ind else None, "out_of_scope": bool(agents._POINT_SCOPE.search(p["text"]))}
                if not ind:
                    hits = packs.search(role, p["text"], protocol_id, india=3, intl=0)["india"]
                    item["pack_indian_hits"] = [{"org": h["org"], "title": h["title"], "page": h["page"], "text": h["text"][:300]} for h in hits]
                    # the agents' own rule (two shared content words or an acronym, same cancer): by construction this is the rule the brief
                    # applied, so it checks the wiring, not relevance; relevance is judged by a person from the list at the end of the report
                    item["indian_relevant"] = bool(agents._indian_reference(role, {"protocol": protocol_id}, p["text"]))
                row["points"].append(item)
            rows.append(row)
            print(f"{case_id} {role:19} {'ERROR ' + str(err) if err else ''} points {len(row['points'])} "
                  f"Indian {sum(1 for p in row['points'] if p['indian'])} ({secs:.0f} s)", flush=True)
    summary = summarise(rows)
    (out / "agent_refs_eval.json").write_text(json.dumps({"summary": summary, "briefs": rows}, indent=2))
    md = ["# Agent guideline references (V1 item 5.5)", "", "| Metric | Value |", "|---|---|"] + [f"| {k} | {v} |" for k, v in summary.items()]
    md += ["", "| Case File | Agent | Points | With Indian reference (agent / search) | Checklist |", "|---|---|---|---|---|"]
    for r in rows:
        ind = [p["indian"] for p in r["points"] if p["indian"]]
        md.append(f"| {r['case']} | {r['role']} | {len(r['points'])}{' (error: ' + str(r['error']) + ')' if r['error'] else ''} | "
                  f"{len(ind)} ({ind.count('agent')} / {ind.count('search')}) | {(r['checklist'] or {}).get('title', '-')} |")
    md += ["", "## Points without an Indian reference", ""]
    for r in rows:
        for p in r["points"]:
            if not p["indian"]:
                found = "; ".join(f"{h['org']} p. {h['page']}" for h in p.get("pack_indian_hits") or []) or "none"
                md.append(f"- {r['case']} {r['role']}: {p['text']} (relevant Indian passage: {'yes' if p.get('indian_relevant') else 'no'}; "
                          f"top Indian pack passages: {found})")
    md += ["", "## Every reference, for a person to judge (relevant to the point? about records, not treatment?)", ""]
    for r in rows:
        for p in r["points"]:
            for x in p["references"]:
                md.append(f"- {r['case']} {r['role']} | {p['text']} | {x['region']}, {x['org']}, {x['title']} {x['page']} ({x['by']}): \"{x['quote']}\"")
    (out / "agent_refs_eval.md").write_text("\n".join(md) + "\n")
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()
