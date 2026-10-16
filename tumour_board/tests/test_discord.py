"""Discordances between reports and the decision watch (12 Oct): plain code over the verified facts; no model."""
import asyncio

from tumour_board import confirm, discord, llm, notify, postboard, rules, store, summary
from tumour_board.tests.util import add, fact, make_doc


def _hist(case, doc_id, value, date, status="FINAL", signed="yes", doc_type="histopathology"):
    add(case, make_doc(doc_id, doc_type, status=status, signed=signed, date=date, facts={"histologic_type": fact(value)},
                       text=f"SYNTHETIC\n{doc_type.upper()} REPORT\n{value}\nReport status: {status}"))


def test_same_value_wording_numbers_and_polarity():
    assert discord.same("Adenocarcinoma", "Adenocarcinoma, acinar predominant")
    assert discord.same("TPS 60%", "PD-L1 TPS 60 %")
    assert not discord.same("TPS 60%", "TPS 6%")
    assert not discord.same("HER2 positive", "HER2 negative")
    assert discord.same("2.45 lakhs/cumm", "245 x10^3/uL")
    assert not discord.same("Adenocarcinoma", "Squamous cell carcinoma")
    assert not discord.same("Adenocarcinoma", "Non-small cell carcinoma, favour adenocarcinoma")
    assert not discord.same("mrT3b N1", "mrT3c N1", "recorded_stage") and discord.same("cT3 N2 M0", "cT3 N2 M0, Stage IIIB (AJCC 8th)", "recorded_stage")
    assert discord.same("ECOG 1", "ECOG performance status: 1") and not discord.same("ECOG 1", "ECOG 2")


def test_stable_field_differing_between_final_reports_is_for_review(unit_case):
    _hist(unit_case, "Dh1", "Squamous cell carcinoma", "2026-08-01")
    _hist(unit_case, "Dh2", "Adenocarcinoma", "2026-09-10")
    its = discord.items(unit_case)
    assert len(its) == 1 and its[0]["kind"] == "conflict" and its[0]["severity"] == "review" and its[0]["field"] == "histologic_type"
    assert {c["doc_id"] for c in its[0]["citations"]} == {"Dh1", "Dh2"} and all(c["quote"] for c in its[0]["citations"])
    s = discord.summary(unit_case)
    assert s["open_review"] == 1 and s["info"] == 0


def test_amended_report_and_non_final_report_are_named(unit_case):
    _hist(unit_case, "Dh1", "Non-small cell carcinoma, favour adenocarcinoma", "2026-09-08")
    _hist(unit_case, "Dh2", "Adenocarcinoma", "2026-09-18", status="AMENDED")
    _hist(unit_case, "Dh3", "Small cell carcinoma", "2026-09-20", status="DRAFT", signed="no")
    kinds = {it["kind"]: it for it in discord.items(unit_case)}
    assert "amended" in kinds and kinds["amended"]["citations"][1]["doc_id"] == "Dh2" and "amended report" in kinds["amended"]["text"]
    assert "conflict" not in kinds  # the amendment is listed once, not again as a conflict
    nf = kinds["non_final_differs"]
    assert nf["citations"][1]["doc_id"] == "Dh3" and "draft report" in nf["text"] and nf["citations"][0]["doc_id"] == "Dh2"


def test_time_varying_field_is_information_unless_same_date(unit_case):
    add(unit_case, make_doc("Dl1", "lab", date="2026-09-01", facts={"haemoglobin": fact("11.8 g/dL")}, text="SYNTHETIC\nLAB\nHaemoglobin 11.8 g/dL\nReport status: FINAL"))
    add(unit_case, make_doc("Dl2", "lab", date="2026-09-14", facts={"haemoglobin": fact("12.1 g/dL")}, text="SYNTHETIC\nLAB\nHaemoglobin 12.1 g/dL\nReport status: FINAL"))
    its = discord.items(unit_case)
    assert len(its) == 1 and its[0]["kind"] == "changed" and its[0]["severity"] == "info"
    add(unit_case, make_doc("Dl3", "lab", date="2026-09-14", facts={"haemoglobin": fact("9.1 g/dL")}, text="SYNTHETIC\nLAB\nHaemoglobin 9.1 g/dL\nReport status: FINAL"))
    kinds = [it["kind"] for it in discord.items(unit_case)]
    assert "conflict" in kinds  # two final reports of the same date disagree


def test_polarity_flip_is_review_and_note_is_a_confirmation(unit_case):
    add(unit_case, make_doc("Di1", "ihc", date="2026-09-05", facts={"her2": fact("HER2 positive (3+)")}, text="SYNTHETIC\nIHC\nHER2 positive (3+)\nReport status: FINAL"))
    add(unit_case, make_doc("Di2", "ihc", date="2026-09-12", facts={"her2": fact("HER2 negative")}, text="SYNTHETIC\nIHC\nHER2 negative\nReport status: FINAL"))
    it = discord.items(unit_case)[0]
    assert it["kind"] == "polarity" and it["severity"] == "review"
    rec = confirm.record(unit_case, "note_discordance", it["key"], reason="discussed at the board", by="Dr. Rao")
    noted = discord.items(unit_case)[0]
    assert noted["noted"]["by"] == "Dr. Rao" and noted["noted"]["note"] == "discussed at the board" and discord.summary(unit_case)["open_review"] == 0
    assert discord.points(unit_case) == []  # noted items leave the points for review
    confirm.undo(unit_case, rec["id"], by="Dr. Rao")
    assert "noted" not in discord.items(unit_case)[0] and discord.summary(unit_case)["open_review"] == 1
    kinds = [e["kind"] for e in store.read_audit(unit_case)]
    assert "confirmation" in kinds and "confirmation_undone" in kinds


def test_points_cite_both_reports_and_text_block_for_agents(unit_case):
    _hist(unit_case, "Dh1", "Squamous cell carcinoma", "2026-08-01")
    _hist(unit_case, "Dh2", "Adenocarcinoma", "2026-09-10")
    pts = discord.points(unit_case)
    assert len(pts) == 1 and pts[0]["from_rules"] and {c["doc_id"] for c in pts[0]["citations"]} == {"Dh1", "Dh2"} and all("page" in c for c in pts[0]["citations"])
    assert discord.text(unit_case).startswith("DISCORDANCES FOUND BY THE SYSTEM") and "Adenocarcinoma" in discord.text(unit_case)


def test_decision_watch_flags_a_later_report_and_notifies_coordinators_once(unit_case, monkeypatch):
    _hist(unit_case, "Dh1", "Non-small cell carcinoma, favour adenocarcinoma", "2026-09-08")
    rules.evaluate(unit_case)

    async def fake_chat(role, msgs, **kw):
        return {"claims": [{"fact": "histologic_type", "value_as_written": "Non-small cell carcinoma, favour adenocarcinoma", "span": "Non-small cell carcinoma, favour adenocarcinoma"}]}
    monkeypatch.setattr(llm, "chat", fake_chat); monkeypatch.setattr(postboard.llm, "chat", fake_chat)
    rec = asyncio.run(postboard.record_decision(unit_case, {"board_date": "2026-09-10", "decision_text": "Histology Non-small cell carcinoma, favour adenocarcinoma. Plan agreed.",
                                                            "recorded_by": "Dr. A", "participants": "Dr. A (Med Onc), Dr. B (Surg Onc), Dr. C (Rad Onc)"}, user="coord"))
    assert any(v["result"] == "consistent" for v in rec["adjudication"]["value_checks"])
    assert discord.decision_watch(unit_case) == []
    _hist(unit_case, "Dh2", "Adenocarcinoma", "2026-09-18", status="AMENDED")
    w = discord.decision_watch(unit_case)
    assert len(w) == 1 and w[0]["record"] == rec["id"] and "cited Histologic type" in w[0]["text"] and w[0]["citations"][1]["doc_id"] == "Dh2"
    assert discord.notify_decision_watch(unit_case) == 1 and discord.notify_decision_watch(unit_case) == 0  # once
    ns = [n for n in notify._load() if n["kind"] == "decision_value_changed"]
    assert len(ns) == 1 and ns[0]["to"] == {"role": "coordinator"} and ns[0]["case_id"] == unit_case
    assert store.get_state(unit_case)["discord_notified"] == [w[0]["key"]]


def test_summary_appends_discordance_points(unit_case, monkeypatch):
    _hist(unit_case, "Dh1", "Squamous cell carcinoma", "2026-08-01")
    _hist(unit_case, "Dh2", "Adenocarcinoma", "2026-09-10")
    rules.evaluate(unit_case)

    async def fake_chat(role, msgs, **kw):
        return {"sentences": [], "points_for_review": []}
    monkeypatch.setattr(llm, "chat", fake_chat); monkeypatch.setattr(summary.llm, "chat", fake_chat)
    out = asyncio.run(summary.build(unit_case, force=True))
    assert any(p.get("from_rules") and p["kind"] == "conflict" for p in out["points_for_review"])
