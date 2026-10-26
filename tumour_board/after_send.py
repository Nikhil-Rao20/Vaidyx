"""After sending (night-v3 item 1.5, design B8, owner decision D9): what changed in a Case File once it was sent to the board. Plain code, no model.

A report that becomes ready after the ready mark (a new upload, a re-fetch from the HIS, a re-read) re-runs the ready hook (ready_hook.on_ready
again=True: the summary and the briefs are written again when stale, never during a meeting, and the MDT Coordinator only is told). When the
new report differs from an earlier one (two reports disagree, or the new one is only preliminary), the difference waits on the treating
doctor: the Check step gives the task "Check 1 value" (steps.build, `since_sent`), and the coordinator's agenda row says "waiting on Dr X"
(waiting_on). Vaidyx never picks: the doctor picks the value the board uses (item 1.7) or notes the difference, and the task is gone.
"""
from . import config, store

_CHECKS: dict = {}  # case_id -> (steps._files_key, count): the count is kept until one of the Case File's files changes


def is_sent(case: dict | None) -> bool:
    """Sent to the board and not taken off the agenda."""
    return isinstance(case, dict) and bool(case.get("board_ready")) and not (case.get("board_send") or {}).get("withdrawn")


def sent_at(case: dict | None) -> str:
    """When the Case File was sent (the ready mark, ISO), "" when it is not sent."""
    return str((case.get("board_ready") or {}).get("at") or "") if is_sent(case) else ""


def new_docs(case_id: str, case: dict | None = None) -> list[str]:
    """The reports that became ready after the ready mark (read, or read again, later than the mark), oldest first."""
    case = case if case is not None else store.get_case(case_id)
    at = sent_at(case)
    if not at:
        return []
    rows = [d for d in store.list_docs(case_id) if d.get("state") == "ready" and not d.get("superseded") and str(d.get("processed") or "") > at]
    return [d["doc_id"] for d in sorted(rows, key=lambda d: str(d.get("processed") or ""))]


def new_since_sent(case_id: str, case: dict | None = None) -> int:
    """How many reports are new or changed since the Case File was sent (0 when it is not sent)."""
    try:
        return len(new_docs(case_id, case))
    except Exception:
        return 0


def since_sent(case_id: str, case: dict | None, problems: list) -> list:
    """The open "two reports differ" problems of the Check step (steps.build) that a report read after the ready mark brought: one of the two
    reports it cites is new since sending. Picked or noted differences are not open, so they never count."""
    fresh = set(new_docs(case_id, case))
    if not fresh:
        return []
    out = []
    for p in problems or []:
        conf = p.get("confirmation") or {}
        if p.get("resolved") or conf.get("type") != "note_discordance":
            continue
        if any((c or {}).get("doc_id") in fresh for c in conf.get("citations") or []):
            out.append(p)
    return out


def check_count(case_id: str) -> int:
    """How many values wait on the treating doctor's check since sending (the "Check N values" task); kept until a file changes."""
    from . import steps
    try:
        key = steps._files_key(case_id)
        hit = _CHECKS.get(case_id)
        if hit and hit[0] == key:
            return hit[1]
        case = store.get_case(case_id)
        n = len(since_sent(case_id, case, steps.build(case_id, None)["check"]["problems"])) if is_sent(case) else 0
        if len(_CHECKS) > 4000:
            _CHECKS.clear()
        _CHECKS[case_id] = (key, n)
        return n
    except Exception:
        return 0


def doctor_of(case: dict) -> str:
    """Who the check waits on: the presenter chosen when the Case File was sent, else the team's owner consultant, else who sent it."""
    from . import meetings
    return meetings.presenter_of(case) or meetings.owner_user(case) or str((case.get("board_ready") or {}).get("by") or "")


def waiting_on(case: dict | None) -> dict | None:
    """{"user", "name", "values"} when a sent Case File has values that wait on the treating doctor's check since sending, else None.
    For the coordinator's agenda row ("waiting on Dr X") and the coordinator's notice."""
    if not is_sent(case) or not case.get("case_id") or case["case_id"] in config.PROTECTED_CASES:
        return None
    n = check_count(case["case_id"])
    if not n:
        return None
    from .slots import display_name
    u = doctor_of(case)
    return {"user": u, "name": display_name(u) if u else "", "values": n}  # name "" : nobody is named, the line says "the treating doctor"
