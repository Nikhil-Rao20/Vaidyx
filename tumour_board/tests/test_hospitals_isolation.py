"""Two hospitals in one app never mix (admin consoles, 16 Nov 2026, DESIGN section 9): both hold a Case File TB-2026-0001 with different
content, and every reader (list_cases, get_case, list_docs, the search index cache, org.roles, the in-memory maps) sees only the current
hospital's, also from asyncio.to_thread and from a thread started inside contextvars.copy_context. Plus: the live hub rooms, the video
room names, the scheduler's per-hospital state, the restart hook, and the static rules (no import-time data path, no bare thread).
Synthetic data in temporary folders only."""
import ast, asyncio, contextvars, copy, json, threading
from pathlib import Path

import pytest

from tumour_board import config, hospitals, live, org, scheduler, search, service, store, video
from tumour_board.tests import util

REAL_INDEX = search.index  # conftest replaces search.index with a stub; the cache test uses the real function with a light CaseIndex
CID = "TB-2026-0001"
REPO = Path(__file__).resolve().parents[2]


@pytest.fixture
def two(data_root):
    """The default hospital and "lotus", each with TB-2026-0001 (a different patient and record) and its own coordinator."""
    lotus = hospitals.create("Lotus Cancer Centre", by="admin")["id"]
    hospitals.assign("bina", lotus, by="admin")
    o = copy.deepcopy(org.DEFAULT_ORG); o["users"] = {"anil": {"coordinator": True, "display_name": "Anil"}}; org.save(o, by="test")
    store.create_case(CID, {"name": "SYNTHETIC, Default Patient", "mrn": "SYN-000001"}, "lung_nsclc", created_by="anil")
    util.add(CID, util.make_doc("D00000001", "ct", title="DEFAULT CT REPORT"))
    with config.use_hospital(lotus):
        o = copy.deepcopy(org.load()); o["users"] = {"bina": {"coordinator": True, "display_name": "Bina"}}; org.save(o, by="test")
        store.create_case(CID, {"name": "SYNTHETIC, Lotus Patient", "mrn": "SYN-000002"}, "breast", created_by="bina")
        util.add(CID, util.make_doc("D00000002", "mri", title="LOTUS MRI REPORT"), util.make_doc("D00000003", "histopathology"))
    return lotus


def _view():
    """What the current hospital shows: (patients, doc ids, coordinator logins)."""
    return ([c["patient"]["name"] for c in store.list_cases()], [d["doc_id"] for d in store.list_docs(CID)],
            sorted(u for u in org.load()["users"] if org.roles(u).get("coordinator")))


DEFAULT_VIEW = (["SYNTHETIC, Default Patient"], ["D00000001"], ["anil"])
LOTUS_VIEW = (["SYNTHETIC, Lotus Patient"], ["D00000002", "D00000003"], ["bina"])


def test_readers_see_only_their_hospital(two):
    assert config.DATA_ROOT == config.BASE_ROOT and config.CASES_DIR == config.BASE_ROOT / "cases"
    assert _view() == DEFAULT_VIEW and store.get_case(CID)["protocol"] == "lung_nsclc"
    with config.use_hospital(two):
        assert config.DATA_ROOT == config.HOSPITALS_ROOT / two and str(config.CASES_DIR) == str(config.HOSPITALS_ROOT / two / "cases")
        assert _view() == LOTUS_VIEW and store.get_case(CID)["protocol"] == "breast"
        assert not org.roles("anil").get("coordinator") and org.roles("bina")["coordinator"]
    assert _view() == DEFAULT_VIEW  # the docs cache holds both, keyed by hospital
    assert not org.roles("bina").get("coordinator")


def test_threads_and_to_thread_carry_the_hospital(two):
    seen = {}

    def look(tag):
        seen[tag] = _view()

    async def main():
        await asyncio.to_thread(look, "to_thread")
        await asyncio.gather(*[asyncio.to_thread(look, f"many{i}") for i in range(4)])
    with config.use_hospital(two):
        asyncio.run(main())
        t = threading.Thread(target=contextvars.copy_context().run, args=(look, "thread"))
        t.start(); t.join()
    t = threading.Thread(target=contextvars.copy_context().run, args=(look, "default_thread"))
    t.start(); t.join()
    assert seen.pop("default_thread") == DEFAULT_VIEW
    assert seen and all(v == LOTUS_VIEW for v in seen.values()), seen


def test_parallel_threads_never_mix(two):
    """Threads of both hospitals reading at once (the org and docs caches are per file / per hospital)."""
    bad = []

    def worker(hid, want):
        with config.use_hospital(hid):
            for _ in range(60):
                store._docs_cache.clear() if _ % 20 == 0 else None
                if _view() != want:
                    bad.append(hid)
    ts = [threading.Thread(target=worker, args=(h, w)) for h, w in ((two, LOTUS_VIEW), ("default", DEFAULT_VIEW)) * 3]
    [t.start() for t in ts]; [t.join() for t in ts]
    assert not bad


def test_bare_thread_in_strict_mode_raises(two, monkeypatch):
    monkeypatch.setenv("TB_HOSPITAL_STRICT", "1")
    err = []

    def bare():
        try:
            store.list_cases()
        except config.HospitalContextError as e:
            err.append(e)
    t = threading.Thread(target=contextvars.Context().run, args=(bare,))  # an empty context: a thread started without copy_context
    t.start(); t.join()
    assert err, "a thread without the hospital must fail loudly in strict mode"


def test_search_index_cache_is_per_hospital(two, monkeypatch):
    class LightIndex:
        def __init__(self, case_id):
            self.where, self.docs = config.hospital_id(), [d["doc_id"] for d in store.list_docs(case_id)]
    monkeypatch.setattr(search, "CaseIndex", LightIndex)
    monkeypatch.setattr(search, "index", REAL_INDEX)
    search._index_cache.clear()
    a = search.index(CID)
    with config.use_hospital(two):
        b = search.index(CID)
        assert search.index(CID) is b
    assert search.index(CID) is a and (a.where, b.where) == ("default", two)
    assert a.docs == ["D00000001"] and b.docs == ["D00000002", "D00000003"]


def test_scoped_maps(two):
    m, s = config.ScopedDict(), config.ScopedSet()
    m[CID] = "default"; s.add(CID)
    with config.use_hospital(two):
        assert CID not in m and m.get(CID) is None and len(m) == 0 and CID not in s
        m[CID] = "lotus"; m.setdefault("x", 1)
        assert dict(m) == {CID: "lotus", "x": 1} and m.pop(CID) == "lotus"
    assert m == {CID: "default"} and set(s) == {CID} and config.scoped(CID) == ("default", CID)
    m.clear(); s.clear()
    with config.use_hospital(two):
        assert len(m) == 0
    from tumour_board import after_send, agents, case_summary, helpers, meeting_notes, meetings, pacs, ready_hook, steps
    for mp in (store._docs_cache, store._locks, search._index_cache, after_send._CHECKS, steps._COUNTS, agents._WARM, case_summary.RUNNING,
               case_summary.AGAIN, ready_hook.RUNNING, ready_hook.AGAIN, helpers.PREPARING, meetings.LIVE_DECISION, meetings.AGENT_STATE,
               meetings.AGENT_AUDIO, meetings.AGENT_LISTEN, meetings.AGENT_LOCKS, meetings._TASKS_BY_MID, meetings._ANSWERING,
               meetings._RECORDING, meetings._REACTED, meetings._CHATTED, meeting_notes._PENDING, meeting_notes._RUNNING,
               service.SESSION_TASKS, service.JOBS, pacs._grants, pacs._access_cache, scheduler._state, scheduler._refetch):
        assert isinstance(mp, (config.ScopedDict, config.ScopedSet)), mp


def test_case_summary_and_ready_hook_threads_keep_the_hospital(two, monkeypatch):
    """With no event loop the background runs go to a thread: it runs in the hospital that asked."""
    from tumour_board import case_summary, ready_hook
    got, done = [], threading.Event()

    async def fake_run(case_id, *a, **kw):
        got.append((config.hospital_id(), store.get_case(case_id)["protocol"]))
        case_summary.RUNNING.pop(case_id, None)
        if len(got) == 2:
            done.set()
    monkeypatch.setattr(case_summary, "_run", fake_run)
    monkeypatch.setattr(ready_hook, "run", fake_run)
    monkeypatch.setattr(case_summary, "enabled", lambda: True)
    monkeypatch.setattr(ready_hook, "enabled", lambda: True)
    monkeypatch.setattr(ready_hook, "_take_needs_again", lambda cid: None)
    with config.use_hospital(two):
        assert case_summary.schedule(CID, {"kind": "test"})["how"] == "thread"
        assert ready_hook.on_ready(CID, "bina")["how"] == "thread"
    assert done.wait(10) and got == [(two, "breast"), (two, "breast")]


def test_live_rooms_are_per_hospital(two):
    live.hub.clear()
    a, b = object(), object()
    live.hub.connect("S20261117-ab12", a, "anil")
    with config.use_hospital(two):
        live.hub.connect("S20261117-ab12", b, "bina")
        assert live.hub.clients("S20261117-ab12") == [b] and live.online("S20261117-ab12") == ["bina"] and live.hub.online_users() == ["bina"]
    assert live.hub.clients("S20261117-ab12") == [a] and live.hub.online_users() == ["anil"] and live.hub.count("S20261117-ab12") == 1
    live.hub.disconnect("S20261117-ab12", a)
    with config.use_hospital(two):
        assert live.hub.count("S20261117-ab12") == 1
    live.hub.clear()


def test_video_room_names(two):
    assert video.room_name("S20261117-ab12") == "tb-S20261117-ab12"  # the default hospital keeps its names
    with config.use_hospital(two):
        assert video.room_name("S20261117-ab12") == f"tb-{two}-S20261117-ab12"


def test_shared_things_stay_in_the_base_folder(two):
    from tumour_board import pubmed, push, site_mail
    from tumour_board.api import site
    with config.use_hospital(two):
        assert video.keys_path() == config.BASE_ROOT / "livekit.json" and push._path(push.KEYS_FILE) == config.BASE_ROOT / "push_keys.json"
        assert push._path(push.SUBS_FILE) == config.HOSPITALS_ROOT / two / "push_subs.json"
        assert site_mail.config_path() == config.BASE_ROOT / "site_mail.json" and site.enquiries_dir() == config.BASE_ROOT / "enquiries"
        (config.BASE_ROOT / "models.json").write_text(json.dumps({"reader": {"label": "shared reader"}}))
        assert config.models()["reader"]["label"] == "shared reader"
    for p in (config.AUDIO_TOKEN_FILE, pubmed.CACHE_DIR, pubmed.SETTINGS):  # fixed at import, never a hospital's folder
        assert config.HOSPITALS_ROOT not in Path(p).parents


def test_websocket_enters_the_login_hospital(two):
    from tumour_board.api.live import enter_hospital

    class Auth:
        def is_admin(self, u):
            return u == "admin"

    class WS:
        def __init__(self, headers=None, query=None):
            self.headers, self.query_params = headers or {}, query or {}
            self.app = type("App", (), {"state": type("S", (), {"auth_manager": Auth()})()})()

    def where(user, ws):
        out = []
        ctx = contextvars.Context()
        ok = ctx.run(lambda: enter_hospital(ws, user) and out.append(config.hospital_id()) is None)
        return out[0] if ok else None
    assert where("bina", WS()) == two and where("anil", WS()) == "default"
    assert where("anil", WS({"x-tb-hospital": two}, {"hospital": two})) == "default"  # ignored for anyone but a Vaidyx admin
    assert where("admin", WS({}, {"hospital": two})) == two and where("admin", WS({"x-tb-hospital": two})) == two
    from tumour_board.api.live import still_in_hospital
    with config.use_hospital(two):
        assert still_in_hospital(WS(), "bina") and not still_in_hospital(WS(), "anil")
    hospitals.set_status(two, "suspended", by="admin", reason="paused")
    assert where("bina", WS()) is None and where("admin", WS({}, {"hospital": two})) == two
    with config.use_hospital(two):
        assert not still_in_hospital(WS(), "bina")  # an open socket closes at its next re-check


def test_scheduler_ticks_every_active_hospital(two):
    scheduler._state.clear(); scheduler._refetch.clear()
    out = scheduler.tick_all(force=True, only=("codes", "prune"))
    assert set(out) == {"default", two} and all(set(r) == {"codes", "prune"} for r in out.values())
    assert (config.BASE_ROOT / "scheduler.json").exists() and (config.HOSPITALS_ROOT / two / "scheduler.json").exists()
    with config.use_hospital(two):
        assert scheduler._state["ticks"] == 1 and scheduler.status()["ticks"] == 1
    hospitals.set_status(two, "suspended", by="admin", reason="paused")
    assert set(scheduler.tick_all(force=True, only=("codes",))) == {"default"}
    assert scheduler._state["ticks"] == 2
    with config.use_hospital(two):
        assert scheduler._state["ticks"] == 1
    scheduler._state.clear()


def test_scheduler_jobs_on_the_app_loop_keep_the_hospital(two, monkeypatch):
    """A quick job handed from the scheduler thread to the app's loop runs in the hospital of the tick."""
    loop = asyncio.new_event_loop()
    t = threading.Thread(target=loop.run_forever, daemon=True)
    t.start()
    try:
        monkeypatch.setattr(scheduler, "app_loop", lambda: loop)
        with config.use_hospital(two):
            assert scheduler._run(lambda now: (config.hospital_id(), _view()), None) == (two, LOTUS_VIEW)
        assert scheduler._run(lambda now: (config.hospital_id(), _view()), None) == ("default", DEFAULT_VIEW)
    finally:
        loop.call_soon_threadsafe(loop.stop)
        t.join(5)
        loop.close()


def test_resume_after_restart_visits_every_hospital(two, monkeypatch):
    seen = []

    def one():
        seen.append(config.hospital_id())
        return {"requeued": {CID: ["D1"]} if config.hospital_id() == two else {}, "interrupted_jobs": [], "pruned": 0}
    monkeypatch.setattr(service, "_resume_one", one)
    out = service.resume_after_restart()
    assert seen == ["default", two] and out == {"requeued": {}, "interrupted_jobs": [], "pruned": 0,
                                                "hospitals": {two: {"requeued": {CID: ["D1"]}, "interrupted_jobs": [], "pruned": 0}}}
    monkeypatch.undo()
    assert service.resume_after_restart() == {"requeued": {}, "interrupted_jobs": [], "pruned": 0}  # nothing anywhere: the old answer


def test_single_hospital_restart_answer_is_unchanged(data_root):
    assert set(service.resume_after_restart()) == {"requeued", "interrupted_jobs", "pruned"}


# ---- static rules -------------------------------------------------------------------------------------------------------------

IMPORT_TIME_ALLOWED = {"tumour_board/eval/gate_summary.py"}  # a command-line script: run in the default hospital
THREAD_ALLOWED = {"tumour_board/scheduler.py",  # one thread for every hospital: each tick enters each hospital (tick_all)
                  "tumour_board/eval/e2e_nik.py"}  # a test script reading a socket, no data folder


def _py_files():
    for p in sorted((REPO / "tumour_board").rglob("*.py")):
        rel = p.relative_to(REPO).as_posix()
        if "/tests/" not in rel:
            yield rel, ast.parse(p.read_text(encoding="utf-8"))


def _import_time_nodes(tree):
    """Nodes evaluated at import: everything outside function bodies (decorators and default values included)."""
    todo = list(ast.iter_child_nodes(tree))
    while todo:
        n = todo.pop()
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            todo.extend(n.decorator_list + n.args.defaults + [d for d in n.args.kw_defaults if d is not None])
            continue
        if isinstance(n, ast.Lambda) or (isinstance(n, ast.If) and "__main__" in ast.unparse(n.test)):  # a script's own start
            continue
        yield n
        todo.extend(ast.iter_child_nodes(n))


def _is_root(n):
    if isinstance(n, ast.Call) and getattr(n.func, "id", "") == "Path" and n.args:
        n = n.args[0]
    return isinstance(n, ast.Attribute) and n.attr in ("DATA_ROOT", "CASES_DIR") and getattr(n.value, "id", "") == "config"


def test_no_import_time_data_paths():
    bad = [f"{rel}:{n.lineno}" for rel, tree in _py_files() if rel not in IMPORT_TIME_ALLOWED
           for n in _import_time_nodes(tree) if isinstance(n, ast.BinOp) and isinstance(n.op, ast.Div) and _is_root(n.left)]
    assert not bad, f"config.DATA_ROOT / ... at import time pins one hospital's folder: {bad}"


def _copied_context(target):
    return isinstance(target, ast.Attribute) and target.attr == "run" and isinstance(target.value, ast.Call) \
        and getattr(target.value.func, "attr", getattr(target.value.func, "id", "")) == "copy_context"


def test_no_bare_threads():
    bad = []
    for rel, tree in _py_files():
        if rel in THREAD_ALLOWED:
            continue
        for n in ast.walk(tree):
            if isinstance(n, ast.Call) and (getattr(n.func, "attr", None) == "Thread" or getattr(n.func, "id", None) == "Thread"):
                target = next((k.value for k in n.keywords if k.arg == "target"), n.args[1] if len(n.args) > 1 else None)
                if not _copied_context(target):
                    bad.append(f"{rel}:{n.lineno}")
    assert not bad, f"a thread must start inside contextvars.copy_context().run (it carries the hospital): {bad}"
