"""The hospital's logo (19 Oct 2026). The .pptx deck routes that lived here were removed in meetings-v2 item 4.2 (owner decision D10):
the meeting PDF and the Case File's board record PDF replace them (api/meeting_pdf.py). The module keeps its name so the router list
in routes/tumour_board_routes.py stays as it is.

    GET  /hospital/logo              the hospital's logo (PNG or JPEG), for the website and the meeting PDF; 404 when none was uploaded
    POST /setup/hospital/logo        {data: "data:image/png;base64,..."} (root admin): kept under the data root as hospital_logo.<ext>,
                                     at most 1 MB, PNG or JPEG only; DELETE removes it
The upload and the removal are audited (org audit: hospital_logo, hospital_logo_removed)."""
import base64
import copy
import re

from fastapi import Request
from fastapi.responses import FileResponse

from tumour_board import config, meeting_pdf, org
from tumour_board.api.common import body, fail, make_router, need, roles, user

router = make_router(["tumour-board-logo"])
LOGO_MAX = 1_000_000
LOGO_TYPES = {"image/png": "png", "image/jpeg": "jpg"}


@router.get("/hospital/logo")
async def hospital_logo(request: Request):
    user(request)
    p = meeting_pdf.logo_path()
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
