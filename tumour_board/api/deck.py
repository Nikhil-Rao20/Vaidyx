"""The board deck downloads (19 Oct 2026) and the hospital's logo.

    GET  /meetings/{mid}/deck        the deck of a meeting (.pptx): the coordinator and the admitted members; an outside expert is refused
    GET  /cases/{cid}/deck           the deck of one Case File (.pptx): whoever may open the whole Case File
    GET  /hospital/logo              the hospital's logo (PNG or JPEG), for the website and the deck; 404 when none was uploaded
    POST /setup/hospital/logo        {data: "data:image/png;base64,..."} (root admin): kept under the data root as hospital_logo.<ext>,
                                     at most 1 MB, PNG or JPEG only (a deck cannot carry an SVG); DELETE removes it
Every download is audited on the meeting or the Case File."""
import asyncio
import base64
import copy
import re

from fastapi import Request
from fastapi.responses import FileResponse, Response

from tumour_board import access, board, config, deck, meetings, org, store
from tumour_board.api.common import body, case, fail, make_router, need, need_known, roles, user

router = make_router(["tumour-board-deck"])
PPTX = "application/vnd.openxmlformats-officedocument.presentationml.presentation"
LOGO_MAX = 1_000_000
LOGO_TYPES = {"image/png": "png", "image/jpeg": "jpg"}


def _pptx(data: bytes, name: str) -> Response:
    return Response(data, media_type=PPTX, headers={"Content-Disposition": f'attachment; filename="{name}"'})


@router.get("/meetings/{mid}/deck")
async def meeting_deck(mid: str, request: Request):
    u = user(request); rl = roles(request); need_known(rl)
    s = meetings.get(mid)
    if not s:
        fail(404, "Meeting not found.", "not_found")
    if rl.get("outside_expert") and not meetings.manage(rl):
        fail(403, "An outside expert follows the shared screen; the deck is for the hospital's members.", "outside_expert")
    if not (meetings.manage(rl) or meetings.is_member(rl, s)):
        fail(403, "Only the MDT Coordinator and the admitted members download the deck.", "not_member")
    try:
        data = await asyncio.to_thread(deck.build_meeting, mid, rl)
    except KeyError:
        fail(404, "Meeting not found.", "not_found")
    board.audit_event(mid, "deck_downloaded", u, bytes=len(data))
    return _pptx(data, deck.filename("meeting", mid, str(s.get("date") or "")))


@router.get("/cases/{case_id}/deck")
async def case_deck(case_id: str, request: Request):
    u = user(request); rl = roles(request); need_known(rl)
    c = case(case_id)
    if str(access.scope(rl, c) or "").upper() != "FULL":
        fail(403, "Only the people who may open the whole Case File download its deck.", "forbidden")
    data = await asyncio.to_thread(deck.build_case, case_id, rl)
    store.audit(case_id, {"kind": "deck_downloaded", "by": u, "bytes": len(data)})
    return _pptx(data, deck.filename("case", case_id))


@router.get("/hospital/logo")
async def hospital_logo(request: Request):
    user(request)
    p = deck.hospital_logo_path()
    if not p or not p.exists():
        fail(404, "No hospital logo has been uploaded.", "no_logo")
    media = "image/png" if p.suffix == ".png" else "image/jpeg"
    return FileResponse(str(p), media_type=media, headers={"Cache-Control": "private, max-age=300"})


@router.post("/setup/hospital/logo")
async def upload_logo(request: Request):
    r = roles(request); need(r, "manage_org"); b = await body(request)
    data = str(b.get("data") or "")
    m = re.match(r"^data:(image/png|image/jpeg);base64,([A-Za-z0-9+/=\s]+)$", data)
    if not m:
        fail(400, "Send the logo as a PNG or JPEG data URL.", "bad_logo")
    try:
        raw = base64.b64decode(m.group(2), validate=False)
    except ValueError:
        fail(400, "The logo could not be decoded.", "bad_logo")
    if not raw or len(raw) > LOGO_MAX:
        fail(400, "The logo must be at most 1 MB.", "too_big")
    if m.group(1) == "image/png" and not raw.startswith(b"\x89PNG\r\n\x1a\n"):
        fail(400, "This is not a PNG file.", "bad_logo")
    if m.group(1) == "image/jpeg" and not raw.startswith(b"\xff\xd8"):
        fail(400, "This is not a JPEG file.", "bad_logo")
    ext = LOGO_TYPES[m.group(1)]
    for old in config.DATA_ROOT.glob("hospital_logo.*"):
        try:
            old.unlink()
        except OSError:
            pass
    target = config.DATA_ROOT / f"hospital_logo.{ext}"
    target.write_bytes(raw)
    o = copy.deepcopy(org.load())
    o["hospital"]["logo"] = {"file": target.name, "type": m.group(1), "bytes": len(raw), "at": org.now_iso(), "by": r["user"]}
    try:
        org.save(o, r["user"])
    except ValueError as e:
        fail(400, str(e), "bad_value")
    org.audit("hospital_logo", r["user"], bytes=len(raw), type=m.group(1))
    return {"ok": True, "logo": o["hospital"]["logo"]}


@router.delete("/setup/hospital/logo")
async def remove_logo(request: Request):
    r = roles(request); need(r, "manage_org")
    for old in config.DATA_ROOT.glob("hospital_logo.*"):
        try:
            old.unlink()
        except OSError:
            pass
    o = copy.deepcopy(org.load())
    o["hospital"].pop("logo", None)
    try:
        org.save(o, r["user"])
    except ValueError as e:
        fail(400, str(e), "bad_value")
    org.audit("hospital_logo_removed", r["user"])
    return {"ok": True}
