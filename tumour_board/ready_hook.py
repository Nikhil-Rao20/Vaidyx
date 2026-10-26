"""At the ready mark (18 Oct, SPEC 3.5): the AI prose of the Case File summary and the five heads' briefs are prepared in the background,
one after the other to keep the GPU calm, and the owning department is told when they are done.

on_ready(case_id, user) is called by POST /cases/{id}/ready after the mark succeeds. It schedules the work on the running event loop (or
on a thread with its own loop when none runs) and returns at once. Nothing runs during a meeting: while a board session is in_session the
run waits five minutes and looks again. Pieces that still stand for the Case File (same signature) are skipped. TB_SCHEDULER=0 turns the
hook off (tests). Every step is audited in the Case File; a failing step never stops the next.

After sending (night-v3 item 1.5, design B8): a report that becomes ready after the ready mark calls on_ready(..., again=True) from
service.process_docs. That run is audited as step "again", waits out a meeting the same way, writes the summary and the briefs again when
stale, and tells the MDT Coordinator only (record_arrived: how many reports are new since sending and, when a value now waits on the treating
doctor's check, "waiting on Dr X"); the owner is not told. A record that arrives while a run is going sets a flag and the run goes once more."""
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
AGAIN: set = set()  # case_ids whose records changed while a run was going: the run goes once more at its end (item 1.5)
MAX_PASSES = 3  # one run and at most two more passes for records that kept arriving
TASKS: set = set()
_lock = threading.Lock()


def enabled() -> bool:
    return os.getenv("TB_SCHEDULER", "1").strip().lower() not in ("0", "false", "no", "off")


def running(case_id) -> bool:
    return case_id in RUNNING


def meeting_in_session() -> bool:
    """A board session is running now (data/tumour_board/sessions; board.running_now: one left in session from an earlier day does not
    count): nothing heavy starts until it ends."""
    try:
        from . import board
        return bool(board.running_sessions())
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


def _notify_coordinator(case_id, case, user, done, failed) -> dict | None:
    """After sending, a new or changed report: the MDT Coordinator only is told what was updated and whom a value waits on (item 1.5)."""
    from . import after_send, notify, team
    try:
        case = store.get_case(case_id) or case
        n = after_send.new_since_sent(case_id, case)
        title = f"New record after the ready mark: {team.patient_line(case)} ({case_id})"
        text = f"{n} new or changed {'report' if n == 1 else 'reports'} since it was sent; "
        text += ("the summary and the slides are updated." if "summary" not in failed
                 else "the slides show the new values; the summary could not be written again (the Case File shows it as out of date).")
        w = after_send.waiting_on(case)
        if w:
            k = w["values"]
            text += f" {k} {'value needs' if k == 1 else 'values need'} the treating doctor's check: waiting on {w['name'] or 'the treating doctor'}."
        return notify.notify({"role": "coordinator"}, "record_arrived", case_id, title, text, by=user, updated=done, failed=failed, new_records=n,
                             waiting_on=w)
    except Exception as e:
        return {"error": f"{e.__class__.__name__}: {e}"}


async def run(case_id, user, again=False) -> dict:
    """The work itself: wait out a meeting, then the summary and the five briefs in turn, skipping what is fresh; the owner is told (the
    first run) or the MDT Coordinator only (again=True: a report arrived after the ready mark). Records that arrive meanwhile: once more."""
    with _lock:
        if case_id in RUNNING:
            if again:
                AGAIN.add(case_id)
            return {"case_id": case_id, "done": [], "skipped": ["already running"], "failed": [], "waited": 0, "again": bool(again)}
        RUNNING[case_id] = {"started": time.time(), "user": user, "step": "waiting"}
    try:
        out = await _pass(case_id, user, again)
        passes = 1
        while passes < MAX_PASSES:
            with _lock:
                more = case_id in AGAIN
                AGAIN.discard(case_id)
            if not more:
                break
            passes += 1
            out = await _pass(case_id, user, True)
        out["passes"] = passes
        return out
    finally:
        with _lock:
            RUNNING.pop(case_id, None)
            AGAIN.discard(case_id)


async def _pass(case_id, user, again=False) -> dict:
    """One pass of the work (run holds the RUNNING guard around it)."""
    out = {"case_id": case_id, "done": [], "skipped": [], "failed": [], "waited": 0, "again": bool(again)}
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
    if again:
        from . import after_send
        if not after_send.is_sent(case):  # taken off the agenda while it waited: nothing to update for the board
            return out
        _audit(case_id, step="again", by=user, new_records=after_send.new_since_sent(case_id, case))
    else:
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
        if store.gone(case_id) or not store.get_case(case_id):  # the Case File was deleted meanwhile: stop (nothing is written for it)
            out["failed"].append("deleted")
            return out
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
    _audit(case_id, step="finished", done=out["done"], skipped=out["skipped"], failed=out["failed"], waited=out["waited"], by=user,
           **({"again": True} if again else {}))
    if again:  # the coordinator only, every time a record arrived (the slides read the new values even when nothing was rewritten)
        n = _notify_coordinator(case_id, case, user, out["done"], out["failed"])
        out["notified"] = bool(n and not n.get("error"))
    elif out["done"]:
        n = _notify_owner(case_id, case, user, out["done"], out["failed"])
        out["notified"] = bool(n and not n.get("error"))
    return out


def on_ready(case_id, user, again=False) -> dict:
    """Schedule the preparation and return at once: {"scheduled": bool, "how": loop|thread|off|running}. again=True: a report became ready
    after the ready mark (service.process_docs); while a run is going it is flagged to go once more."""
    if not enabled():
        return {"scheduled": False, "how": "off", "reason": "TB_SCHEDULER=0"}
    if case_id in config.PROTECTED_CASES:
        return {"scheduled": False, "how": "off", "reason": "protected Case File"}
    with _lock:
        if case_id in RUNNING:
            if again:
                AGAIN.add(case_id)
            return {"scheduled": False, "how": "running", "reason": "already running", "again": bool(again)}
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if loop is not None:
        task = loop.create_task(run(case_id, user, again))
        TASKS.add(task)
        task.add_done_callback(TASKS.discard)
        return {"scheduled": True, "how": "loop"}
    t = threading.Thread(target=lambda: asyncio.run(run(case_id, user, again)), daemon=True, name=f"tb-ready-{case_id}")
    t.start()
    return {"scheduled": True, "how": "thread"}
