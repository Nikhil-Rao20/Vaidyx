"""V2 item 6.2, the service side: when the session starts, the agents run per Case File (a head not recorded present, the Surgical
Oncology agent only where no surgeon fills the seat), and an on-demand agent runs when asked. The agent run is a fake (no model)."""
import asyncio, copy, json

import pytest

from tumour_board import access, agents, board, dept_requests, his_case, metrics, notify, org, postboard, rules, service, store
from tumour_board.tests import util
from tumour_board.tests.test_board_v2 import DATE, COORD, BREAST, MEDONC, RAD, GYN, ADMIN, UNPLACED, _case, _hospital, _decide, cases  # noqa: F401


def test_prepare_session_agents_runs_per_case_file(cases, monkeypatch):
    runs = []

    async def fake(case_id, role, focus="", max_steps=5):
        runs.append((case_id, role))
        brief = {"role": role, "label": agents.ROLES[role]["label"], "generated": f"2026-10-22T09:00:{len(runs):02d}", "model": "fake", "seconds": 0.1,
                 "version": agents.BRIEF_VERSION, "focus": focus, "near_match": False, "sections": [], "points_for_review": [], "not_documented": [],
                 "signature": rules.case_signature(case_id)}
        st = store.get_state(case_id); st.setdefault("artefacts", {})[f"brief_{role}"] = brief; store.save_state(case_id, st)
        yield {"type": "brief", "brief": brief}
    monkeypatch.setattr(agents, "run_agent", fake)
    s = board.create(DATE, "anil", case_ids=["TB-BR", "TB-MO"])
    for d in ("radiology", "medical_oncology"):
        board.set_attendance(s["id"], d, "present", "anil")
    board.add_member(s["id"], "Dr Meera Nair", "breast_surgery", "anil")  # Pathology not recorded: its agent; the surgical seat filled for TB-BR only
    board.start(s["id"], "anil")

    async def go(**kw):
        pairs = service.prepare_session_agents(s["id"], "anil", **kw)
        while service.SESSION_TASKS.get(s["id"]):
            await asyncio.sleep(0.01)
        return pairs
    pairs = asyncio.run(go())
    assert sorted(pairs) == sorted(runs) == [("TB-BR", "pathology"), ("TB-MO", "pathology"), ("TB-MO", "surgical_oncology")]
    pairs = asyncio.run(go(roles=["radiation_oncology"], case_ids=["TB-BR"]))  # on demand: an explicit role runs even when not absent
    assert pairs == [("TB-BR", "radiation_oncology")] and runs[-1] == ("TB-BR", "radiation_oncology")
