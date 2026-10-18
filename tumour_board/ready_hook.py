"""At the ready mark (18 Oct, SPEC 3.5): the AI prose of the Case File summary and the five heads' briefs are prepared in the background,
one after the other to keep the GPU calm, and the owning department is told when they are done.

on_ready(case_id, user) is called by POST /cases/{id}/ready after the mark succeeds. It schedules the work on the running event loop (or
on a thread with its own loop when none runs) and returns at once. Nothing runs during a meeting: while a board session is in_session the
run waits five minutes and looks again. Pieces that still stand for the Case File (same signature) are skipped. TB_SCHEDULER=0 turns the
hook off (tests). Every step is audited in the Case File; a failing step never stops the next."""
import asyncio
import logging
import os
import threading
import time

from . import agents, config, rules, store, summary

log = logging.getLogger("tumour_board")

HEADS = ("radiology", "pathology", "medical_oncology", "surgical_oncology", "radiation_oncology")
MEETING_DELAY = 300  # seconds between looks while a meeting is in session
MAX_WAITS = 48  # four hours of waiting at most
RUNNING: dict = {}  # case_id -> {"started", "user", "step"}
TASKS: set = set()
_lock = threading.Lock()


def enabled() -> bool:
    return os.getenv("TB_SCHEDULER", "1").strip().lower() not in ("0", "false", "no", "off")


def running(case_id) -> bool:
    return case_id in RUNNING


def meeting_in_session() -> bool:
    """A board session is running (data/tumour_board/sessions): nothing heavy starts until it ends."""
    try:
        from . import board
        return any(s.get("status") == "in_session" for s in board.list_sessions())
    except Exception:
        return False


def summary_fresh(st, sig) -> bool:
    s = (st.get("artefacts") or {}).get("summary")
    return bool(isinstance(s, dict) and isinstance(s.get("sections"), list) and s.get("signature") and not rules.stale_reason(s["signature"], sig))


def _audit(case_id, **ev):
    try:
        store.audit(case_id, {"kind": "ready_hook", **ev})
    except Exception:
        pass


def _notify_owner(case_id, case, user, done, failed):
    from . import notify, org
    patient = (case.get("patient") or {}).get("name") or case_id
    to = {"department": case["department"]} if case.get("department") and org.department_id(case["department"]) else {"user": user}
    title = f"Summary and briefs prepared: {patient} ({case_id})"
    text = ("The Case File summary and the specialty briefs are ready to review (AI drafts, not reviewed): " + ", ".join(done)
            + (f". Not prepared: {', '.join(failed)}" if failed else "") + ".")
    for kind in ("summary_ready", "owner_reminder"):  # summary_ready when notify.KINDS knows it; else the owner's reminder channel
        try:
            return notify.notify(to, kind, case_id, title, text, by="Vaidyx (automatic)", prepared=done, failed=failed)
        except ValueError:
            continue
        except Exception as e:
            return {"error": f"{e.__class__.__name__}: {e}"}
    return None


async def run(case_id, user) -> dict:
    """The work itself: wait out a meeting, then the summary and the five briefs in turn, skipping what is fresh; the owner is told."""
    out = {"case_id": case_id, "done": [], "skipped": [], "failed": [], "waited": 0}
    with _lock:
        if case_id in RUNNING:
            return {**out, "skipped": ["already running"]}
        RUNNING[case_id] = {"started": time.time(), "user": user, "step": "waiting"}
    try:
        waits = 0
        while meeting_in_session():
            if waits >= MAX_WAITS:
                _audit(case_id, step="gave_up", why="a board session stayed in session", by=user)
                out["failed"].append("meeting")
                return out
            waits += 1; out["waited"] = waits
            await asyncio.sleep(MEETING_DELAY)
        case = store.get_case(case_id)
        if not case or not case.get("protocol"):
            return out
        _audit(case_id, step="start", by=user)
        st = store.get_state(case_id)
        sig = rules.case_signature(case_id, st)
        RUNNING[case_id]["step"] = "summary"
        if summary_fresh(st, sig):
            out["skipped"].append("summary")
        else:
            try:
                res = await summary.build(case_id, force=True)  # the ready mark is the doctor's word: the draft is compiled even with open gaps
                if res.get("status") in ("ready", "incomplete_gate"):
                    out["done"].append("summary")
                else:
                    out["failed"].append("summary"); _audit(case_id, step="summary_failed", why=res.get("message") or res.get("status"), by=user)
            except Exception as e:
                out["failed"].append("summary"); _audit(case_id, step="summary_failed", why=f"{e.__class__.__name__}: {str(e)[:200]}", by=user)
        for role in HEADS:
            RUNNING[case_id]["step"] = role
            st = store.get_state(case_id)
            art = (st.get("artefacts") or {}).get(f"brief_{role}")
            if agents.fresh(art, rules.case_signature(case_id, st)):
                out["skipped"].append(role)
                continue
            try:
                res = await agents.prepare(case_id, role)
                (out["done"] if res.get("brief") else out["failed"]).append(role)
                if not res.get("brief"):
                    _audit(case_id, step=f"{role}_failed", why=res.get("error") or "no brief", by=user)
            except Exception as e:
                out["failed"].append(role); _audit(case_id, step=f"{role}_failed", why=f"{e.__class__.__name__}: {str(e)[:200]}", by=user)
        _audit(case_id, step="finished", done=out["done"], skipped=out["skipped"], failed=out["failed"], waited=out["waited"], by=user)
        if out["done"]:
            n = _notify_owner(case_id, case, user, out["done"], out["failed"])
            out["notified"] = bool(n and not n.get("error"))
        return out
    finally:
        with _lock:
            RUNNING.pop(case_id, None)


def on_ready(case_id, user) -> dict:
    """Schedule the preparation and return at once: {"scheduled": bool, "how": loop|thread|off}."""
    if not enabled():
        return {"scheduled": False, "how": "off", "reason": "TB_SCHEDULER=0"}
    if case_id in config.PROTECTED_CASES:
        return {"scheduled": False, "how": "off", "reason": "protected Case File"}
    if running(case_id):
        return {"scheduled": False, "how": "running", "reason": "already running"}
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if loop is not None:
        task = loop.create_task(run(case_id, user))
        TASKS.add(task)
        task.add_done_callback(TASKS.discard)
        return {"scheduled": True, "how": "loop"}
    t = threading.Thread(target=lambda: asyncio.run(run(case_id, user)), daemon=True, name=f"tb-ready-{case_id}")
    t.start()
    return {"scheduled": True, "how": "thread"}
