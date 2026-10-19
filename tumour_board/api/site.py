"""Public endpoints of the website (/tb-nik/api/*), no login: the auth middleware exempts the /tb-nik prefix, and the router is
mounted beside /api/tb by setup_tumour_board_routes(). Today: the enquiry form. Every enquiry is written to
data/tumour_board/enquiries/ and then emailed (tumour_board/site_mail.py) when an SMTP account is configured. A honeypot field,
field limits and a small per-address rate limit keep the form from being abused."""
from __future__ import annotations

import json
import re
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request

from tumour_board import config, site_mail

router = APIRouter(prefix="/tb-nik/api", tags=["site"])

LIMITS = {"name": (2, 120), "email": (5, 200), "hospital": (0, 200), "message": (10, 4000)}
EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
RATE = (5, 600)  # five enquiries per address per ten minutes
_seen: dict[str, list[float]] = {}
_lock = threading.Lock()


def enquiries_dir() -> Path:
    return Path(config.DATA_ROOT) / "enquiries"


def _ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for", "")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _limited(ip: str) -> bool:
    now = time.time()
    with _lock:
        hits = [t for t in _seen.get(ip, []) if now - t < RATE[1]]
        if len(hits) >= RATE[0]:
            _seen[ip] = hits
            return True
        hits.append(now)
        _seen[ip] = hits
    return False


def _field(body: dict, key: str) -> str:
    v = body.get(key, "")
    if not isinstance(v, str):
        raise HTTPException(400, {"message": f"{key} must be text.", "code": "bad_field"})
    v = " ".join(v.split()) if key != "message" else v.strip()
    lo, hi = LIMITS[key]
    if len(v) < lo:
        raise HTTPException(400, {"message": f"{key} is too short.", "code": "too_short", "field": key})
    if len(v) > hi:
        raise HTTPException(400, {"message": f"{key} is too long.", "code": "too_long", "field": key})
    return v


@router.post("/enquiry")
async def enquiry(request: Request):
    try:
        body = await request.json()
    except ValueError:
        raise HTTPException(400, {"message": "Send the enquiry as JSON.", "code": "bad_json"})
    if not isinstance(body, dict):
        raise HTTPException(400, {"message": "Send the enquiry as JSON.", "code": "bad_json"})
    # a field people never see; a bot fills it, so the enquiry is dropped quietly
    if body.get("website"):
        return {"ok": True, "sent": False, "id": None}
    name, email, hospital, message = _field(body, "name"), _field(body, "email"), _field(body, "hospital"), _field(body, "message")
    if not EMAIL.match(email):
        raise HTTPException(400, {"message": "The email address does not look right.", "code": "bad_email", "field": "email"})
    ip = _ip(request)
    if _limited(ip):  # only complete enquiries count
        raise HTTPException(429, {"message": "Too many enquiries from this connection. Please try again later.", "code": "rate_limited"})
    rec = {
        "id": uuid.uuid4().hex[:12],
        "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "name": name, "email": email, "hospital": hospital, "message": message,
        "ip": ip, "user_agent": request.headers.get("user-agent", "")[:300],
    }
    d = enquiries_dir()
    d.mkdir(parents=True, exist_ok=True)
    stamp = rec["at"].replace(":", "").replace("-", "")[:15]
    (d / f"{stamp}-{rec['id']}.json").write_text(json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8")
    sent = site_mail.send_enquiry(rec)
    rec["sent"] = sent
    (d / f"{stamp}-{rec['id']}.json").write_text(json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"ok": True, "sent": sent, "id": rec["id"], "direct": site_mail.recipient()}
