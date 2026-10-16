"""dates.doc_dates: the one reader of a document's dates (V1 item 3.1, refactor step a)."""
from tumour_board import dates, postboard, rules, store
from tumour_board.tests.util import add, make_doc


def test_report_only_stands_in_for_event():
    d = dates.doc_dates({"classification": {"report_date_iso": "2026-09-04"}})
    assert d["report"] == d["event"] == "2026-09-04" and d["event_assumed"] and not d["report_assumed"] and not d["unconfirmed"]
    assert d["sort"] == ("2026-09-04", "2026-09-04")


def test_event_only_stands_in_for_report():
    d = dates.doc_dates({"classification": {"event_date_iso": "2026-09-02"}})
    assert d["report"] == d["event"] == "2026-09-02" and d["report_assumed"] and not d["event_assumed"]


def test_both_dates_kept_apart_and_sorted_by_event():
    d = dates.doc_dates({"classification": {"report_date_iso": "2026-09-03", "event_date_iso": "2026-09-02"}})
    assert (d["report"], d["event"]) == ("2026-09-03", "2026-09-02") and not d["report_assumed"] and not d["event_assumed"]
    assert d["sort"] == ("2026-09-02", "2026-09-03")


def test_no_date_is_unconfirmed():
    d = dates.doc_dates({"classification": {}})
    assert d["unconfirmed"] and d["report"] == d["event"] == "" and d["sort"] == ("", "")
    assert dates.doc_dates({})["unconfirmed"]
    assert dates.doc_dates({"classification": {"report_date_iso": "2026-09-04", "date_unconfirmed": True}})["unconfirmed"]


def test_flags_passed_through():
    assert dates.doc_dates({"classification": {"report_date_iso": "2026-09-04", "date_flags": ["report date is after today"]}})["flags"] == ["report date is after today"]


def test_rules_order_by_event_then_report_then_status(unit_case):
    a = make_doc("Dlab00001", "lab", date="2026-09-01"); a["classification"]["event_date_iso"] = "2026-09-05"
    b = make_doc("Dlab00002", "lab", date="2026-09-04")
    assert rules._doc_sort_key(a) > rules._doc_sort_key(b)  # a's event date is later although its report date is earlier
    c = make_doc("Dlab00003", "lab", date="2026-09-04", status="PRELIMINARY")
    assert rules._doc_sort_key(b) > rules._doc_sort_key(c)


def test_timeline_uses_event_date(unit_case):
    d = make_doc("Dct000001", "ct", region="chest", date="2026-09-03"); d["classification"]["event_date_iso"] = "2026-09-02"
    add(unit_case, d)
    ev = [e for e in postboard.timeline(unit_case) if e["kind"] == "document"]
    assert ev[0]["date"] == "2026-09-02" and ev[0]["report_date"] == "2026-09-03" and ev[0]["date_assumed"] is False


def test_resolve_facts_history_carries_both_dates(unit_case):
    from tumour_board.tests.util import fact
    d = make_doc("Dlab00001", "lab", date="2026-09-04", facts={"haemoglobin": fact("11.8 g/dL")}); d["classification"]["event_date_iso"] = "2026-09-03"
    add(unit_case, d)
    h = rules.resolve_facts(store.list_docs(unit_case))["haemoglobin"]["history"][0]
    assert h["date"] == "2026-09-03" and h["report_date"] == "2026-09-04"
