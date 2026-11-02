"""Makes sure the night-v3 resident login exists, works and is on the team of TB-DEMO-P19 (for the baseline screenshots).

    /data/vaidyx/venv/app/bin/python docs/night-v3/tools/ensure_resident.py

The demo has no resident login, so one is placed in the demo Breast Surgery department the way tumour_board/eval/e2e_nik.py
(step0_resident) does it: the Breast Surgery department admin (tb-breast-admin) adds "night-v3.resident@vaidyx-demo.invalid" as a
resident (end date today plus 180 days), resets its password (the first password comes back inside a mailto), and the resident signs in
and chooses a new random password (the forced change). The treating doctor (tb-breast-doc) then gives the team's join code of
TB-DEMO-P19 (the code already shown on the Team panel, or a new one) and the resident joins with POST /case-join.

The login is saved as "<user> <password>" in /data/vaidyx/night-v3/.resident_login (mode 600, outside the repo). When that file exists
and its login works, nothing is changed (only the team join is checked). Demo passwords are read from ~/vaidyx/.tb_v2_demo_logins in
code. No password or code is ever printed. Synthetic demo data only; never the real case. Exit code 0 on success, 1 with a plain
message otherwise.
"""
import os
import re
import secrets
import sys
import time
import urllib.parse
from datetime import date, timedelta
from pathlib import Path

import httpx

VAIDYX = os.environ.get("TBNIK_BASE_URL", "http://127.0.0.1:7000")
DEMO_LOGINS = Path.home() / "vaidyx" / ".tb_v2_demo_logins"
LOGIN_FILE = Path("/data/vaidyx/night-v3/.resident_login")
RESIDENT = "night-v3.resident@vaidyx-demo.invalid"
RESIDENT_NAME = "Dr Meera (night-v3 resident, demo)"
DEPT = "breast_surgery"
DEPT_ADMIN = "tb-breast-admin"
TREATING = "tb-breast-doc"
CASE = "TB-DEMO-P19"
HEADERS = {"X-Requested-With": "tb-nik"}


class Failed(Exception):
    """A step failed; the message is plain words and never carries a password or a code."""


def j(r):
    try:
        return r.json()
    except ValueError:
        return {}


def demo_password(user):
    """The demo login's password (the file is whitespace separated: username, password, then words)."""
    if not DEMO_LOGINS.exists():
        raise Failed(f"the demo logins file {DEMO_LOGINS} is missing")
    for line in DEMO_LOGINS.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        parts = line.split()
        if len(parts) >= 2 and parts[0] == user:
            return parts[1]
    raise Failed(f"no demo login for {user} in {DEMO_LOGINS}")


def sign_in(user, password, quiet=False):
    """A client signed in as `user`, or None when the login is refused and `quiet` is set."""
    c = httpx.Client(base_url=VAIDYX, timeout=60, headers=HEADERS)
    r = None
    for _ in range(4):
        r = c.post("/api/auth/login", json={"username": user, "password": password, "remember": False})
        if r.status_code != 429:
            break
        time.sleep(20)  # the sign-in limiter (15 a minute) is shared with whoever else signs in on this server
    if r.status_code == 200 and c.cookies.get("vaidyx_session"):
        return c
    c.close()
    if quiet:
        return None
    raise Failed(f"sign-in as {user} refused (HTTP {r.status_code})")


def read_saved():
    if not LOGIN_FILE.exists():
        return None
    parts = LOGIN_FILE.read_text(encoding="utf-8").split()
    return (parts[0], parts[1]) if len(parts) >= 2 else None


def save(user, password):
    LOGIN_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = LOGIN_FILE.with_name(LOGIN_FILE.name + ".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(f"{user} {password}\n")
    os.chmod(tmp, 0o600)
    os.replace(tmp, LOGIN_FILE)


def usable(c):
    """Signed in, no forced password change and placed as a resident of Breast Surgery."""
    me = j(c.get("/api/tb/me"))
    return not me.get("must_change_password") and ((me.get("roles") or {}).get("departments") or {}).get(DEPT) == "resident"


def make_resident():
    """Places (or re-places) the resident, resets its password and lets it choose a new one. Returns a signed-in client."""
    adm = sign_in(DEPT_ADMIN, demo_password(DEPT_ADMIN))
    end = (date.today() + timedelta(days=180)).isoformat()
    r = adm.post(f"/api/tb/departments/{DEPT}/people", json={"email": RESIDENT, "display_name": RESIDENT_NAME, "role": "resident", "end_date": end})
    if r.status_code != 200:
        raise Failed(f"the Breast Surgery department admin could not place the resident (HTTP {r.status_code}: {str(j(r).get('detail'))[:200]})")
    b = j(r)
    mailto = b.get("mailto") or ""
    how = "created"
    if not mailto:  # the account exists already: a reset gives a new first password inside a mailto
        r = adm.post(f"/api/tb/accounts/{urllib.parse.quote(RESIDENT)}/reset-password", json={"email": RESIDENT})
        mailto = j(r).get("mailto") or ""
        how = "existed; password reset by the department admin"
        if r.status_code != 200 or not mailto:
            raise Failed(f"the department admin could not reset the resident's password (HTTP {r.status_code})")
    adm.close()
    body = urllib.parse.parse_qs(urllib.parse.urlsplit(mailto).query).get("body", [""])[0]
    m = re.search(r"First password: (\S+)", body)
    if not m:
        raise Failed("the mailto carries no first password")
    first = m.group(1)
    res = sign_in(RESIDENT, first)
    new = "N3r-" + secrets.token_urlsafe(18)
    r = res.post("/api/tb/me/password", json={"current_password": first, "new_password": new})
    if r.status_code != 200 or j(r).get("must_change_password") is not False:
        raise Failed(f"the resident could not set a new password (HTTP {r.status_code}: {str(j(r).get('detail'))[:200]})")
    save(RESIDENT, new)
    if not usable(res):
        raise Failed("the resident signs in but is not placed as a resident of Breast Surgery")
    print(f"resident {RESIDENT}: account {how}, new password set and saved to {LOGIN_FILE} (mode 600)")
    return res


def ensure_join(res):
    """The resident on the team of TB-DEMO-P19 (join code from the treating doctor, then /case-join). Returns a plain status line."""
    t = res.get(f"/api/tb/cases/{CASE}/team")
    if t.status_code == 200 and (j(t).get("can") or {}).get("leave"):
        return f"already on the team of {CASE}"
    doc = sign_in(TREATING, demo_password(TREATING))
    try:
        team = j(doc.get(f"/api/tb/cases/{CASE}/team"))
        if any(x.get("user") == RESIDENT for x in team.get("residents") or []):
            return f"already on the team of {CASE}"
        if not (team.get("can") or {}).get("manage"):
            raise Failed(f"{TREATING} may not manage the team of {CASE}; join skipped")
        code = ((team.get("join_code") or {}).get("code") or "").strip()
        how = "the existing join code"
        if not re.fullmatch(r"\d{6}", code):
            r = doc.post(f"/api/tb/cases/{CASE}/team/code")
            code = (j(r).get("code") or "").strip()
            how = "a new join code from the treating doctor"
            if r.status_code != 200 or not re.fullmatch(r"\d{6}", code):
                raise Failed(f"the treating doctor could not make a join code for {CASE} (HTTP {r.status_code})")
        r = res.post("/api/tb/case-join", json={"code": code})
        status = j(r).get("status")
        if r.status_code != 200 or status not in ("joined", "pending"):
            raise Failed(f"/case-join refused (HTTP {r.status_code}: {str(j(r).get('detail'))[:200]})")
        if status == "pending":
            r = doc.post(f"/api/tb/cases/{CASE}/team/pending/{urllib.parse.quote(RESIDENT)}/approve", json={"note": "night-v3 baseline resident (demo)"})
            if r.status_code != 200:
                raise Failed(f"the join request waits for approval and the approval failed (HTTP {r.status_code})")
            return f"joined the team of {CASE} with {how} (request approved by the treating doctor)"
        return f"joined the team of {CASE} with {how}"
    finally:
        doc.close()


def main():
    saved = read_saved()
    res = None
    if saved and saved[0] == RESIDENT:
        res = sign_in(saved[0], saved[1], quiet=True)
        if res is not None and not usable(res):
            res.close()
            res = None
        if res is not None:
            print(f"resident {RESIDENT}: the saved login in {LOGIN_FILE} works; account left as it is")
    if res is None:
        res = make_resident()
    try:
        # Without the join the screenshots show the first Case File the resident has; the run goes on and says so.
        try:
            print(f"team: {ensure_join(res)}")
        except Failed as e:
            print(f"team: join skipped: {e}")
    finally:
        res.close()
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Failed as e:
        print(f"ensure_resident: {e}", file=sys.stderr)
        sys.exit(1)
    except httpx.HTTPError as e:
        print(f"ensure_resident: the app on {VAIDYX} did not answer ({type(e).__name__})", file=sys.stderr)
        sys.exit(1)
