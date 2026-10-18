"""Shared helpers of the HIMS screen tests: sign in through the login form as one of the 9 demo accounts, the session's CSRF
token, form posts that carry it, and small HTML helpers. SYNTHETIC data only (temporary builds)."""
import re
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from fastapi.testclient import TestClient

from his_mock import auth

EM_DASH = "\u2014"
EN_DASH = "\u2013"


def logins(data_dir):
    """{first role: (email, password)} from the build's logins.tsv (never printed)."""
    out = {}
    for line in (Path(data_dir) / auth.LOGINS_NAME).read_text(encoding="utf-8").splitlines()[1:]:
        email, roles, password = line.split("\t")
        out[roles.split(",")[0]] = (email, password)
    return out


def login(app, role, data_dir=None):
    """A TestClient signed in as `role` (reception, opd.doctor, lab.tech, lab.doctor, rad.tech, radiologist,
    pathologist, admin)."""
    d = data_dir or app.state.hospital.files["data_dir"]
    email, password = logins(d)[role]
    c = TestClient(app)
    r = c.post("/his/login", data={"email": email, "password": password, "next": "/his"}, follow_redirects=False)
    assert r.status_code == 303, (role, r.status_code, r.text[:300])
    assert c.cookies.get(auth.COOKIE)
    return c


def session(client):
    return client.app.state.hospital.accounts.session(client.cookies.get(auth.COOKIE))


def csrf(client):
    return session(client)["csrf"]


def post(client, url, data=None, **kw):
    """A form post carrying the session's CSRF token; redirects are not followed."""
    body = dict(data or {})
    body.setdefault("csrf", csrf(client))
    return client.post(url, data=body, follow_redirects=False, **kw)


def location(resp):
    assert resp.status_code == 303, (resp.status_code, resp.text[:400])
    u = urlparse(resp.headers["location"])
    return u.path, {k: v[0] for k, v in parse_qs(u.query).items()}


def flash(resp):
    """The flash text of a redirect (from its query) or of a rendered page."""
    if resp.status_code == 303:
        return location(resp)[1].get("flash", "")
    m = re.search(r'<div class="flash [a-z]+">([^<]*)</div>', resp.text)
    return m.group(1) if m else ""


def text_of(html):
    t = re.sub(r"<style>.*?</style>", " ", html, flags=re.S)
    return " ".join(re.sub(r"<[^>]+>", " ", t).split())


def clean(html):
    """The page carries the SYNTHETIC ribbon, no em or en dash and no Aadhaar word."""
    assert "SYNTHETIC DATA" in html
    assert EM_DASH not in html and EN_DASH not in html
    assert "aadhaar" not in html.lower()
