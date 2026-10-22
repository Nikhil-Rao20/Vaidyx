"""Video routes (B3): GET /video/status and POST /meetings/{mid}/video-token for the admitted members of a meeting."""
from fastapi import Request

from . import common
from .. import meetings, video

router = common.make_router(["tumour-board-video"])


@router.get("/video/status")
async def video_status(request: Request):
    common.user(request)
    return video.status()


@router.post("/meetings/{mid}/video-token")
async def video_token(mid: str, request: Request):
    """A LiveKit access token for the meeting's room (tb-<mid>), for a member admitted by the MDT Coordinator (or the coordinator)."""
    u = common.user(request); rl = common.roles(request)
    if not (rl.get("outside_expert") and not rl.get("disabled")):  # an outside expert admitted to the meeting may join its video too
        common.need_known(rl)
    s = meetings.get(mid)
    if not s:
        common.fail(404, "Meeting not found.", "not_found")
    if s.get("status") in ("closed", "cancelled"):
        common.fail(409, "This meeting is over.", "meeting_over")
    if not meetings.is_member(rl, s):
        common.fail(403, "Only members admitted to this meeting can join its video.", "not_member")
    if not video.enabled():
        common.fail(503, "Video is not set up on this server (ask the Vaidyx admin to run scripts/livekit.sh).", "video_off")
    body = await common.body(request) if request.headers.get("content-length") not in (None, "0") else {}
    screen = str((body or {}).get("screen") or "").strip().lower()
    if screen == "room":  # the room computer: its own identity, so the coordinator's laptop and the room screen are both in the call
        if not meetings.manage(rl):
            common.fail(403, "Only the MDT Coordinator opens the room screen's video.", "not_coordinator")
        out = video.for_meeting(mid, f"{u}#room", f"Room screen ({meetings.display_name(u)})")
    else:
        out = video.for_meeting(mid, u, meetings.display_name(u))
    from .. import board
    board.audit_event(mid, "video_token", u, room=out["room"], identity=out["identity"])
    return out
