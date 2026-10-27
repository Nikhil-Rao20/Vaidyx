"""The in-process scheduler (18 Oct, B3): one daemon thread, a tick every 60 s (TB_SCHEDULER_INTERVAL), every automatic action by
"Vaidyx (automatic)" and audited.

Jobs: re-fetch every 30 min for the HIS-connected, non-archived, undecided Case Files (his_case.refetch_all_active; skipped while a
meeting is in session; a Case File with a running job is skipped); automatic reminders at the due date for sent, unanswered requests
(dept_requests.remind_automatic, at most one per request per day); the daily digest per user at their digest time (one notification
with the unread count); expiry of meeting codes and of break-glass windows; the meeting_starting notice 15 minutes before a meeting;
prune of old notifications. State in data/tumour_board/scheduler.json {last_tick, last_jobs{name: {at, result}}}.

Where the work runs: the stores are JSON files changed by read-modify-write on the app's event loop, and the model client is bound to
that loop, so the thread only keeps time. When the app's loop is known (attach_loop(), called by the meeting routes, the bell and the
meeting sockets) every job runs ON that loop: the quick ones are awaited by the thread, the re-fetch is started there and collected
on a later tick. Before the app has served a request the quick jobs run in the thread (they touch small files) and the re-fetch waits.
TB_SCHEDULER=0 disables start(); under pytest it only starts with TB_SCHEDULER=1."""
import asyncio, logging, os, threading
from datetime import datetime

from . import config, store

log = logging.getLogger(__name__)

AUTOMATIC = "Vaidyx (automatic)"
STATE_FILE = "scheduler.json"
REFETCH_EVERY = 30 * 60
REMINDERS_EVERY = 10 * 60
PRUNE_EVERY = 24 * 3600
STARTING_MINUTES = 15
SYNC_TIMEOUT = 120  # seconds the thread waits for a quick job on the app's loop
_thread: threading.Thread | None = None
_stop = threading.Event()
_lock = threading.Lock()   # one tick at a time
_start_lock = threading.Lock()
_state: dict = {"last_tick": None, "last_jobs": {}, "started": None, "ticks": 0}
_LOOP = None               # the app's event loop (attach_loop)
_refetch: dict = {"future": None, "started": None, "collected": True}


# ---- the app's event loop ---------------------------------------------------------------------------------------------------------

def attach_loop(loop=None) -> None:
    """Remember the app's event loop (call from code running on it: a route, a socket). Cheap; safe anywhere."""
    global _LOOP
    if loop is None:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
    if _LOOP is not loop:
        _LOOP = loop


def app_loop():
    """The app's running event loop, or None (not known yet, or stopped: a test client that closed)."""
    cands = [_LOOP]
    try:
        from . import live
        cands.append(live.hub.loop)
    except Exception:
        pass
    for lp in cands:
        if lp is not None and not lp.is_closed() and lp.is_running():
            return lp
    return None


def _on(loop) -> bool:
    try:
        return asyncio.get_running_loop() is loop
    except RuntimeError:
        return False


def _run(fn, now):
    """Run a quick job on the app's loop and wait for it; inline when there is no loop or when already on it."""
    loop = app_loop()
    if loop is None or _on(loop):
        return fn(now)

    async def go():
        return fn(now)
    return asyncio.run_coroutine_threadsafe(go(), loop).result(timeout=SYNC_TIMEOUT)


def interval() -> float:
    try:
        return max(0.05, float(os.getenv("TB_SCHEDULER_INTERVAL", "60")))
    except ValueError:
        return 60.0


def _path():
    return config.DATA_ROOT / STATE_FILE


def _load() -> dict:
    d = store._read_json(_path(), None) if _path().exists() else None
    return d if isinstance(d, dict) else {"last_tick": None, "last_jobs": {}}


def _save() -> None:
    try:
        store._write_json(_path(), {k: v for k, v in _state.items()})
    except Exception as e:
        log.warning("scheduler state not saved (%s)", e)


def _due(name: str, every: float, now: datetime) -> bool:
    last = ((_state.get("last_jobs") or {}).get(name) or {}).get("at")
    if not last:
        return True
    try:
        return (now - datetime.fromisoformat(str(last))).total_seconds() >= every
    except ValueError:
        return True


def _mark(name: str, result, now: datetime) -> None:
    _state.setdefault("last_jobs", {})[name] = {"at": now.isoformat(timespec="seconds"), "result": result}


# ---- the jobs -----------------------------------------------------------------------------------------------------------------------

def job_codes(now: datetime) -> dict:
    from . import meetings
    return {"expired": meetings.expire_codes(now)}


def job_break_glass(now: datetime) -> dict:
    """Break-glass windows past their end are dropped (access.expire_break_glass)."""
    from . import access
    fn = getattr(access, "expire_break_glass", None)
    return {"expired": fn() if callable(fn) else 0}


def job_meeting_starting(now: datetime) -> dict:
    from . import meetings
    return {"announced": meetings.notify_starting(now, STARTING_MINUTES)}


def job_reminders(now: datetime) -> dict:
    """Every sent, unanswered Pre-Authorization request whose due date has come: one automatic reminder per request per day."""
    from . import dept_requests
    today = now.date()
    sent = []
    for c in store.list_cases():
        cid = c.get("case_id")
        if not cid or cid in config.PROTECTED_CASES or c.get("archived") or (c.get("listing") or {}).get("status") == "archived":
            continue
        try:
            st = store.get_state(cid)
        except (OSError, ValueError):
            continue
        for a in st.get("actions") or []:
            if not isinstance(a, dict) or a.get("source") != "pre_authorization" or a.get("status") in ("completed", "suggested"):
                continue
            try:
                if dept_requests.remind_automatic(cid, a["id"], today=today):
                    sent.append(f"{cid}:{a['id']}")
            except Exception as e:
                log.warning("automatic reminder %s %s failed (%s)", cid, a.get("id"), e)
    return {"sent": sent}


def job_digests(now: datetime) -> dict:
    """One digest notification per user at their digest time: the unread count by kind (no patient detail). Each person is looked at
    once a day from their digest time on; the digest goes out only when something is unread then."""
    from . import notify, org, push
    done_today = dict(((_state.get("last_jobs") or {}).get("digests") or {}).get("result", {}).get("done_on") or {})
    out = []
    for u, rec in (org.load().get("users") or {}).items():
        if not isinstance(rec, dict) or rec.get("disabled"):
            continue
        if not push.digest_due(u, now, done_today.get(u)):
            continue
        r = org.roles(u)
        if not r.get("known"):
            continue
        unread = [n for n in notify.for_roles(r, limit=None, unread_only=True) if n.get("kind") != "digest"]
        done_today[u] = now.date().isoformat()
        if not unread:
            continue
        kinds: dict = {}
        for n in unread:
            kinds[n.get("kind") or "other"] = kinds.get(n.get("kind") or "other", 0) + 1
        parts = ", ".join(f"{v} {k.replace('_', ' ')}" for k, v in sorted(kinds.items(), key=lambda x: -x[1]))
        try:
            notify.notify({"user": u}, "digest", "", f"Your digest: {len(unread)} unread notification(s)", f"Unread: {parts}. Open the bell to read them.", by=AUTOMATIC)
            out.append(u)
        except Exception as e:
            log.warning("digest to %s failed (%s)", u, e)
    return {"sent": out, "done_on": {u: d for u, d in done_today.items() if d == now.date().isoformat()}}


def job_prune(now: datetime) -> dict:
    from . import notify
    return {"dropped": notify.prune()}


def _running_jobs() -> set:
    from . import service
    return {j.get("case_id") for j in service.JOBS.values() if isinstance(j, dict) and j.get("state") == "running"}


async def _refetch_all() -> dict:
    """On the app's loop: the Case Files with a running job are looked up at the start, then each active one is re-fetched in turn
    (each processing job awaited, so the reader model gets one Case File at a time)."""
    from . import his_case
    return {"cases": await his_case.refetch_all_active(AUTOMATIC, skip=_running_jobs(), wait=True)}


def _collect_refetch(now: datetime) -> None:
    """A re-fetch started on an earlier tick that has finished: its result is kept as last_jobs.refetch_done."""
    fut = _refetch.get("future")
    if fut is None or not fut.done() or _refetch.get("collected"):
        return
    try:
        res = fut.result()
    except Exception as e:
        res = {"error": f"{e.__class__.__name__}: {str(e)[:200]}"}
    _refetch["collected"] = True
    _mark("refetch_done", {"started": _refetch.get("started"), **(res if isinstance(res, dict) else {"result": res})}, now)


def job_refetch(now: datetime) -> dict:
    """Start the re-fetch of the active HIS-connected Case Files on the app's loop (never in this thread: the model client and the
    Case File locks belong to that loop). Skipped while a meeting is in session, while the previous run is still going and until
    the app's loop is known."""
    from . import meetings
    if meetings.any_in_session():
        return {"skipped": "a meeting is in session"}
    fut = _refetch.get("future")
    if fut is not None and not fut.done():
        return {"skipped": "the previous re-fetch is still running", "since": _refetch.get("started")}
    loop = app_loop()
    if loop is None:
        return {"skipped": "waiting for the app to serve its first request"}
    _refetch.update({"future": asyncio.run_coroutine_threadsafe(_refetch_all(), loop), "started": now.isoformat(timespec="seconds"), "collected": False})
    return {"started": _refetch["started"]}


def similar_job(now: datetime) -> dict:
    """The Similar Case Files index (night-v3 item 7.1): profiles rebuilt for the Case Files that changed, in this thread (embedding on
    CPU, never on the app's loop). Never raises."""
    try:
        from . import similar
        return similar.job(now)
    except Exception as e:
        return {"error": f"{e.__class__.__name__}: {str(e)[:200]}"}


QUICK = ("codes", "break_glass", "meeting_starting", "reminders", "digests", "prune")
JOBS = (("codes", job_codes, 0), ("break_glass", job_break_glass, 0), ("meeting_starting", job_meeting_starting, 0),
        ("reminders", job_reminders, REMINDERS_EVERY), ("digests", job_digests, 0), ("prune", job_prune, PRUNE_EVERY),
        ("refetch", job_refetch, REFETCH_EVERY), ("similar", similar_job, 1800))


def tick(now: datetime | None = None, force: bool = False, only=None, refetch: bool = True) -> dict:
    """Run the jobs that are due (all of them with force=True; `only` names a subset). Returns {job: result}. Never raises."""
    now = now or datetime.now()
    out = {}
    with _lock:
        if not _state.get("last_jobs"):
            _state.update({k: v for k, v in _load().items() if k in ("last_jobs",)})
        _collect_refetch(now)
        for name, fn, every in JOBS:
            if only is not None and name not in only:
                continue
            if name == "refetch" and not refetch:
                continue
            if not force and every and not _due(name, every, now):
                continue
            try:
                res = _run(fn, now) if name in QUICK else fn(now)
            except Exception as e:
                log.exception("scheduler job %s failed", name)
                res = {"error": f"{e.__class__.__name__}: {str(e)[:200]}"}
            out[name] = res
            if not (name == "refetch" and isinstance(res, dict) and str(res.get("skipped") or "").startswith("waiting")):
                _mark(name, res, now)  # a re-fetch that could not start yet is tried again on the next tick
        _state["last_tick"] = now.isoformat(timespec="seconds")
        _state["ticks"] = int(_state.get("ticks") or 0) + 1
        _save()
    return out


def _loop() -> None:
    """Wait one interval first (the app finishes starting and serves its first requests, so the jobs find its loop), then tick."""
    log.info("tumour board scheduler started (every %.0f s)", interval())
    while not _stop.wait(interval()):
        try:
            tick()
        except Exception:
            log.exception("scheduler tick failed")


def start() -> bool:
    """Start the daemon thread once; TB_SCHEDULER=0 keeps it off; under pytest it starts only with TB_SCHEDULER=1."""
    global _thread
    if os.getenv("TB_SCHEDULER", "1") == "0":
        return False
    if "PYTEST_CURRENT_TEST" in os.environ and os.getenv("TB_SCHEDULER") != "1":
        return False
    with _start_lock:
        if _thread is not None and _thread.is_alive():
            return True
        _stop.clear()
        _state["started"] = store.now_iso()
        _thread = threading.Thread(target=_loop, daemon=True, name="tb-scheduler")
        _thread.start()
    return True


def stop(timeout: float = 5.0) -> None:
    global _thread
    _stop.set()
    t = _thread
    if t is not None and t.is_alive() and t is not threading.current_thread():
        t.join(timeout)
    _thread = None


def running() -> bool:
    return _thread is not None and _thread.is_alive()


def status() -> dict:
    saved = _load()
    fut = _refetch.get("future")
    return {"running": running(), "interval_seconds": interval(), "enabled": os.getenv("TB_SCHEDULER", "1") != "0", "started": _state.get("started"),
            "last_tick": _state.get("last_tick") or saved.get("last_tick"), "last_jobs": _state.get("last_jobs") or saved.get("last_jobs") or {},
            "ticks": _state.get("ticks", 0), "jobs": [{"name": n, "every_seconds": e} for n, _, e in JOBS], "by": AUTOMATIC, "now": store.now_iso(),
            "app_loop": app_loop() is not None, "refetch_running": bool(fut is not None and not fut.done())}
