"""Give the practice Case Files TB-001..TB-008 of the doctors' instance their treating department, so each doctor finds cases at
the first sign-in (they were created by test accounts that do not exist in the instance, and a Case File without an owning
department opens only for the MDT Coordinator).

Run once after setup_instance.py (and after --reset-cases). It signs in as the MDT Coordinator through the gate and uses the
app's own audited route (POST /api/tb/cases/<id>/owner), so every change is an "owner_set" line in that Case File's audit log.
A Case File that already has an owner is left alone (the route answers 409). The password is read from the private logins file
and never printed.

    /data/vaidyx/venv/app/bin/python deploy/h200/demo_owners.py
"""
import http.client
import json
import os
import re

OWNERS = {"TB-001": "pulmonology", "TB-002": "breast_surgery", "TB-003": "colorectal_surgery", "TB-004": "medical_oncology",
          "TB-005": "breast_surgery", "TB-006": "colorectal_surgery", "TB-007": "medical_oncology",  # oral cavity: no head-and-neck login
          "TB-008": "gynaecologic_oncology"}
REASON = "Doctors' demo instance set-up: the practice Case File gets its treating department"
SECRET = open(os.path.expanduser(os.getenv("VX_GATE_SECRET_FILE", "~/vaidyx/deploy_vm/secrets/gate_secret"))).read().strip()
LOGINS = os.path.expanduser(os.getenv("VX_LOGINS", "~/vaidyx/.tb_deploy_logins"))
HEAD = {"Host": os.getenv("VX_PUBLIC_HOST", "vaidyx.tanuh.ai"), "X-Vaidyx-Gate": SECRET,
        "X-Forwarded-For": "127.0.0.2", "X-Forwarded-Proto": "https"}


def call(method, path, body=None, cookie=None):
    c = http.client.HTTPConnection("127.0.0.1", 7301, timeout=60)
    h = dict(HEAD)
    if body is not None:
        h["Content-Type"] = "application/json"
    if cookie:
        h["Cookie"] = cookie
    c.request(method, path, body=json.dumps(body) if body is not None else None, headers=h)
    r = c.getresponse()
    data, headers = r.read(), r.getheaders()
    c.close()
    return r.status, headers, data


def main():
    rows = [l.rstrip("\n").split("\t") for l in open(LOGINS) if re.match(r"^[^\t#]+\t", l)]
    pw = {r[0]: r[1] for r in rows}
    st, hd, _ = call("POST", "/api/auth/login", {"username": "tb-mdt", "password": pw["tb-mdt"]})
    if st != 200:
        raise SystemExit(f"sign-in as tb-mdt failed: HTTP {st}")
    cookie = "; ".join(v.split(";")[0] for k, v in hd if k.lower() == "set-cookie")
    try:
        for cid, dep in OWNERS.items():
            st, _, data = call("POST", f"/api/tb/cases/{cid}/owner", {"department": dep, "reason": REASON}, cookie)
            print(f"{cid}: {dep}: " + ("set" if st == 200 else "already owned, left alone" if st == 409 else f"HTTP {st} {data[:160]!r}"))
    finally:
        call("POST", "/api/auth/logout", {}, cookie)


if __name__ == "__main__":
    main()
