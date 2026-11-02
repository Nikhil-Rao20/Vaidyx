"""Unit tests of the pure parts of docs/night-v3/tools/make_history.py (night-v3 item 7.4, the synthetic decided history).

No network, no login, no data/ access: the script is loaded with every httpx entry point made to raise, and no test calls the functions that
read the demo login files (they are only read as source, with the ast module)."""
import ast
import importlib.util
import re
from datetime import date, timedelta
from pathlib import Path

import httpx
import pytest

from tumour_board import decision_record, postboard

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "docs" / "night-v3" / "tools" / "make_history.py"
SOURCE = SCRIPT.read_text(encoding="utf-8")
TREE = ast.parse(SOURCE)

ALLOWED_NAMED = {"TB-P01-BOARD", "TB-DEMO-P19", "TB-2026-0002", "TB-2026-0005", "TB-2026-0006", "TB-2026-0007", "TB-2026-0008"}
FORBIDDEN = re.compile(r"^(TB-00[1-8]$|TB-TEST$|E2E-)|bharath", re.I)
FORBIDDEN_WORDS = ("recommend", "consider", "suggest", "do the same", "treat as", "best match")
TODAYS = (date(2026, 10, 15), date(2026, 10, 16), date(2026, 10, 27), date(2026, 11, 30))


def _no_network(*a, **k):
    raise AssertionError("a network call was made")


class _NoClient:
    def __init__(self, *a, **k):
        raise AssertionError("an httpx client was built")


def _block_httpx(monkeypatch):
    monkeypatch.setattr(httpx, "Client", _NoClient)
    monkeypatch.setattr(httpx, "AsyncClient", _NoClient)
    for name in ("get", "post", "put", "request", "stream"):
        monkeypatch.setattr(httpx, name, _no_network)


@pytest.fixture(scope="module")
def mh():
    """The script, loaded as a file with httpx blocked: importing must make no call."""
    mp = pytest.MonkeyPatch()
    try:
        _block_httpx(mp)
        spec = importlib.util.spec_from_file_location("make_history", SCRIPT)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
    finally:
        mp.undo()
    return mod


def _strings():
    """Every fixed string of the script (docstrings and the parts of f-strings included)."""
    return [n.value for n in ast.walk(TREE) if isinstance(n, ast.Constant) and isinstance(n.value, str)]


def _walk_text(node):
    for n in ast.walk(node):
        if isinstance(n, ast.Name):
            yield n.id
        elif isinstance(n, ast.Attribute):
            yield n.attr
        elif isinstance(n, ast.Constant) and isinstance(n.value, str):
            yield n.value


def _function_of(node_target):
    """Name of the function (or method) that holds node_target; "" at module level."""
    best = ""
    for f in ast.walk(TREE):
        if isinstance(f, (ast.FunctionDef, ast.AsyncFunctionDef)) and any(n is node_target for n in ast.walk(f)):
            best = f.name
    return best


# ---- 1. the plan table and the ids ----------------------------------------------------------------------------------------------------

def test_import_makes_no_call_and_holds_no_client(mh):
    assert not [k for k, v in vars(mh).items() if isinstance(v, (httpx.Client, httpx.AsyncClient))]
    # and loading it again with every httpx entry point raising is fine (the fixture did it once already)
    mp = pytest.MonkeyPatch()
    try:
        _block_httpx(mp)
        spec = importlib.util.spec_from_file_location("make_history_again", SCRIPT)
        spec.loader.exec_module(importlib.util.module_from_spec(spec))
    finally:
        mp.undo()


def test_plan_rows_shape(mh):
    plan = mh.PLAN
    assert len(plan) >= 13
    ids = [r["id"] for r in plan]
    assert len(set(ids)) == len(ids)
    assert ids[:13] == [f"HIST-{n:02d}" for n in range(1, 14)]
    for r in plan:
        assert re.fullmatch(r"HIST-\d{2}", r["id"])
        for k in ("protocol", "setting", "creator", "meeting"):
            assert r.get(k), (r["id"], k)
        assert r["meeting"] in ("past", "today")
        assert isinstance(r.get("decision"), dict) and r["decision"].get("outcome"), r["id"]
        assert r["decision"].get("responsible_doctor"), r["id"]
        assert r["creator"] == mh.COORDINATOR or r["creator"] in mh.DOCTOR_LOGINS, r["id"]
        assert bool(r.get("slot")) == bool(r.get("uhid")) != bool(r.get("register")), r["id"]  # a seed patient or a run-time registration
        if r.get("uhid"):
            assert mh.SEED_UHID.match(r["uhid"]), r["id"]


def test_only_allowed_case_file_ids(mh):
    named = set(mh.EXISTING_FOR_SUMMARY) | set(mh.ALSO_COUNTED)
    assert set(mh.EXISTING_FOR_SUMMARY) == {"TB-P01-BOARD", "TB-DEMO-P19", "TB-2026-0002"}
    assert named <= ALLOWED_NAMED
    for cid in mh.allowed_ids() | named | {r["id"] for r in mh.PLAN}:
        assert re.fullmatch(r"HIST-\d{2}", cid) or cid in ALLOWED_NAMED, cid
        assert not FORBIDDEN.search(cid), cid
    # no fixed string names the real case or an e2e id (only the pattern that forbids them, which is a regular expression, does)
    for s_ in _strings():
        if "bharath" in s_.lower() and "TB-00[1-8]" in s_:
            continue  # FORBIDDEN_ID itself
        assert "bharath" not in s_.lower() and "TB-TEST" not in s_ and "E2E-" not in s_, s_[:80]
        for token in re.findall(r"\bTB-[A-Za-z0-9-]+", s_):
            assert token in ALLOWED_NAMED, token


def test_check_id_refuses_everything_off_the_list(mh):
    for cid in ("TB-2026-bharath", "TB-001", "TB-008", "TB-TEST", "E2E-1", "E2E-HIST-01", "", None, "HIST-99", "TB-2026-0001", "HIST-01x"):
        with pytest.raises(SystemExit):
            mh.check_id(cid)
    for cid in mh.allowed_ids():
        assert mh.check_id(cid) == cid


def test_select_only_known_ids(mh):
    rows, ex = mh.select("")
    assert len(rows) == len(mh.PLAN) and ex == list(mh.EXISTING_FOR_SUMMARY)
    rows, ex = mh.select("HIST-01, HIST-04,TB-P01-BOARD")
    assert [r["id"] for r in rows] == ["HIST-01", "HIST-04"] and ex == ["TB-P01-BOARD"]
    for bad in ("TB-2026-bharath", "TB-001", "TB-2026-0005", "HIST-99"):
        with pytest.raises(SystemExit):
            mh.select(bad)


# ---- 2. every decision body passes the meeting route's strict clean --------------------------------------------------------------------

@pytest.mark.parametrize("today", TODAYS)
def test_every_decision_body_passes_strict_clean(mh, today):
    for row in mh.PLAN:
        body = mh.decision_body(row, today)
        clean = decision_record.clean({**body, "outcome": str(body.get("outcome") or "decision").strip()}, strict=True)  # as meetings._record_decision
        assert clean["outcome"] == row["decision"]["outcome"], row["id"]
        assert not decision_record.missing_required(clean), row["id"]
        board = mh.meeting_date(row["meeting"], today)
        assert not postboard.informed_date_problem({**clean, "board_date": board}), row["id"]
        if clean["outcome"] == "decision":
            assert len(clean["decision_text"]) >= decision_record.MIN_DECISION
            assert clean["intent"] in ("curative", "palliative")
            assert clean["modalities"], row["id"]
            assert clean["responsible_doctor"] == row["decision"]["responsible_doctor"]
        assert clean["members_present"] and row["decision"]["responsible_doctor"] in clean["members_present"]
        assert len(set(clean["members_present"])) == len(clean["members_present"])
        assert clean["informed_by"] == row["decision"]["responsible_doctor"]


def test_deferred_row_has_what_is_awaited(mh):
    rows = [r for r in mh.PLAN if r["decision"]["outcome"] == "deferred"]
    assert [r["id"] for r in rows] == ["HIST-08"]
    body = mh.decision_body(rows[0], date(2026, 10, 27))
    assert body["outcome"] == "deferred" and body["awaited"] and body["awaited_from"]
    clean = decision_record.clean(body, strict=True)
    assert clean["awaited"] and clean["awaited_from"]
    assert clean["deferred_reason"].startswith(clean["awaited"])
    # a deferred outcome that lost either field would be refused by the route
    for k in ("awaited", "awaited_from"):
        with pytest.raises(ValueError):
            decision_record.clean({kk: v for kk, v in body.items() if kk != k}, strict=True)


def test_decision_rows_carry_no_empty_required_fields(mh):
    for row in mh.PLAN:
        d = row["decision"]
        if d["outcome"] == "decision":
            assert d["decision_text"] and d["intent"] in ("curative", "palliative") and d["modalities"], row["id"]
            ids = {c["id"] for c in decision_record.CHOICES["modalities"]}
            assert set(d["modalities"]) <= ids, row["id"]


# ---- 3. the date rules -----------------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("today", TODAYS)
def test_date_rules(mh, today):
    for row in mh.PLAN:
        body = mh.decision_body(row, today)
        board = date.fromisoformat(mh.meeting_date(row["meeting"], today))
        inform_by = date.fromisoformat(body["inform_by_date"])
        told = date.fromisoformat(body["patient_informed_date"])
        nxt = date.fromisoformat(body["next_step_date"])
        assert inform_by >= board, row["id"]
        assert told >= board, row["id"]
        assert board <= nxt <= board + timedelta(days=14), row["id"]
        assert nxt > board
        if today >= board:  # the patient is never told on a day still ahead
            assert told <= max(today, board), row["id"]


def test_meeting_dates_and_titles(mh):
    assert mh.meeting_date("past", date(2026, 10, 27)) == "2026-10-15"
    assert mh.meeting_date("today", date(2026, 10, 27)) == "2026-10-27"
    assert mh.meeting_title("past", date(2026, 10, 27)) == "History (SYNTHETIC) 15/10/2026"
    assert mh.meeting_title("today", date(2026, 10, 27)) == "History (SYNTHETIC) 27/10/2026"
    assert "SYNTHETIC" in mh.TITLE


# ---- 4. wording ------------------------------------------------------------------------------------------------------------------------

def test_no_em_or_en_dash_in_the_script():
    assert "—" not in SOURCE
    assert "–" not in SOURCE


def test_no_advice_wording_in_fixed_strings():
    for s in _strings():
        low = s.lower()
        for w in FORBIDDEN_WORDS:
            assert w not in low, (w, s[:80])


def test_built_decision_bodies_have_no_advice_wording(mh):
    for row in mh.PLAN:
        text = " ".join(str(v) for v in mh.decision_body(row, date(2026, 10, 27)).values()).lower()
        for w in FORBIDDEN_WORDS:
            assert w not in text, (row["id"], w)


def test_registered_names_end_with_synthetic(mh):
    names = [r["register"]["name"] for r in mh.PLAN if r.get("register")]
    assert len(names) >= 2
    for n in names:
        assert n.endswith("(SYNTHETIC)"), "a registered name does not end with (SYNTHETIC)"


def test_discharge_summaries_say_synthetic(mh):
    summaries = [r["post_board"] for r in mh.PLAN if r.get("post_board") and r["post_board"]["kind"] == "discharge_summary"]
    assert summaries
    for pb in summaries:
        assert "SYNTHETIC" in pb["diagnosis"]
        assert "SYNTHETIC" in pb["course"]
        assert "SYNTHETIC" in pb["advice"]
        assert "SYNTHETIC" in " ".join([pb["diagnosis"], mh.discharge_course(pb), pb["advice"]])
        # the treatment received joins the course and nothing else is lost
        assert pb["course"] in mh.discharge_course(pb) and pb["treatment_received"] in mh.discharge_course(pb)


def test_reports_after_the_board_say_synthetic(mh):
    for r in mh.PLAN:
        pb = r.get("post_board")
        if pb and pb["kind"] == "report":
            for _, values in pb["tests"]:
                assert "SYNTHETIC" in " ".join(str(v) for v in values.values()), r["id"]


def test_opd_notes_say_synthetic(mh):
    notes = [(r["id"], blk["note"]) for r in mh.PLAN for blk in r.get("his_before") or [] if blk.get("note")]
    assert notes
    for cid, note in notes:
        assert "SYNTHETIC" in " ".join(str(v) for v in note.values()), cid


def test_every_hist_row_names_its_cancer_and_setting_in_plain_words(mh):
    for r in mh.PLAN:
        assert re.fullmatch(r"[a-z_]+", r["protocol"]) and re.fullmatch(r"[a-z_]+", r["setting"]), r["id"]
        if r["protocol"] == "generic":
            assert r.get("cancer_name"), r["id"]


# ---- 5. the dry run is pure ------------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("today", (None, date(2026, 10, 27)))
def test_plan_lines_pure_and_complete(mh, monkeypatch, today):
    _block_httpx(monkeypatch)
    for fn in ("demo_password", "his_write_token", "his_login_password"):  # the dry run never reads a secret
        monkeypatch.setattr(mh, fn, _no_network)
    lines = mh.plan_lines(mh.PLAN, mh.EXISTING_FOR_SUMMARY, today)
    text = "\n".join(lines)
    for r in mh.PLAN:
        assert any(line.startswith(f"{r['id']}: ") for line in lines), r["id"]
        assert f"/cases/{r['id']}/decision" in text and f"/api/tb/cases/{r['id']}/case-summary" in text, r["id"]
    for cid in mh.EXISTING_FOR_SUMMARY:
        assert any(line.startswith(f"{cid}: ") for line in lines), cid
    assert "HIST-08" in text and "awaited MRI pelvis report from Radiology" in text
    assert "/archive" in text and "HIST-06" in text.split("/archive")[0]
    assert not [x for x in lines if not x.strip()]


def test_plan_lines_hold_no_secret_and_no_full_uhid(mh):
    text = "\n".join(mh.plan_lines(mh.PLAN, mh.EXISTING_FOR_SUMMARY, date(2026, 10, 27)))
    low = text.lower()
    assert "password" not in low and "bearer" not in low and "write_token" not in low and "authorization" not in low
    assert not re.search(r"VXH/\d{2}/\d+", text)
    assert not re.search(r"\d{6}", text.replace("VXREG", ""))  # no registration number or UHID tail
    for r in mh.PLAN:
        if r.get("uhid"):
            assert r["uhid"] not in text and r["uhid"].split("/")[-1] not in text
        if r.get("register"):
            assert r["register"]["name"] not in text
    assert re.search(r"seed P\d{2}", text)
    for forbidden in ("bharath", "TB-2026-bharath", "E2E-"):
        assert forbidden not in text


def test_plan_lines_for_a_subset(mh, monkeypatch):
    _block_httpx(monkeypatch)
    rows, ex = mh.select("HIST-04,TB-DEMO-P19")
    lines = mh.plan_lines(rows, ex, date(2026, 10, 27))
    assert lines[0].startswith("HIST-04: ")
    assert any(x.startswith("TB-DEMO-P19: ") for x in lines)
    assert not any("HIST-01" in x for x in lines)


def test_main_dry_run_sends_nothing(mh, monkeypatch, capsys):
    _block_httpx(monkeypatch)
    for fn in ("demo_password", "his_write_token", "his_login_password"):
        monkeypatch.setattr(mh, fn, _no_network)
    assert mh.main(["--dry-run"]) == 0
    out = capsys.readouterr().out
    assert f"{len(mh.PLAN)} plan rows, {len(mh.EXISTING_FOR_SUMMARY)} existing files; nothing is sent" in out
    assert "password" not in out.lower() and "bearer" not in out.lower()
    assert mh.main(["--dry-run", "--only", "HIST-01"]) == 0
    assert "1 plan rows" in capsys.readouterr().out


# ---- 6. secrets: where they are read, and that nothing prints them ------------------------------------------------------------------------

def test_login_files_are_read_only_by_the_two_readers():
    holders = {}
    for n in ast.walk(TREE):
        if isinstance(n, ast.Name) and n.id == "DEMO_LOGINS" and isinstance(n.ctx, ast.Load):
            holders.setdefault("DEMO_LOGINS", set()).add(_function_of(n))
        if isinstance(n, ast.Constant) and n.value == "logins.tsv":
            holders.setdefault("logins.tsv", set()).add(_function_of(n))
    assert holders["DEMO_LOGINS"] == {"demo_password"}
    assert holders["logins.tsv"] == {"his_login_password"}
    readers = set()
    for n in ast.walk(TREE):
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr in ("read_text", "read_bytes", "open"):
            readers.add(_function_of(n))
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "open":
            readers.add(_function_of(n))
    # the two login readers, the HIS write token reader, and the run's own state file; nothing else reads a file
    assert {"demo_password", "his_login_password"} <= readers
    assert readers <= {"demo_password", "his_login_password", "his_write_token", "_load_state"}


def test_secret_readers_are_called_only_to_sign_in():
    callers = {}
    for n in ast.walk(TREE):
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in ("demo_password", "his_login_password", "his_write_token"):
            callers.setdefault(n.func.id, set()).add(_function_of(n))
    assert callers["demo_password"] == {"login"}
    assert callers["his_login_password"] == {"his_screen"}
    assert callers["his_write_token"] == {"his"}


def test_no_print_carries_a_secret():
    prints = 0
    for n in ast.walk(TREE):
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "print":
            prints += 1
            for arg in list(n.args) + [k.value for k in n.keywords]:
                for text in _walk_text(arg):
                    low = str(text).lower()
                    assert "password" not in low and "token" not in low and "bearer" not in low, f"line {n.lineno}: {low[:60]}"
    assert prints >= 10


def test_no_failure_message_interpolates_a_secret():
    """Failed and SystemExit messages may say the word "token" (a file is missing) but never fill in a value that holds one."""
    seen = 0
    for n in ast.walk(TREE):
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in ("Failed", "SystemExit"):
            seen += 1
            for part in ast.walk(n):
                if isinstance(part, ast.FormattedValue):
                    for t in _walk_text(part.value):
                        low = str(t).lower()
                        assert "password" not in low and "token" not in low and "bearer" not in low and "secret" not in low, f"line {n.lineno}: {low[:60]}"
    assert seen >= 10


def test_report_rows_hold_ids_protocol_and_slots_only():
    init = next(f for f in ast.walk(TREE) if isinstance(f, ast.FunctionDef) and f.name == "__init__"
                and any(a.arg == "rows" for a in f.args.args))
    keys = {k.value for n in ast.walk(init) if isinstance(n, ast.Dict) for k in n.keys if isinstance(k, ast.Constant) and isinstance(k.value, str)}
    assert {"id", "slot", "protocol", "setting", "creator", "meeting", "steps"} <= keys
    assert not keys & {"password", "token", "name", "uhid", "identifier"}
