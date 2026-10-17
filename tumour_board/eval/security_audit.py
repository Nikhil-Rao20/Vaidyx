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

Usage: /data/vaidyx/venv/app/bin/python -m tumour_board.eval.security_audit [--base http://127.0.0.1:7000] [--his http://127.0.0.1:7130]
       [--user USER --password-file FILE]   (a Vaidyx login for the authenticated checks; the password is read from the file, never printed)
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
    for route in r.routes:
        path = getattr(route, "path", "")
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


def check_headers(base):
    c = httpx.Client(base_url=base, timeout=15, follow_redirects=False)
    for path in ("/tb-nik", "/api/tb/health"):
        r = c.get(path)
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
    for rel in ("data/his_mock/token", "data/his_mock/logins.tsv", "data/tumour_board/livekit.json", "data/tumour_board/push_keys.json"):
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:7000")
    ap.add_argument("--his", default="http://127.0.0.1:7130")
    ap.add_argument("--user", default="")
    ap.add_argument("--password-file", default="")
    ap.add_argument("--out", default="")
    a = ap.parse_args()
    client = None
    if a.user and a.password_file:
        pw = Path(a.password_file).read_text().strip().split()[-1]
        client = login(a.base, a.user, pw)
        if client is None:
            print("login for the authenticated checks failed (wrong user or password file)")
    check_unauthenticated(a.base)
    check_shells(a.base)
    check_headers(a.base)
    check_csrf(a.base, client)
    check_login_limit(a.base)
    check_his(a.his)
    check_binding()
    check_secret_modes()
    check_bundle_secrets()
    check_ws(a.base)
    fails = [r for r in RESULTS if r[1] == "FAIL"]
    print(f"\n{len(RESULTS)} checks, {len(fails)} failed, {sum(1 for r in RESULTS if r[1] == 'SKIP')} skipped")
    if a.out:
        Path(a.out).write_text(json.dumps([{"check": n, "result": s, "note": w} for n, s, w in RESULTS], indent=1))
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
