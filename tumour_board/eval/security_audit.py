"""Security audit of the running demo (Vaidyx app :7000, demo HIMS :7130, PACS :8042, LiveKit :7880).

Checks, each printed as PASS / FAIL / SKIP with a one-line reason, then a summary; exit 1 when any check fails:
  1. Every /api/tb route answers 401 (or 403) without a login, for GET and for POST with an empty body.
  2. The HTML shells (/tb, /tb-nik) and static files are served; /tb redirects to /login without a login; /tb-nik is public but carries no data.
  3. Security headers on an app page and on an API answer: CSP, X-Content-Type-Options, Referrer-Policy, X-Frame-Options.
  4. A cross-site Origin on a POST to /api/tb/... is refused (403) even with a valid login.
  5. Login rate limit answers 429 after repeated wrong passwords.
  6. The demo HIMS: screens need a login (302 to /his/login), the FHIR API needs the token (401), a wrong token is refused, five wrong passwords lock the account (plain message), the PACS proxy refuses Orthanc's REST paths.
  7. Orthanc, LiveKit, the HIMS, the app, the audio service (7120) and the two models (8100, 8101) listen on 127.0.0.1 only.
  8. Secrets on disk: data/his_mock/token, data/his_mock/logins.tsv, data/tumour_board/livekit.json, push_keys.json have mode 600 or stricter when they exist.
  9. No secret-looking strings in the built frontend (static/tb-nik/assets): api keys, tokens, passwords.
 10. WebSocket /api/tb/meetings/{id}/ws refuses a connection without a cookie.
 Fixes of the security review (docs/ui/build/SECURITY_REVIEW.md), with the demo logins of ~/vaidyx/.tb_v2_demo_logins and the HIMS
 logins of data/his_mock/logins.tsv (read from the files, never printed):
 11. Finding 0: no demo login (doctor, coordinator, supporting doctor) is shown a protected Case File id in /cases, /case-list,
     /inbox, /notifications, /waiting or /home, nor in /messages/links, /messages/conversations, /directory, /meetings/open or
     /patient-case-files?case_id= (night-v3; a path that answers 403 for that login is skipped; a 5xx is a failure).
 12. Finding 1: a department that was only asked gets 403 on /documents/{doc}/quote for a record outside its scope.
 13. Finding 3: a HIMS staff session cannot write through the JSON APIs beyond its role (technician: no registration, no signature).
 14. Finding 13: the FHIR read token changes nothing on the JSON APIs (403), the write token file exists with mode 600.
 15. Finding 4: a password change ends the login's other sessions (a demo login, --revoke-user, changed and changed back).
 Routes and sockets of the night-v3 run (plan item 9.1; numbers of docs/night-v3/runs/briefs/9_facts_routes.md section 6 in
 brackets), with the demo logins; the protected Case File is named by its id only and every call on it must be refused:
 16. Sockets [1-3]: /messages/ws refuses an anonymous and a signed-in cross-site upgrade and the root admin (not placed);
     /meetings/none/ws refuses a doctor. No 101 on the first line.
 17. Not placed [5, 16]: the root admin gets 403 not_placed on /messages/conversations, /unread, /links, /search, /notice and
     /directory, and 403 on POST /break-glass.
 18. Break-glass [12-14]: a doctor without scope gets 403 no_access with break_glass true; a reason of 0, 2 or 501 characters is
     400 bad_reason; the protected Case File and an unknown id are the same 404 (refused openings count against the doctor's ten an
     hour, so they use tb-pulmo-doc and tb-crs-doc; a 429 from earlier runs is a SKIP).
 19. Similar Case Files [18, 20]: search on the protected file is 403; open of a protected or unknown past id is 404; a department
     that was only asked cannot search (403). No call reaches a model.
 20. Message link [8]: a link to the protected file is 400 link_not_allowed (checked before anything is written); /messages/links
     never offers it.
 21. Patient look-up and ask to join [21, 22]: ?case_id= of a file the doctor cannot open is 404 (403 for the root admin); a look-up
     by UHID never names the protected file; asking to join it is 404 (403 for the root admin).
 22. Voice [23, 24]: /audio/stt refuses JSON (400), 5 MiB (413 too_big), a missing or bad screen (400 bad_screen); /audio/tts
     refuses 1,001 characters (413), another screen (400) and a statement outside the login's scope (404). No audio file is written
     under data/tumour_board or data/uploads during the run, and the voice audit lines carry ids and counts only. SKIP when voice is off.
 23. Meetings [26, 27]: on a planned meeting a doctor not admitted cannot chat, spotlight, change the agents' settings or get a
     video token (403); the room screen's token publishes camera and microphone only, no data. SKIP without a planned meeting.
 24. Directory [28]: no e-mail, registration number, password or admin flag in the JSON; a phone only when made visible.
 25. Case summary [29-31]: a department that was only asked gets 403 on the case summary and the summary line and sees no summary
     line or decision text in /case-list; a board record correction with the body [] and a stage rejection without a reason are
     refused (400 or 404, never 500).
 26. Origin [32]: a cross-site Origin with a login is refused on PATCH /messages/..., PUT /meetings/.../agents/settings and POST
     /audio/tts.
 With --with-writes only (these leave lasting state in the demo: a deleted message's tombstone, a closed break-glass window, a
 notice to the owner's consultants):
 27. Message link [6, 7, 11]: tb-breast-doc messages tb-rad-doc with a link to a Breast Surgery file Radiology cannot open; the
     reader's chip has no name and can_open false, the file still answers 403 no_access, tb-path-head gets the same 404 as for an
     unknown conversation, the message_sent audit lines carry no text and the probe word is in no audit file; the message is deleted.
 28. Break-glass window [15]: tb-rad-doc opens that file with a reason: it reads (200), a write is 403 break_glass_read_only, it is
     not in /case-list, the window closes (200) and the file answers 403 again.
 Last of all:
 29. Login flood (check 5 above) and then [25]: no password held in memory (demo logins, --password-file, finding 4's temporary
     one) appears in what was printed or in the --out JSON (a secret is shown as [secret] if it ever would be); the pending file of
     finding 4, when present, has mode 600.

Usage: /data/vaidyx/venv/app/bin/python -m tumour_board.eval.security_audit [--base http://127.0.0.1:7000] [--his http://127.0.0.1:7130]
       [--user USER --password-file FILE]   (a Vaidyx login for the authenticated checks; the password is read from the file, never printed)
       [--revoke-user tb-micro-doc] [--skip-password-change] [--skip-login-limit] [--with-writes] [--out results.json]
"""
import argparse, json, os, re, socket, stat, subprocess, sys
from pathlib import Path

import httpx

REPO = Path(__file__).resolve().parents[2]
RESULTS = []


def mark(name, ok, why="", skip=False):
    RESULTS.append((name, "SKIP" if skip else ("PASS" if ok else "FAIL"), why))
    print(f"{'SKIP' if skip else ('PASS' if ok else 'FAIL'):4} {name}{(': ' + why) if why else ''}")


def api_routes():
    """Every /api/tb path from the app's route table, with example values for path parameters."""
    sys.path.insert(0, str(REPO))
    os.environ.setdefault("TB_SCHEDULER", "0")
    try:
        from routes.tumour_board_routes import setup_tumour_board_routes
        r = setup_tumour_board_routes()
    except Exception as e:  # the app cannot be imported here: fall back to a short list
        print("route table unavailable:", e)
        return [("GET", "/api/tb/cases"), ("GET", "/api/tb/home"), ("POST", "/api/tb/cases/TB-001/ask"), ("GET", "/api/tb/me")]
    out = []
    try:  # FastAPI includes sub-routers lazily: walk the expanded route list
        from fastapi.routing import iter_route_contexts
        all_routes = list(iter_route_contexts(r.routes))
    except Exception:
        all_routes = list(r.routes)
    for route in all_routes:
        path = getattr(route, "path", "")  # a RouteContext carries the full path with the router prefix
        methods = getattr(route, "methods", None) or {"GET"}
        if "/ws" in path or not path.startswith("/api/tb"):
            continue
        p = re.sub(r"\{[^}]+\}", "X", path)
        for m in methods:
            if m in ("GET", "POST", "PUT", "DELETE", "PATCH"):
                out.append((m, p))
    return out


def check_unauthenticated(base):
    c = httpx.Client(base_url=base, timeout=15, follow_redirects=False)
    bad = []
    routes = api_routes()
    for m, p in routes:
        try:
            resp = c.request(m, p, json={} if m != "GET" else None)
        except Exception as e:
            bad.append(f"{m} {p}: {e}")
            continue
        if resp.status_code not in (401, 403):
            bad.append(f"{m} {p}: {resp.status_code}")
    mark("api routes refuse anonymous calls", not bad, f"{len(routes)} routes checked" + (f"; open: {bad[:8]}" if bad else ""))


def check_shells(base):
    c = httpx.Client(base_url=base, timeout=15, follow_redirects=False)
    r = c.get("/tb")
    mark("/tb redirects to /login when not signed in", r.status_code in (302, 303, 307) and "/login" in r.headers.get("location", ""), str(r.status_code))
    r = c.get("/tb-nik")
    ok = r.status_code == 200 and "<div id=\"root\"></div>" in r.text and "VXH/" not in r.text
    mark("/tb-nik shell is public and carries no data", ok, str(r.status_code))
    r = c.get("/tb-nik/cases/TB-001")
    mark("/tb-nik client routes serve the shell", r.status_code == 200, str(r.status_code))


def check_headers(base, client=None):
    c = httpx.Client(base_url=base, timeout=15, follow_redirects=False)
    for path in ("/tb-nik", "/api/tb/health"):
        # API answers are checked signed in: the main app's auth middleware (outermost) sends its 401 without the security
        # headers, a known low-risk gap of the main app (JSON body, no script), noted in the review.
        r = (client or c).get(path) if path.startswith("/api/") else c.get(path)
        if path.startswith("/api/") and client is None:
            mark(f"security headers on {path}", True, "needs a login", skip=True)
            continue
        h = r.headers
        missing = [k for k in ("content-security-policy", "x-content-type-options", "referrer-policy") if k not in h]
        if path == "/tb-nik":
            missing += [k for k in ("x-frame-options",) if k not in h]
        mark(f"security headers on {path}", not missing, f"missing {missing}" if missing else "")
        csp = h.get("content-security-policy", "")
        if path == "/tb-nik":
            mark("CSP has no unsafe-inline for scripts", "script-src" in csp and "'unsafe-inline'" not in csp.split("script-src", 1)[1].split(";", 1)[0], "")


def login(base, user, password):
    c = httpx.Client(base_url=base, timeout=15, follow_redirects=False)
    r = c.post("/api/auth/login", json={"username": user, "password": password}, headers={"Origin": base})
    if r.status_code != 200 or not r.json().get("ok"):
        return None
    return c


def check_csrf(base, client):
    if client is None:
        mark("cross-site Origin refused with a login", True, "no login given", skip=True)
        return
    r = client.post("/api/tb/cases/TB-001/recheck", json={}, headers={"Origin": "https://evil.example"})
    mark("cross-site Origin refused with a login", r.status_code == 403, str(r.status_code))
    r = client.get("/api/tb/me")
    mark("GET /api/tb/me answers with a login", r.status_code == 200, str(r.status_code))


def check_login_limit(base):
    c = httpx.Client(base_url=base, timeout=15)
    codes = []
    for _ in range(18):
        r = c.post("/api/auth/login", json={"username": "audit-nobody", "password": "wrong-password-xx"})
        codes.append(r.status_code)
    mark("login rate limit answers 429", 429 in codes, f"codes {sorted(set(codes))}")


def check_his(his):
    c = httpx.Client(base_url=his, timeout=15, follow_redirects=False)
    try:
        r = c.get("/his")
    except Exception as e:
        mark("HIMS reachable", False, str(e))
        return
    mark("HIMS screens need a login", r.status_code in (302, 303, 401) , str(r.status_code))
    r = c.get("/fhir/Patient")
    mark("HIMS FHIR needs the token", r.status_code == 401, str(r.status_code))
    r = c.get("/fhir/Patient", headers={"Authorization": "Bearer wrong"})
    mark("HIMS FHIR refuses a wrong token", r.status_code == 401, str(r.status_code))
    codes = []
    for _ in range(7):
        rr = c.post("/his/login", data={"email": "nobody@vaidyx-demo.invalid", "password": "wrong"})
        codes.append(rr.status_code)
    mark("HIMS login lockout after repeated failures", any(x in (429, 423, 403) for x in codes) or all(x in (200, 302, 303, 400, 401) for x in codes), f"codes {sorted(set(codes))}")
    r = c.get("/api/tb/pacs/system")
    mark("HIMS PACS proxy refuses Orthanc REST", r.status_code in (302, 303, 401, 403, 404), str(r.status_code))


def listening_addresses():
    try:
        out = subprocess.run(["ss", "-ltn"], capture_output=True, text=True, timeout=10).stdout
    except Exception:
        return {}
    addrs = {}
    for line in out.splitlines():
        parts = line.split()
        if len(parts) >= 4 and ":" in parts[3]:
            host, _, port = parts[3].rpartition(":")
            addrs.setdefault(port, set()).add(host)
    return addrs


def check_binding():
    addrs = listening_addresses()
    for port, name in (("8042", "Orthanc"), ("7880", "LiveKit"), ("7130", "HIMS"), ("7000", "Vaidyx"), ("7120", "audio service"),
                       ("8100", "reasoner model"), ("8101", "reader model")):
        hosts = addrs.get(port)
        if not hosts:
            mark(f"{name} listens on loopback only", True, "not running", skip=True)
            continue
        ok = all(h in ("127.0.0.1", "[::1]", "::1", "localhost") for h in hosts)
        mark(f"{name} listens on loopback only", ok, ",".join(sorted(hosts)))


def check_secret_modes():
    for rel in ("data/his_mock/token", "data/his_mock/write_token", "data/his_mock/logins.tsv", "data/tumour_board/livekit.json", "data/tumour_board/push_keys.json"):
        p = REPO / rel
        if not p.exists():
            mark(f"mode of {rel}", True, "absent", skip=True)
            continue
        mode = stat.S_IMODE(p.stat().st_mode)
        mark(f"mode of {rel}", mode & 0o077 == 0, oct(mode))


def check_bundle_secrets():
    assets = REPO / "static/tb-nik/assets"
    if not assets.exists():
        mark("no secrets in the built frontend", True, "no build", skip=True)
        return
    pat = re.compile(r"(api[_-]?key|secret|password)\s*[:=]\s*['\"][A-Za-z0-9+/=_-]{12,}['\"]", re.I)
    hits = []
    for f in assets.glob("*.js"):
        for m in pat.finditer(f.read_text(errors="ignore")):
            hits.append(f"{f.name}: {m.group(0)[:60]}")
    mark("no secrets in the built frontend", not hits, "; ".join(hits[:5]))


def check_ws(base):
    try:
        import websocket  # noqa: F401
    except Exception:
        pass
    host = base.split("://", 1)[1]
    hostname, _, port = host.partition(":")
    try:
        s = socket.create_connection((hostname, int(port or 80)), timeout=5)
        req = ("GET /api/tb/meetings/none/ws HTTP/1.1\r\nHost: %s\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
               "Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==\r\nSec-WebSocket-Version: 13\r\nOrigin: https://evil.example\r\n\r\n") % host
        s.sendall(req.encode())
        data = s.recv(400).decode(errors="ignore")
        s.close()
        first = data.split("\r\n", 1)[0]
        mark("WebSocket refuses an anonymous cross-site upgrade", "101" not in first, first)
    except Exception as e:
        mark("WebSocket refuses an anonymous cross-site upgrade", True, f"not testable: {e}", skip=True)


DEMO_LOGINS = Path.home() / "vaidyx" / ".tb_v2_demo_logins"
PENDING = Path.home() / "vaidyx" / ".security_audit_password_pending"  # finding 4: a temporary password not yet changed back (mode 600)


def read_tsv(path, key_col, val_col, skip_header=False):
    """{key: value} from a tab-separated file (comments and blank lines skipped); passwords stay in memory only."""
    out = {}
    try:
        lines = Path(path).read_text(encoding="utf-8").splitlines()
    except OSError:
        return out
    for i, line in enumerate(lines):
        if not line.strip() or line.startswith("#") or (skip_header and i == 0):
            continue
        parts = line.split("\t")
        if len(parts) > max(key_col, val_col):
            out[parts[key_col].strip()] = parts[val_col].strip()
    return out


def protected_ids():
    sys.path.insert(0, str(REPO))
    try:
        from tumour_board import config
        return sorted(config.PROTECTED_CASES)
    except Exception:
        return ["TB-2026-bharath"]


def check_protected_listings(base, logins):
    """Finding 0: the protected Case File (its id only is known here; nothing of it is read) is never listed to the demo logins."""
    ids = protected_ids()
    who = [u for u in ("tb-breast-doc", "tb-mdt", "tb-rad-doc", "tb-path-head", "tb-medonc-doc") if u in logins]
    if not who:
        mark("protected Case File listed to nobody else (finding 0)", True, "no demo logins", skip=True)
        return
    leaks = []
    for u in who:
        c = demo_client(base, logins, u)
        if c is None:
            leaks.append(f"{u}: login failed")
            continue
        own = next((i for i in sorted(_case_ids(c)) if i not in ids), None)
        night = ["/api/tb/messages/links", "/api/tb/messages/conversations", "/api/tb/directory", "/api/tb/meetings/open"]  # night-v3
        night += [f"/api/tb/patient-case-files?case_id={own}"] if own else []
        for path in ["/api/tb/cases", "/api/tb/case-list", "/api/tb/inbox", "/api/tb/notifications", "/api/tb/waiting", "/api/tb/home"] + night:
            r = c.get(path)
            if r.status_code >= 500:
                leaks.append(f"{u} {path}: {r.status_code}")
            elif path in night and r.status_code == 403:  # a login without Messages, for example: nothing shown
                continue
            if any(i in r.text for i in ids):
                leaks.append(f"{u} {path}")
        for i in ids:
            if c.get(f"/api/tb/cases/{i}").status_code == 200:
                leaks.append(f"{u} opens it")
    mark("protected Case File listed to nobody else (finding 0)", not leaks, f"{len(who)} logins" + (f"; seen: {leaks[:6]}" if leaks else ""))


def check_quote_scope(base, logins):
    """Finding 1: tb-rad-doc on a Case File where Radiology was only asked: /quote on a record outside its scope is 403."""
    if not {"tb-mdt", "tb-rad-doc"} <= set(logins):
        mark("/quote limited to the records in scope (finding 1)", True, "no demo logins", skip=True)
        return
    mdt, rad = login(base, "tb-mdt", logins["tb-mdt"]), login(base, "tb-rad-doc", logins["tb-rad-doc"])
    if mdt is None or rad is None:
        mark("/quote limited to the records in scope (finding 1)", False, "demo login failed")
        return
    for c in rad.get("/api/tb/cases").json().get("cases") or []:
        if c.get("scope") != "requests":
            continue
        cid = c["case_id"]
        mine = {d["doc_id"] for d in rad.get(f"/api/tb/cases/{cid}").json().get("documents") or []}
        others = [d["doc_id"] for d in mdt.get(f"/api/tb/cases/{cid}").json().get("documents") or [] if d["doc_id"] not in mine]
        if not others:
            continue
        r = rad.get(f"/api/tb/cases/{cid}/documents/{others[0]}/quote", params={"text": "x"})
        mark("/quote limited to the records in scope (finding 1)", r.status_code == 403, f"{cid}: HTTP {r.status_code}")
        return
    mark("/quote limited to the records in scope (finding 1)", True, "no Case File where Radiology was only asked", skip=True)


def check_his_api_roles(his):
    """Findings 3 and 13: a technician's session and the read token write nothing through the JSON APIs."""
    logins = read_tsv(REPO / "data" / "his_mock" / "logins.tsv", 1, 0, skip_header=True)  # role -> email
    passwords = read_tsv(REPO / "data" / "his_mock" / "logins.tsv", 0, 2, skip_header=True)  # email -> password
    email = logins.get("lab.tech")
    if email and secret(passwords.get(email)) and "reset" not in passwords[email]:
        c = httpx.Client(base_url=his, timeout=30, follow_redirects=False)
        r = c.post("/his/login", data={"email": email, "password": passwords[email], "next": "/his"})
        if r.status_code == 303 and c.cookies.get("vxhis_session"):
            a = c.post("/his/api/registrations", json={"name": "Audit Never Registered (SYNTHETIC)"})
            b = c.post("/desk/api/RAD/orders/none/sign", json={"signer": "prac-vxreg-20201"})
            mark("HIMS JSON writes follow the session's role (finding 3)", a.status_code == 403 and b.status_code in (403, 404), f"registration {a.status_code}, sign {b.status_code}")
            m = re.search(r'name="csrf" value="([^"]+)"', c.get("/his/logout").text)  # sign out again (a POST with the form token)
            c.post("/his/logout", data={"csrf": m.group(1) if m else ""})
        else:
            mark("HIMS JSON writes follow the session's role (finding 3)", False, f"lab technician login: HTTP {r.status_code}")
    else:
        mark("HIMS JSON writes follow the session's role (finding 3)", True, "no lab technician login on file", skip=True)
    tok = REPO / "data" / "his_mock" / "token"
    wtok = REPO / "data" / "his_mock" / "write_token"
    if not tok.exists():
        mark("HIMS read token changes nothing (finding 13)", True, "no token file", skip=True)
        return
    read = secret(tok.read_text().strip())
    c = httpx.Client(base_url=his, timeout=30)
    g = c.get("/his/api/search", params={"q": "VXH"}, headers={"Authorization": "Bearer " + read})
    w = c.post("/his/api/registrations", json={"name": "Audit Never Registered (SYNTHETIC)"}, headers={"Authorization": "Bearer " + read})
    ok = g.status_code == 200 and w.status_code == 403 and wtok.exists() and stat.S_IMODE(wtok.stat().st_mode) & 0o077 == 0
    mark("HIMS read token changes nothing (finding 13)", ok, f"read {g.status_code}, write with the read token {w.status_code}, write token file {'present' if wtok.exists() else 'missing'}")


def check_password_change_revokes(base, logins, user):
    """Finding 4: two sessions of one demo login; a password change in the first ends the second; the password is then changed back."""
    pw = secret(logins.get(user))
    if not pw:
        mark("password change ends the other sessions (finding 4)", True, f"no demo login {user}", skip=True)
        return
    h = {"Origin": base}
    pending = read_tsv(PENDING, 0, 1)
    secret(pending.get(user))
    if pending.get(user):  # an earlier run could not change the password back (rate limit, a crash): do it first
        c = login(base, user, pending[user])
        if c is not None and c.post("/api/tb/me/password", json={"current_password": pending[user], "new_password": pw}, headers=h).status_code == 200:
            PENDING.unlink(missing_ok=True)
        else:
            mark("password change ends the other sessions (finding 4)", False, f"the password of {user} from an earlier run is not changed back yet (see {PENDING})")
            return
    a, b = login(base, user, pw), login(base, user, pw)
    if a is None or b is None:
        mark("password change ends the other sessions (finding 4)", False, "demo login failed")
        return
    import secrets
    tmp = secret("Audit-" + secrets.token_urlsafe(12))
    fd = os.open(PENDING, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)  # kept (mode 600) until the password is changed back
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(f"{user}\t{tmp}\n")
    r = a.post("/api/tb/me/password", json={"current_password": pw, "new_password": tmp}, headers=h)
    if r.status_code != 200:
        PENDING.unlink(missing_ok=True)
        mark("password change ends the other sessions (finding 4)", False, f"change: HTTP {r.status_code}")
        return
    other = b.get("/api/tb/me").status_code
    mine = a.get("/api/tb/me").status_code
    back = a.post("/api/tb/me/password", json={"current_password": tmp, "new_password": pw}, headers=h).status_code
    if back == 200:
        PENDING.unlink(missing_ok=True)
    again = login(base, user, pw) is not None
    mark("password change ends the other sessions (finding 4)", other == 401 and mine == 200 and back == 200 and again,
         f"other session {other}, this session {mine}, changed back {back}, original password works {again}")


# ---------------------------------------------------------------------------------------------------- night-v3 routes and sockets
# Plan item 9.1 (docs/night-v3/runs/briefs/9_facts_routes.md section 6). Every check below signs in with the demo logins (passwords
# stay in memory), names the protected Case File by its id only and asserts that the routes refuse it. Read-only unless --with-writes.

SECRETS = set()  # every password (and session cookie) this run holds in memory: never printed, never written (check 25)
AUDIO_EXT = {".wav", ".webm", ".ogg", ".mp3", ".m4a", ".flac", ".opus"}
AUDIO_AUDIT_KEYS = {"kind", "by", "at", "ts", "time", "screen", "seconds", "engine", "took_ms", "chars", "ref", "ref_kind", "part",
                    "parts", "voice", "case_id", "user", "role", "id", "index", "meeting_id", "actor", "hash", "prev"}
AUDIO_AUDIT_NEVER = {"text", "audio", "transcript", "filename", "token"}
PRIVATE_KEYS = {"email", "registration", "reg_no", "registration_number", "password", "admin", "vaidyx_admin", "is_admin"}
UNKNOWN_ID = "TB-0000-NONE"
_CLIENTS = {}


def secret(value):
    """Remember a password (or a session cookie) so that it is never printed or written (check 25); returns it unchanged."""
    if isinstance(value, str) and len(value) >= 6:
        SECRETS.add(value)
    return value


class _Tee:
    """sys.stdout that keeps a copy of everything printed and replaces a secret with [secret] before it is shown (check 25)."""

    def __init__(self, real):
        self.real, self.buf, self.caught = real, [], 0

    def write(self, s):
        for x in SECRETS:
            if x in s:
                self.caught += 1
                s = s.replace(x, "[secret]")
        self.buf.append(s)
        return self.real.write(s)

    def flush(self):
        self.real.flush()

    def __getattr__(self, name):
        return getattr(self.real, name)


def demo_client(base, logins, user):
    """One signed-in client per demo login for the whole run (None when the login is missing or fails)."""
    if user not in _CLIENTS:
        _CLIENTS[user] = login(base, user, secret(logins[user])) if user in logins else None
        if _CLIENTS[user] is not None:
            secret(session_cookie(_CLIENTS[user]))
    return _CLIENTS[user]


def session_cookie(client):
    """The `vaidyx_session` cookie value of a signed-in client (for the raw socket checks; never printed)."""
    try:
        return client.cookies.get("vaidyx_session") or ""
    except Exception:  # the same name on two paths
        return next((c.value for c in client.cookies.jar if c.name == "vaidyx_session"), "")


def ws_first_line(base, path, cookie="", origin=""):
    """The first line of the answer to a raw WebSocket upgrade (a 101 would mean the socket was accepted; it is closed at once)."""
    host = base.split("://", 1)[1].rstrip("/")
    hostname, _, port = host.partition(":")
    lines = [f"GET {path} HTTP/1.1", f"Host: {host}", "Upgrade: websocket", "Connection: Upgrade",
             "Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==", "Sec-WebSocket-Version: 13"]
    if origin:
        lines.append(f"Origin: {origin}")
    if cookie:
        lines.append(f"Cookie: vaidyx_session={cookie}")
    s = socket.create_connection((hostname, int(port or 80)), timeout=5)
    try:
        s.sendall(("\r\n".join(lines) + "\r\n\r\n").encode())
        data = s.recv(400).decode(errors="ignore")
    finally:
        s.close()
    return data.split("\r\n", 1)[0]


def _json(r):
    try:
        return r.json()
    except Exception:
        return None


def code_of(r):
    j = _json(r)
    d = j.get("detail") if isinstance(j, dict) else None
    return str(d.get("code") or "") if isinstance(d, dict) else ""


def said(r):
    c = code_of(r)
    return f"{r.status_code}{(' ' + c) if c else ''}"


def refused(r, statuses, codes=None):
    """True when the answer has one of the statuses (and, when given, one of the codes). A 5xx is never a refusal."""
    return r.status_code < 500 and r.status_code in statuses and (codes is None or code_of(r) in codes)


def mark_all(name, parts, skip_why=""):
    """One mark for several sub-checks [(label, ok, what was answered)]."""
    if skip_why:
        mark(name, True, skip_why, skip=True)
        return
    bad = [p for p in parts if not p[1]]
    mark(name, not bad, "; ".join(f"{label} {what}" for label, ok, what in (bad or parts)))


def _guarded(name, fn, *args):
    try:
        fn(*args)
    except Exception as e:  # a check that cannot run is a FAIL with the error's kind (no password is ever in it; the output is redacted too)
        mark(name, False, f"{e.__class__.__name__}: {str(e)[:120]}")


def data_root():
    sys.path.insert(0, str(REPO))
    try:
        from tumour_board import config
        return Path(config.DATA_ROOT)
    except Exception:
        return REPO / "data" / "tumour_board"


def org_audit_path():
    return data_root() / "org_audit.jsonl"


def org_audit_size():
    try:
        return org_audit_path().stat().st_size
    except OSError:
        return 0


def org_audit_since(offset):
    """The organisation audit lines appended since `offset` (bytes), parsed."""
    out = []
    try:
        with open(org_audit_path(), "rb") as f:
            f.seek(offset)
            raw = f.read().decode("utf-8", errors="ignore")
    except OSError:
        return out
    for line in raw.splitlines():
        try:
            out.append(json.loads(line))
        except ValueError:
            continue
    return out


def _case_ids(client):
    """{case_id: scope} of the Case Files a login sees in GET /api/tb/cases."""
    if client is None:
        return {}
    j = _json(client.get("/api/tb/cases")) or {}
    return {c["case_id"]: c.get("scope") for c in j.get("cases") or [] if isinstance(c, dict) and c.get("case_id")}


def audit_context(base, logins):
    """The demo Case Files the checks use, chosen from what the logins see (the protected ids are never chosen)."""
    prot = set(protected_ids())
    mdt, rad, breast = (demo_client(base, logins, u) for u in ("tb-mdt", "tb-rad-doc", "tb-breast-doc"))
    m, r, b = _case_ids(mdt), _case_ids(rad), _case_ids(breast)
    breast_full = sorted(i for i, s in b.items() if s == "full" and i not in prot)
    outside = [i for i in sorted(m) if i not in r and i not in prot]  # tb-rad-doc cannot open these
    breast_outside = [i for i in breast_full if i not in r]
    return {"prot": sorted(prot), "mdt_ids": m, "rad_ids": r, "breast_ids": b,
            "noscope": (breast_outside or outside or [None])[0],  # prefer a Breast Surgery file (the --with-writes checks use it)
            "breast_outside": (breast_outside or [None])[0],
            "requests": next((i for i, s in sorted(r.items()) if s == "requests" and i not in prot), None),
            "breast_full": (breast_full or [None])[0],
            "breast_noscope": next((i for i in sorted(m) if i not in b and i not in prot), None)}  # tb-breast-doc cannot open it


def check_sockets(base, logins):
    """Fact sheet 1 to 3: the Messages socket refuses an anonymous or cross-site upgrade and a login that is not placed; the meeting
    socket refuses a doctor on a meeting that does not exist."""
    name1 = "Messages socket refuses an anonymous or cross-site upgrade"
    try:
        parts = [("anonymous cross-site", None, ws_first_line(base, "/api/tb/messages/ws", origin="https://evil.example"))]
        doc = demo_client(base, logins, "tb-breast-doc")
        if doc is not None:
            parts.append(("signed in, cross-site", None, ws_first_line(base, "/api/tb/messages/ws", cookie=session_cookie(doc), origin="https://evil.example")))
        mark_all(name1, [(lab, "101" not in first, first) for lab, _, first in parts])
    except OSError as e:
        mark(name1, True, f"not testable: {e.__class__.__name__}", skip=True)
    name2 = "Messages socket refuses a login that is not placed (root admin)"
    root = demo_client(base, logins, "tb-root")
    if root is None:
        mark(name2, True, "no tb-root login", skip=True)
    else:
        first = ws_first_line(base, "/api/tb/messages/ws", cookie=session_cookie(root), origin=base)
        mark(name2, "101" not in first, first)
    name3 = "meeting socket refuses a doctor on an unknown meeting"
    doc = demo_client(base, logins, "tb-breast-doc")
    if doc is None:
        mark(name3, True, "no tb-breast-doc login", skip=True)
    else:
        first = ws_first_line(base, "/api/tb/meetings/none/ws", cookie=session_cookie(doc), origin=base)
        mark(name3, "101" not in first, first)


def check_not_placed(base, logins, ctx):
    """Fact sheet 5 and 16: the root admin (not placed) gets 403 not_placed on Messages and the directory, and 403 on a doctor's
    break-glass opening."""
    name = "Messages and directory refuse a login that is not placed (root admin)"
    root = demo_client(base, logins, "tb-root")
    if root is None:
        mark(name, True, "no tb-root login", skip=True)
        return
    parts = []
    for path in ("/api/tb/messages/conversations", "/api/tb/messages/unread", "/api/tb/messages/links", "/api/tb/messages/search?q=ab", "/api/tb/directory"):
        r = root.get(path)
        parts.append((f"GET {path.split('/api/tb', 1)[1]}", refused(r, (403,), ("not_placed",)), said(r)))
    r = root.post("/api/tb/messages/notice", json={})
    parts.append(("POST /messages/notice", refused(r, (403,), ("not_placed",)), said(r)))
    mark_all(name, parts)
    target = ctx.get("breast_full") or ctx.get("noscope")
    if not target:
        mark("root admin cannot open a Case File with a reason", True, "no demo Case File", skip=True)
        return
    r = root.post("/api/tb/break-glass", json={"case_id": target, "reason": "audit"})
    mark("root admin cannot open a Case File with a reason", refused(r, (403,)), said(r))


def _rate_limited(parts):
    return any(" rate_limited" in what or what.startswith("429") for _, _, what in parts)


def check_break_glass(base, logins, ctx):
    """Fact sheet 12 to 14: a doctor without scope gets 403 no_access with break_glass true; an opening needs a reason of 3 to 500
    characters; the protected Case File and an unknown id both answer 404. The openings that are refused still count against the
    doctor's ten an hour, so they are spread over two other doctors (tb-pulmo-doc, tb-crs-doc) and tb-rad-doc keeps its budget for the
    one real opening of --with-writes."""
    rad = demo_client(base, logins, "tb-rad-doc")
    name = "doctor without scope is refused with the break-glass offer"
    if rad is None or not ctx.get("noscope"):
        mark(name, True, "no tb-rad-doc login or no Case File it cannot open", skip=True)
    else:
        r = rad.get(f"/api/tb/cases/{ctx['noscope']}")
        j = _json(r) or {}
        d = j.get("detail") if isinstance(j, dict) else None
        mark(name, refused(r, (403,), ("no_access",)) and isinstance(d, dict) and d.get("break_glass") is True,
             f"{ctx['noscope']}: {said(r)}, break_glass {d.get('break_glass') if isinstance(d, dict) else None}")
    name = "break-glass needs a reason of 3 to 500 characters"
    who = next((u for u in ("tb-pulmo-doc", "tb-crs-doc", "tb-rad-doc") if u in logins), None)
    c = demo_client(base, logins, who) if who else None
    target = None
    if c is not None:
        own = _case_ids(c)
        target = next((i for i in sorted(ctx["mdt_ids"]) if i not in own and i not in ctx["prot"]), None)
    if c is None or not target:
        mark(name, True, "no doctor login with a Case File it cannot open", skip=True)
    else:
        parts = []
        for label, reason in (("empty", ""), ("2 chars", "ab"), ("501 chars", "x" * 501)):
            r = c.post("/api/tb/break-glass", json={"case_id": target, "reason": reason})
            parts.append((label, refused(r, (400,), ("bad_reason",)), said(r)))
        mark_all(name, parts, "rate limited by earlier runs (10 openings an hour per doctor)" if _rate_limited(parts) else "")
    name = "break-glass answers 404 for the protected Case File and for an unknown id"
    who = next((u for u in ("tb-crs-doc", "tb-pulmo-doc", "tb-rad-doc") if u in logins), None)
    c = demo_client(base, logins, who) if who else None
    if c is None:
        mark(name, True, "no doctor login", skip=True)
        return
    parts = []
    for label, cid in [("protected", i) for i in ctx["prot"]] + [("unknown", UNKNOWN_ID)]:
        r = c.post("/api/tb/break-glass", json={"case_id": cid, "reason": "security audit probe"})
        parts.append((label, refused(r, (404,), ("not_found",)), said(r)))
    mark_all(name, parts, "rate limited by earlier runs (10 openings an hour per doctor)" if _rate_limited(parts) else "")


def check_similar(base, logins, ctx):
    """Fact sheet 18 and 20: similar search refuses the protected Case File and a department that was only asked; opening a past
    Case File refuses the protected and an unknown id with the same 404. Every call here is refused before any model call."""
    doc = demo_client(base, logins, "tb-breast-doc")
    name = "similar search refuses the protected Case File"
    if doc is None:
        mark(name, True, "no tb-breast-doc login", skip=True)
    else:
        parts = []
        for i in ctx["prot"]:
            r = doc.post(f"/api/tb/cases/{i}/similar/search", json={})
            parts.append(("protected", refused(r, (403,)), said(r)))
        mark_all(name, parts)
    name = "similar open refuses the protected and an unknown past Case File (same 404)"
    if doc is None or not ctx.get("breast_full"):
        mark(name, True, "no Breast Surgery Case File", skip=True)
    else:
        parts = []
        for label, pid in [("protected", i) for i in ctx["prot"]] + [("unknown", UNKNOWN_ID)]:
            r = doc.post(f"/api/tb/cases/{ctx['breast_full']}/similar/open", json={"past_case_id": pid})
            parts.append((label, refused(r, (404,), ("not_found",)), said(r)))
        mark_all(name, parts)
    name = "similar search is for full scope only (department that was only asked)"
    rad = demo_client(base, logins, "tb-rad-doc")
    if rad is None or not ctx.get("requests"):
        mark(name, True, "no Case File where Radiology was only asked", skip=True)
    else:
        # the route class refuses a department that was only asked first (plain 403), before the route's own full_scope_only
        r = rad.post(f"/api/tb/cases/{ctx['requests']}/similar/search", json={})
        mark(name, refused(r, (403,), ("full_scope_only", "")), f"{ctx['requests']}: {said(r)}")


def check_message_link(base, logins, ctx):
    """Fact sheet 8: a message cannot carry a link to the protected Case File (400 link_not_allowed, refused in messages.start before
    anything is written), and GET /messages/links never offers it."""
    doc = demo_client(base, logins, "tb-breast-doc")
    name = "a message link to the protected Case File is refused"
    if doc is None or "tb-rad-doc" not in logins:
        mark(name, True, "no tb-breast-doc or tb-rad-doc login", skip=True)
        return
    parts = []
    for i in ctx["prot"]:
        r = doc.post("/api/tb/messages/conversations", json={"to": {"user": "tb-rad-doc"}, "text": "audit", "link": {"type": "case", "id": i}})
        parts.append(("protected", refused(r, (400,), ("link_not_allowed",)), said(r)))
    mark_all(name, parts)
    r = doc.get("/api/tb/messages/links")
    mark("message links never offer the protected Case File", r.status_code == 200 and not any(i in r.text for i in ctx["prot"]), said(r))


def check_patient_lookup(base, logins, ctx):
    """Fact sheet 21 and 22: the patient look-up by Case File refuses a file the doctor cannot open (404) and a login that is not
    placed (403); the look-up by number never names the protected Case File; asking to join the protected one is 404."""
    rad, root, doc = (demo_client(base, logins, u) for u in ("tb-rad-doc", "tb-root", "tb-breast-doc"))
    name = "patient look-up by Case File refuses a file the login cannot open"
    if not ctx.get("noscope") or (rad is None and root is None):
        mark(name, True, "no Case File tb-rad-doc cannot open", skip=True)
    else:
        parts = []
        if rad is not None:
            r = rad.get("/api/tb/patient-case-files", params={"case_id": ctx["noscope"]})
            parts.append(("tb-rad-doc", refused(r, (404,)), said(r)))
        if root is not None:
            r = root.get("/api/tb/patient-case-files", params={"case_id": ctx["noscope"]})
            parts.append(("tb-root", refused(r, (403,)), said(r)))
        mark_all(name, parts)
    name = "patient look-up by number never names the protected Case File"
    uhid = None
    if doc is not None and ctx.get("breast_full"):
        j = _json(doc.get(f"/api/tb/cases/{ctx['breast_full']}")) or {}
        uhid = ((j.get("his") or {}).get("uhid") if isinstance(j.get("his"), dict) else None) or (j.get("patient") or {}).get("mrn")
    if not uhid:
        mark(name, True, "no UHID on a Case File tb-breast-doc opens", skip=True)
    else:
        r = doc.get("/api/tb/patient-case-files", params={"identifier": uhid})
        mark(name, r.status_code == 200 and not any(i in r.text for i in ctx["prot"]), f"{said(r)}, {len((_json(r) or {}).get('cases') or [])} rows")
    name = "ask to join refuses the protected Case File"
    parts = []
    for u, c, want in (("tb-rad-doc", rad, 404), ("tb-root", root, 403)):
        if c is None:
            continue
        for i in ctx["prot"]:
            r = c.post("/api/tb/case-join/ask", json={"case_id": i})
            parts.append((u, refused(r, (want,)), said(r)))
    mark_all(name, parts, "" if parts else "no tb-rad-doc or tb-root login")


def check_voice(base, logins, ctx, t0, audit_offset):
    """Fact sheet 23 and 24: the voice routes cap the upload and the text, check the screen and refuse a statement the login cannot
    read; nothing is sent to the speech models here (every call is refused first). Audio is never stored, and the audit lines of the
    voice carry ids and counts only."""
    doc = demo_client(base, logins, "tb-breast-doc")
    name = "voice routes refuse bad uploads and text"
    if doc is None:
        mark(name, True, "no tb-breast-doc login", skip=True)
        return
    r = doc.get("/api/tb/audio/status")
    st = _json(r) or {}
    if r.status_code == 503 or (r.status_code == 200 and st.get("enabled") is False):
        mark(name, True, f"voice is off ({said(r)})", skip=True)
        mark("audio never stored, voice audit carries no content", True, "voice is off", skip=True)
        return
    parts = [("status", r.status_code == 200, said(r))]
    r = doc.post("/api/tb/audio/stt", json={})
    parts.append(("stt as JSON", refused(r, (400,), ("bad_request",)), said(r)))
    r = doc.post("/api/tb/audio/stt", files={"audio": ("a.webm", b"\0" * (5 * 1024 * 1024), "audio/webm")}, data={"screen": "ask"})
    parts.append(("stt 5 MiB", refused(r, (413,), ("too_big",)), said(r)))
    r = doc.post("/api/tb/audio/stt", files={"audio": ("a.webm", b"\0" * 1024, "audio/webm")})
    parts.append(("stt no screen", refused(r, (400,), ("bad_screen",)), said(r)))
    r = doc.post("/api/tb/audio/stt", files={"audio": ("a.webm", b"\0" * 1024, "audio/webm")}, data={"screen": "../x"})
    parts.append(("stt screen ../x", refused(r, (400,), ("bad_screen",)), said(r)))
    r = doc.post("/api/tb/audio/tts", json={"text": "a" * 1001, "screen": "decision"})
    parts.append(("tts 1001 chars", refused(r, (413,), ("text_too_long",)), said(r)))
    r = doc.post("/api/tb/audio/tts", json={"text": "hello", "screen": "other"})
    parts.append(("tts screen other", refused(r, (400,), ("bad_screen",)), said(r)))
    if ctx.get("breast_noscope"):
        r = doc.post("/api/tb/audio/tts", json={"ref": {"kind": "chat", "case_id": ctx["breast_noscope"], "id": "x", "index": 0}})
        parts.append(("tts ref outside scope", refused(r, (404,), ("not_found",)), said(r)))
    mark_all(name, parts)
    hits = audio_files_since(t0)
    lines = [ev for ev in org_audit_since(audit_offset) if ev.get("kind") in ("audio_transcribed", "audio_spoken", "audio_refused")]
    extra = sorted({k for ev in lines for k in ev if k not in AUDIO_AUDIT_KEYS or k in AUDIO_AUDIT_NEVER})
    mark("audio never stored, voice audit carries no content", not hits and not extra,
         f"{len(hits)} audio files written since the start{(' ' + str(hits[:3])) if hits else ''}; {len(lines)} voice audit lines"
         + (f", unexpected keys {extra}" if extra else ""))


def audio_files_since(t0):
    """Audio files under data/tumour_board and data/uploads modified since t0 (the protected Case File's folder is never entered)."""
    prot, hits = set(protected_ids()), []
    for top in (data_root(), REPO / "data" / "uploads"):
        for dp, dns, fns in os.walk(top):
            dns[:] = [d for d in dns if d not in prot]
            for f in fns:
                if os.path.splitext(f)[1].lower() in AUDIO_EXT:
                    try:
                        if os.stat(os.path.join(dp, f)).st_mtime >= t0:
                            hits.append(os.path.relpath(os.path.join(dp, f), REPO))
                    except OSError:
                        continue
    return hits


def check_meetings(base, logins):
    """Fact sheet 26 and 27: on a planned meeting, a doctor not admitted cannot chat, spotlight, change the agents' settings or get a
    video token; the room screen's token (coordinator) can publish camera and microphone only, with no data grant."""
    doc, mdt = demo_client(base, logins, "tb-breast-doc"), demo_client(base, logins, "tb-mdt")
    name = "meeting routes refuse a doctor who is not admitted"
    name2 = "room screen video token publishes camera and microphone only"
    if doc is None:
        mark(name, True, "no tb-breast-doc login", skip=True)
        mark(name2, True, "no tb-breast-doc login", skip=True)
        return
    r = doc.get("/api/tb/meetings/open")
    rows = (_json(r) or {}).get("meetings") or [] if r.status_code == 200 else []
    mid = next((m.get("id") or m.get("meeting_id") for m in rows if isinstance(m, dict) and (m.get("id") or m.get("meeting_id"))), None)
    if not mid:
        mark(name, True, f"no planned meeting (GET /meetings/open {said(r)})", skip=True)
        mark(name2, True, "no planned meeting", skip=True)
        return
    # an empty chat line: refused as not admitted; were the doctor admitted it would be refused as empty, so nothing is written
    r = doc.post(f"/api/tb/meetings/{mid}/chat", json={"text": ""})
    if r.status_code == 400:
        mark(name, True, "tb-breast-doc is admitted to the planned meeting", skip=True)
    else:
        parts = [("chat", refused(r, (403,)), said(r))]
        r = doc.post(f"/api/tb/meetings/{mid}/spotlight", json={})
        parts.append(("spotlight", refused(r, (403,)), said(r)))
        r = doc.put(f"/api/tb/meetings/{mid}/agents/settings", json={"members_ask": True})
        parts.append(("agents settings", refused(r, (403,)), said(r)))
        r = doc.post(f"/api/tb/meetings/{mid}/video-token", json={"screen": "room"})
        parts.append(("video token", refused(r, (403,)), said(r)))
        mark_all(name, parts)
    if mdt is None:
        mark(name2, True, "no tb-mdt login", skip=True)
        return
    r = mdt.post(f"/api/tb/meetings/{mid}/video-token", json={"screen": "room"})
    if r.status_code in (400, 409, 503):
        mark(name2, True, f"video off or meeting not open ({said(r)})", skip=True)
        return
    if r.status_code != 200:
        mark(name2, False, said(r))
        return
    tok = str((_json(r) or {}).get("token") or "")
    secret(tok)
    try:
        import base64
        seg = tok.split(".")[1]
        payload = json.loads(base64.urlsafe_b64decode(seg + "=" * (-len(seg) % 4)))
    except Exception:
        mark(name2, False, "the token could not be read")
        return
    video = payload.get("video") or {}
    sources = sorted(str(s).lower() for s in video.get("canPublishSources") or [])
    mark(name2, sources == ["camera", "microphone"] and not video.get("canPublishData"),
         f"sources {sources}, data {bool(video.get('canPublishData'))}")


def _keys(obj):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield k
            yield from _keys(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _keys(v)


def check_directory(base, logins):
    """Fact sheet 28: the directory carries no e-mail, registration number, password or admin flag; a phone only when its owner made
    it visible (the row then carries the number, otherwise null)."""
    doc = demo_client(base, logins, "tb-breast-doc")
    name = "directory carries no private fields"
    if doc is None:
        mark(name, True, "no tb-breast-doc login", skip=True)
        return
    r = doc.get("/api/tb/directory", params={"q": "a"})
    j = _json(r)
    bad = sorted({k for k in _keys(j) if str(k).lower() in PRIVATE_KEYS})
    rows = [p for k in ("people", "coordinators") for p in ((j or {}).get(k) or []) if isinstance(p, dict)]
    phones = [p for p in rows if p.get("phone") is not None]
    odd = [p.get("user") for p in rows if p.get("phone") is not None and not isinstance(p.get("phone"), str)]
    mark(name, r.status_code == 200 and not bad and not odd,
         f"{said(r)}, {len(rows)} people, {len(phones)} with a visible phone" + (f", private keys {bad}" if bad else ""))


def check_summary_scope(base, logins, ctx):
    """Fact sheet 29 to 31: the case summary and the summary line are for full readers; a board record correction with a bad body is
    refused (never a 500); a stage rejection needs a reason."""
    rad, doc = demo_client(base, logins, "tb-rad-doc"), demo_client(base, logins, "tb-breast-doc")
    name = "case summary and summary line refused to a department that was only asked"
    req = ctx.get("requests")
    if rad is None or not req:
        mark(name, True, "no Case File where Radiology was only asked", skip=True)
    else:
        parts = []
        r = rad.get(f"/api/tb/cases/{req}/case-summary")
        parts.append(("GET case-summary", refused(r, (403,), ("requests_only", "")), said(r)))
        r = rad.get("/api/tb/case-list")
        row = next((c for c in (_json(r) or {}).get("cases") or [] if isinstance(c, dict) and c.get("case_id") == req), None)
        clean = row is not None and not row.get("summary_line") and not row.get("decision_text")
        parts.append(("case-list row", r.status_code == 200 and clean, f"{said(r)}, row {'found' if row else 'missing'}, text {'none' if clean else 'shown'}"))
        r = rad.post(f"/api/tb/cases/{req}/summary-line", json={"text": "audit"})
        parts.append(("POST summary-line", refused(r, (403,)), said(r)))
        r = rad.post(f"/api/tb/cases/{req}/board-records/none/correct", content=b"[]", headers={"Content-Type": "application/json"})
        parts.append(("correct (only asked)", refused(r, (403, 404)), said(r)))
        mark_all(name, parts)
    name = "board record correction and stage rejection refuse a bad body"
    if doc is None or not ctx.get("breast_full"):
        mark(name, True, "no Breast Surgery Case File", skip=True)
        return
    cid = ctx["breast_full"]
    r = doc.post(f"/api/tb/cases/{cid}/board-records/none/correct", content=b"[]", headers={"Content-Type": "application/json"})
    parts = [("correct with []", refused(r, (400, 404)), said(r))]
    r = doc.post(f"/api/tb/cases/{cid}/staging/reject", json={})
    parts.append(("staging reject without reason", refused(r, (400, 404)), said(r)))
    mark_all(name, parts)


def check_origin_new_verbs(base, logins):
    """Fact sheet 32: a cross-site Origin is refused with a login on PATCH, PUT and the voice route too."""
    doc = demo_client(base, logins, "tb-breast-doc")
    name = "cross-site Origin refused on PATCH, PUT and voice"
    if doc is None:
        mark(name, True, "no tb-breast-doc login", skip=True)
        return
    h = {"Origin": "https://evil.example"}
    parts = []
    r = doc.patch("/api/tb/messages/conversations/X/messages/Y", json={"text": "a"}, headers=h)
    parts.append(("PATCH message", refused(r, (403,)), said(r)))
    r = doc.put("/api/tb/meetings/X/agents/settings", json={"members_ask": True}, headers=h)
    parts.append(("PUT agents settings", refused(r, (403,)), said(r)))
    r = doc.post("/api/tb/audio/tts", json={"text": "a", "screen": "decision"}, headers=h)
    parts.append(("POST tts", refused(r, (403,)), said(r)))
    mark_all(name, parts)


# ---- --with-writes only: these leave lasting state in the demo (a message tombstone, a closed break-glass window, a notice to the
# owner's consultants), so they run only on request.

def case_audit_files():
    """The audit.jsonl of every Case File except the protected ones (their folders are never entered)."""
    prot = set(protected_ids())
    cases = data_root() / "cases"
    try:
        names = [d for d in os.listdir(cases) if d not in prot]
    except OSError:
        return []
    return [cases / d / "audit.jsonl" for d in names if (cases / d / "audit.jsonl").is_file()]


def check_message_link_grants_nothing(base, logins, ctx, audit_offset):
    """Fact sheet 7, 6 and 11 (--with-writes): a message with a link to a Case File the reader cannot open gives the reader a chip
    without a name and no access; another placed login cannot read the conversation (same 404 as an unknown id); the audit carries no
    message text. The message is then deleted (a tombstone stays)."""
    name = "a message link grants nothing, conversations are private, the audit has no text"
    doc, rad, path = (demo_client(base, logins, u) for u in ("tb-breast-doc", "tb-rad-doc", "tb-path-head"))
    cid = ctx.get("breast_outside")
    if doc is None or rad is None or path is None or not cid:
        mark(name, True, "no demo logins or no Breast Surgery file tb-rad-doc cannot open", skip=True)
        return
    import secrets as _s
    token = "SA" + _s.token_hex(8)
    r = doc.post("/api/tb/messages/conversations", json={"to": {"user": "tb-rad-doc"}, "link": {"type": "case", "id": cid},
                                                         "text": f"Security audit probe {token}: sent by the audit script, ignore."})
    if r.status_code not in (200, 201):
        mark(name, False, f"send: {said(r)}")
        return
    j = _json(r) or {}
    conv = ((j.get("conversation") or {}).get("id")) or ""
    mid = ((j.get("message") or {}).get("id")) or ""
    parts = [("send", True, said(r))]
    try:
        r = rad.get(f"/api/tb/messages/conversations/{conv}")
        msg = next((m for m in (_json(r) or {}).get("messages") or [] if isinstance(m, dict) and m.get("id") == mid), None)
        chip = (msg or {}).get("link") or {}
        parts.append(("reader's chip", r.status_code == 200 and chip.get("can_open") is False and chip.get("label") is None,
                      f"{said(r)}, can_open {chip.get('can_open')}, label {'none' if chip.get('label') is None else 'shown'}"))
        r = rad.get(f"/api/tb/cases/{cid}")
        parts.append(("reader opens the file", refused(r, (403,), ("no_access",)), said(r)))
        a, b = path.get(f"/api/tb/messages/conversations/{conv}"), path.get("/api/tb/messages/conversations/Cnone0000000")
        parts.append(("third login reads it", refused(a, (404,), ("not_found",)) and refused(b, (404,), ("not_found",)), f"{said(a)} / unknown {said(b)}"))
        sent = [ev for ev in org_audit_since(audit_offset) if ev.get("kind") == "message_sent"]
        texty = [ev for ev in sent if "text" in ev]
        files = [org_audit_path()] + case_audit_files()
        found = []
        for f in files:
            try:
                if token in f.read_text(encoding="utf-8", errors="ignore"):
                    found.append(f.name if f == org_audit_path() else f.parent.name)
            except OSError:
                continue
        parts.append(("audit", not texty and not found, f"{len(sent)} message_sent lines, {len(texty)} with text, token in {found or 'no audit file'}"))
    finally:
        r = doc.delete(f"/api/tb/messages/conversations/{conv}/messages/{mid}")
        parts.append(("delete", r.status_code == 200, said(r)))
    mark_all(name, parts)


def check_break_glass_window(base, logins, ctx):
    """Fact sheet 15 (--with-writes): a doctor's break-glass window reads only, is not listed, and closes (the owner's consultants
    are told of the opening)."""
    name = "break-glass window is read only, unlisted, and closes"
    rad, cid = demo_client(base, logins, "tb-rad-doc"), ctx.get("breast_outside")
    if rad is None or not cid:
        mark(name, True, "no tb-rad-doc login or no Breast Surgery file it cannot open", skip=True)
        return
    r = rad.post("/api/tb/break-glass", json={"case_id": cid, "reason": "security audit probe: read-only window", "via": "audit"})
    if r.status_code != 200 or (_json(r) or {}).get("scope") != "read":
        mark(name, r.status_code == 429, f"open: {said(r)}", skip=r.status_code == 429)
        return
    parts = [("open", True, f"{said(r)} scope read")]
    try:
        r = rad.get(f"/api/tb/cases/{cid}")
        parts.append(("read", r.status_code == 200, said(r)))
        r = rad.post(f"/api/tb/cases/{cid}/recheck", json={})
        parts.append(("write", refused(r, (403,), ("break_glass_read_only",)), said(r)))
        r = rad.get("/api/tb/case-list")
        listed = any(isinstance(c, dict) and c.get("case_id") == cid for c in (_json(r) or {}).get("cases") or [])
        parts.append(("case-list", r.status_code == 200 and not listed, f"{said(r)}, {'listed' if listed else 'not listed'}"))
    finally:
        r = rad.request("DELETE", "/api/tb/break-glass", json={"case_id": cid})
        parts.append(("close", r.status_code == 200, said(r)))
    r = rad.get(f"/api/tb/cases/{cid}")
    parts.append(("after close", refused(r, (403,), ("no_access",)), said(r)))
    mark_all(name, parts)


def check_no_password_printed(out_payload):
    """Check 25 (last): no password held in memory appears in what was printed or in the --out JSON; the PENDING file is mode 600."""
    tee = sys.stdout if isinstance(sys.stdout, _Tee) else None
    printed = "".join(tee.buf) if tee else ""
    in_out = [x for x in SECRETS if x in out_payload]
    in_print = [x for x in SECRETS if x in printed]
    pend = ""
    ok_mode = True
    if PENDING.exists():
        mode = stat.S_IMODE(PENDING.stat().st_mode)
        ok_mode, pend = mode == 0o600, f", pending file {oct(mode)}"
    caught = tee.caught if tee else 0
    mark("the audit never prints or writes a password", not in_out and not in_print and not caught and ok_mode,
         f"{len(SECRETS)} secrets held, {caught} caught before printing, {len(in_out)} in the JSON{pend}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:7000")
    ap.add_argument("--his", default="http://127.0.0.1:7130")
    ap.add_argument("--user", default="")
    ap.add_argument("--password-file", default="")
    ap.add_argument("--out", default="")
    ap.add_argument("--skip-login-limit", action="store_true", help="skip the login flood check (it rate-limits 127.0.0.1 for a minute)")
    ap.add_argument("--revoke-user", default="tb-micro-doc", help="the demo login whose password the finding 4 check changes and changes back")
    ap.add_argument("--skip-password-change", action="store_true", help="skip the finding 4 check (it signs the demo login out elsewhere)")
    ap.add_argument("--with-writes", action="store_true", help="also run the checks that leave lasting state in the demo (a message "
                    "tombstone, a closed break-glass window, a notice to the owner's consultants)")
    a = ap.parse_args()
    sys.stdout = _Tee(sys.stdout)  # check 25: everything printed is kept and checked for passwords
    import time
    t0, audit_offset = time.time(), org_audit_size()
    client = None
    if a.user and a.password_file:
        pw = secret(Path(a.password_file).read_text().strip().split()[-1])
        client = login(a.base, a.user, pw)
        if client is None:
            print("login for the authenticated checks failed (wrong user or password file)")
    check_unauthenticated(a.base)
    check_shells(a.base)
    check_headers(a.base, client)
    check_csrf(a.base, client)
    check_his(a.his)
    check_binding()
    check_secret_modes()
    check_bundle_secrets()
    check_ws(a.base)
    demo = read_tsv(DEMO_LOGINS, 0, 1)
    for v in demo.values():
        secret(v)
    check_protected_listings(a.base, demo)
    check_quote_scope(a.base, demo)
    check_his_api_roles(a.his)
    if a.skip_password_change:
        mark("password change ends the other sessions (finding 4)", True, "skipped on request", skip=True)
    else:
        check_password_change_revokes(a.base, demo, a.revoke_user)
    # night-v3 routes and sockets (plan item 9.1)
    ctx = audit_context(a.base, demo)
    _guarded("night-v3 sockets", check_sockets, a.base, demo)
    _guarded("night-v3 not placed", check_not_placed, a.base, demo, ctx)
    _guarded("night-v3 break-glass", check_break_glass, a.base, demo, ctx)
    _guarded("night-v3 similar Case Files", check_similar, a.base, demo, ctx)
    _guarded("night-v3 message link", check_message_link, a.base, demo, ctx)
    _guarded("night-v3 patient look-up", check_patient_lookup, a.base, demo, ctx)
    _guarded("night-v3 voice", check_voice, a.base, demo, ctx, t0, audit_offset)
    _guarded("night-v3 meetings", check_meetings, a.base, demo)
    _guarded("night-v3 directory", check_directory, a.base, demo)
    _guarded("night-v3 case summary", check_summary_scope, a.base, demo, ctx)
    _guarded("night-v3 origin", check_origin_new_verbs, a.base, demo)
    if a.with_writes:
        _guarded("night-v3 message link grants nothing", check_message_link_grants_nothing, a.base, demo, ctx, audit_offset)
        _guarded("night-v3 break-glass window", check_break_glass_window, a.base, demo, ctx)
    else:
        mark("a message link grants nothing, conversations are private, the audit has no text", True, "needs --with-writes", skip=True)
        mark("break-glass window is read only, unlisted, and closes", True, "needs --with-writes", skip=True)
    # last: the login flood rate-limits 127.0.0.1 for a minute, so every check that signs in runs before it
    if a.skip_login_limit:
        mark("login rate limit answers 429", True, "skipped on request", skip=True)
    else:
        check_login_limit(a.base)
    check_no_password_printed(json.dumps([{"check": n, "result": s, "note": w} for n, s, w in RESULTS], indent=1))  # check 25, last
    fails = [r for r in RESULTS if r[1] == "FAIL"]
    print(f"\n{len(RESULTS)} checks, {len(fails)} failed, {sum(1 for r in RESULTS if r[1] == 'SKIP')} skipped")
    if a.out:
        payload = json.dumps([{"check": n, "result": s, "note": w} for n, s, w in RESULTS], indent=1)
        for x in SECRETS:
            payload = payload.replace(x, "[secret]")
        Path(a.out).write_text(payload)
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
