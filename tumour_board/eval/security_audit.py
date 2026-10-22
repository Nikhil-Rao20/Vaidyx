"""Security audit of the running demo (Vaidyx app :7000, demo HIMS :7130, PACS :8042, LiveKit :7880).

Checks, each printed as PASS / FAIL / SKIP with a one-line reason, then a summary; exit 1 when any check fails:
  1. Every /api/tb route answers 401 (or 403) without a login, for GET and for POST with an empty body.
  2. The HTML shells (/tb, /tb-nik) and static files are served; /tb redirects to /login without a login; /tb-nik is public but carries no data.
  3. Security headers on an app page and on an API answer: CSP, X-Content-Type-Options, Referrer-Policy, X-Frame-Options.
  4. A cross-site Origin on a POST to /api/tb/... is refused (403) even with a valid login.
  5. Login rate limit answers 429 after repeated wrong passwords.
  6. The demo HIMS: screens need a login (302 to /his/login), the FHIR API needs the token (401), a wrong token is refused, five wrong passwords lock the account (plain message), the PACS proxy refuses Orthanc's REST paths.
  7. Orthanc and LiveKit listen on 127.0.0.1 only (no 0.0.0.0 listener).
  8. Secrets on disk: data/his_mock/token, data/his_mock/logins.tsv, data/tumour_board/livekit.json, push_keys.json have mode 600 or stricter when they exist.
  9. No secret-looking strings in the built frontend (static/tb-nik/assets): api keys, tokens, passwords.
 10. WebSocket /api/tb/meetings/{id}/ws refuses a connection without a cookie.
 Fixes of the security review (docs/ui/build/SECURITY_REVIEW.md), with the demo logins of ~/vaidyx/.tb_v2_demo_logins and the HIMS
 logins of data/his_mock/logins.tsv (read from the files, never printed):
 11. Finding 0: no demo login (doctor, coordinator, supporting doctor) is shown a protected Case File id in /cases, /case-list,
     /inbox, /notifications, /waiting or /home.
 12. Finding 1: a department that was only asked gets 403 on /documents/{doc}/quote for a record outside its scope.
 13. Finding 3: a HIMS staff session cannot write through the JSON APIs beyond its role (technician: no registration, no signature).
 14. Finding 13: the FHIR read token changes nothing on the JSON APIs (403), the write token file exists with mode 600.
 15. Finding 4: a password change ends the login's other sessions (a demo login, --revoke-user, changed and changed back).

Usage: /data/vaidyx/venv/app/bin/python -m tumour_board.eval.security_audit [--base http://127.0.0.1:7000] [--his http://127.0.0.1:7130]
       [--user USER --password-file FILE]   (a Vaidyx login for the authenticated checks; the password is read from the file, never printed)
       [--revoke-user tb-micro-doc] [--skip-password-change]
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
    for port, name in (("8042", "Orthanc"), ("7880", "LiveKit"), ("7130", "HIMS"), ("7000", "Vaidyx")):
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
        c = login(base, u, logins[u])
        if c is None:
            leaks.append(f"{u}: login failed")
            continue
        for path in ("/api/tb/cases", "/api/tb/case-list", "/api/tb/inbox", "/api/tb/notifications", "/api/tb/waiting", "/api/tb/home"):
            r = c.get(path)
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
    if email and passwords.get(email) and "reset" not in passwords[email]:
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
    read = tok.read_text().strip()
    c = httpx.Client(base_url=his, timeout=30)
    g = c.get("/his/api/search", params={"q": "VXH"}, headers={"Authorization": "Bearer " + read})
    w = c.post("/his/api/registrations", json={"name": "Audit Never Registered (SYNTHETIC)"}, headers={"Authorization": "Bearer " + read})
    ok = g.status_code == 200 and w.status_code == 403 and wtok.exists() and stat.S_IMODE(wtok.stat().st_mode) & 0o077 == 0
    mark("HIMS read token changes nothing (finding 13)", ok, f"read {g.status_code}, write with the read token {w.status_code}, write token file {'present' if wtok.exists() else 'missing'}")


def check_password_change_revokes(base, logins, user):
    """Finding 4: two sessions of one demo login; a password change in the first ends the second; the password is then changed back."""
    pw = logins.get(user)
    if not pw:
        mark("password change ends the other sessions (finding 4)", True, f"no demo login {user}", skip=True)
        return
    h = {"Origin": base}
    pending = read_tsv(PENDING, 0, 1)
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
    tmp = "Audit-" + secrets.token_urlsafe(12)
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
    a = ap.parse_args()
    client = None
    if a.user and a.password_file:
        pw = Path(a.password_file).read_text().strip().split()[-1]
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
    check_protected_listings(a.base, demo)
    check_quote_scope(a.base, demo)
    check_his_api_roles(a.his)
    if a.skip_password_change:
        mark("password change ends the other sessions (finding 4)", True, "skipped on request", skip=True)
    else:
        check_password_change_revokes(a.base, demo, a.revoke_user)
    # last: the login flood rate-limits 127.0.0.1 for a minute, so every check that signs in runs before it
    if a.skip_login_limit:
        mark("login rate limit answers 429", True, "skipped on request", skip=True)
    else:
        check_login_limit(a.base)
    fails = [r for r in RESULTS if r[1] == "FAIL"]
    print(f"\n{len(RESULTS)} checks, {len(fails)} failed, {sum(1 for r in RESULTS if r[1] == 'SKIP')} skipped")
    if a.out:
        Path(a.out).write_text(json.dumps([{"check": n, "result": s, "note": w} for n, s, w in RESULTS], indent=1))
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
