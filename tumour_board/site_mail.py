"""Email for the public website: the enquiry form (tumour_board/api/site.py) is sent to the Vaidyx team through an SMTP account
the owner configures in data/tumour_board/site_mail.json:

    {"host": "smtp.example.org", "port": 587, "username": "...", "password": "...", "from": "vaidyx@example.org",
     "to": "sulake.nikhileswararao@tanuh.ai", "starttls": true}

Without the file (or when the send fails) nothing is lost: every enquiry is written to data/tumour_board/enquiries/ first and
the API answers sent=false, so the interface can offer the direct address instead. The subject line is fixed so the mailbox
can filter the website's enquiries. Never logs the password."""
from __future__ import annotations

import json
import logging
import smtplib
import ssl
from email.message import EmailMessage
from pathlib import Path

from tumour_board import config

log = logging.getLogger("tumour_board.site_mail")

SUBJECT = "[Vaidyx] Website enquiry"
DEFAULT_TO = "sulake.nikhileswararao@tanuh.ai"
TIMEOUT = 20


def config_path() -> Path:
    return Path(config.DATA_ROOT) / "site_mail.json"


def settings() -> dict | None:
    """The SMTP settings, or None when the file is missing or unusable."""
    p = config_path()
    if not p.exists():
        return None
    try:
        s = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        log.warning("site_mail.json unreadable: %s", e)
        return None
    if not isinstance(s, dict) or not s.get("host") or not s.get("from"):
        log.warning("site_mail.json needs at least host and from")
        return None
    return s


def configured() -> bool:
    return settings() is not None


def recipient() -> str:
    s = settings() or {}
    return str(s.get("to") or DEFAULT_TO)


def compose(rec: dict) -> EmailMessage:
    """The message for one enquiry record (as written by the API)."""
    msg = EmailMessage()
    s = settings() or {}
    msg["Subject"] = f"{SUBJECT}: {rec.get('name', '')}".strip(": ")
    msg["From"] = str(s.get("from") or DEFAULT_TO)
    msg["To"] = recipient()
    if rec.get("email"):
        msg["Reply-To"] = str(rec["email"])
    body = "\n".join([
        "A new enquiry from the Vaidyx website.",
        "",
        f"Name: {rec.get('name', '')}",
        f"Email: {rec.get('email', '')}",
        f"Hospital or institution: {rec.get('hospital', '') or '(not given)'}",
        f"Received: {rec.get('at', '')}",
        "",
        "Message:",
        str(rec.get("message", "")),
        "",
        f"Enquiry id: {rec.get('id', '')}",
    ])
    msg.set_content(body)
    return msg


def send_enquiry(rec: dict) -> bool:
    """Sends the enquiry; True when the SMTP server accepted it. Never raises."""
    s = settings()
    if not s:
        return False
    try:
        msg = compose(rec)
        host, port = str(s["host"]), int(s.get("port") or 587)
        if s.get("ssl"):
            server = smtplib.SMTP_SSL(host, port, timeout=TIMEOUT, context=ssl.create_default_context())
        else:
            server = smtplib.SMTP(host, port, timeout=TIMEOUT)
        with server:
            if s.get("starttls", True) and not s.get("ssl"):
                server.starttls(context=ssl.create_default_context())
            if s.get("username"):
                server.login(str(s["username"]), str(s.get("password") or ""))
            server.send_message(msg)
        log.info("enquiry %s sent to %s", rec.get("id"), msg["To"])
        return True
    except Exception as e:  # noqa: BLE001 - any SMTP failure leaves the enquiry on disk
        log.warning("enquiry %s not sent: %s", rec.get("id"), e.__class__.__name__)
        return False
