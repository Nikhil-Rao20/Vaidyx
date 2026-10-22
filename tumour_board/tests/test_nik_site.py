"""The website's public enquiry endpoint (/tb-nik/api/enquiry): stored on disk, emailed when SMTP is configured, validated,
honeypot, rate limit. Hermetic: no SMTP server (the send is monkeypatched)."""
import json

from tumour_board import site_mail
from tumour_board.api import site
from tumour_board.tests.test_nik_meetings import app, tc  # noqa: F401

GOOD = {"name": "Dr Test Person", "email": "test.person@example.org", "hospital": "Example Hospital", "message": "We would like to try Vaidyx for our breast Tumour Board."}


def test_enquiry_is_stored_and_answered_without_a_login(tc, monkeypatch):
    site._seen.clear()
    monkeypatch.setattr(site_mail, "send_enquiry", lambda rec: False)
    r = tc.post("/tb-nik/api/enquiry", json=GOOD)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True and body["sent"] is False and body["id"]
    assert body["direct"] == site_mail.DEFAULT_TO
    files = list(site.enquiries_dir().glob("*.json"))
    assert len(files) == 1
    rec = json.loads(files[0].read_text())
    assert rec["name"] == GOOD["name"] and rec["email"] == GOOD["email"] and rec["sent"] is False


def test_enquiry_is_sent_when_smtp_is_configured(tc, monkeypatch, tmp_path):
    site._seen.clear()
    captured = {}
    monkeypatch.setattr(site_mail, "send_enquiry", lambda rec: captured.update(rec) or True)
    r = tc.post("/tb-nik/api/enquiry", json=GOOD)
    assert r.status_code == 200 and r.json()["sent"] is True
    assert captured["message"] == GOOD["message"]
    # the composed mail carries the fixed subject, the sender as Reply-To and the recipient
    (site_mail.config_path()).write_text(json.dumps({"host": "smtp.example.org", "from": "vaidyx@example.org"}))
    msg = site_mail.compose(captured)
    assert msg["Subject"].startswith(site_mail.SUBJECT)
    assert msg["Reply-To"] == GOOD["email"] and msg["To"] == site_mail.DEFAULT_TO
    assert GOOD["message"] in msg.get_content()


def test_enquiry_validation_honeypot_and_rate_limit(tc, monkeypatch):
    site._seen.clear()
    monkeypatch.setattr(site_mail, "send_enquiry", lambda rec: False)
    assert tc.post("/tb-nik/api/enquiry", json={**GOOD, "email": "not-an-address"}).status_code == 400
    assert tc.post("/tb-nik/api/enquiry", json={**GOOD, "message": "short"}).status_code == 400
    assert tc.post("/tb-nik/api/enquiry", json={**GOOD, "name": "x" * 200}).status_code == 400
    before = len(list(site.enquiries_dir().glob("*.json"))) if site.enquiries_dir().exists() else 0
    r = tc.post("/tb-nik/api/enquiry", json={**GOOD, "website": "http://spam.example"})
    assert r.status_code == 200 and r.json()["id"] is None
    assert (len(list(site.enquiries_dir().glob("*.json"))) if site.enquiries_dir().exists() else 0) == before
    for _ in range(site.RATE[0]):
        assert tc.post("/tb-nik/api/enquiry", json=GOOD).status_code == 200
    assert tc.post("/tb-nik/api/enquiry", json=GOOD).status_code == 429


def test_send_without_settings_is_false_and_quiet():
    assert site_mail.settings() is None
    assert site_mail.send_enquiry({"id": "x", "name": "n", "email": "a@b.co", "message": "m"}) is False
