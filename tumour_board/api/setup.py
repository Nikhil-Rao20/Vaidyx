"""Guided set-up and accounts for the new interface (18 Oct 2026; SPEC-API setup.py).

Five steps, each saved at once by the root admin: hospital (name, NCG level, type, PM-JAY), departments (which exist, their contacts),
people (invited by email: a login with a generated first password inside a mail draft), hospital system (the HIS url and a test that
must pass), board (coordinators, the heads, the meeting defaults). The step stamps live in org.json hospital.setup_steps {step: {at, by}}.
The first step also answers the old first set-up question (org.first_setup) so the V2 home stops asking it. Accounts: create, reset a
password, change roles; the department admin's people list with residents and end dates. Passwords travel only inside mailto: links.
No model calls."""
import asyncio, copy, hmac, time

from fastapi import Request

from tumour_board import accounts, his_client, org
from tumour_board.api.common import RateLimit, auth_manager, body, fail, make_router, need, roles

router = make_router()
STEPS = ("hospital", "departments", "people", "his", "board")
STEP_LABELS = {"hospital": "Hospital", "departments": "Departments", "people": "People and roles", "his": "Hospital system", "board": "Board"}


def _limits() -> dict:
    try:
        from src.constants import PASSWORD_MIN_LENGTH
        from core.auth import RESERVED_USERNAMES
        return {"reserved": RESERVED_USERNAMES, "min_length": PASSWORD_MIN_LENGTH}
    except Exception:
        return {"reserved": ("api", "demo", "system", "internal-tool"), "min_length": accounts.PASSWORD_MIN}


def _call(fn, *a, **kw):
    try:
        return fn(*a, **kw)
    except accounts.AccountError as e:
        fail(e.status, str(e), "account")
    except ValueError as e:
        fail(400, str(e), "bad_value")


def login_url(request: Request) -> str:
    """Where the invited person signs in (the new interface on this server), for the mail draft."""
    try:
        return str(request.base_url).rstrip("/") + accounts.LOGIN_URL
    except Exception:
        return accounts.LOGIN_URL


def _stamp(o: dict, step: str, by: str) -> None:
    o["hospital"].setdefault("setup_steps", {})
    if not isinstance(o["hospital"]["setup_steps"], dict):
        o["hospital"]["setup_steps"] = {}
    o["hospital"]["setup_steps"][step] = {"at": org.now_iso(), "by": by}


def _save(o: dict, by: str, step: str = "") -> dict:
    try:
        saved = org.save(o, by)
    except ValueError as e:
        fail(400, str(e), "bad_value")
    if step:
        org.audit("setup_step", by, step=step)
    return saved


def _summaries(o: dict, mgr) -> dict:
    h = o["hospital"]
    depts = o["departments"]
    users = {u: v for u, v in (o.get("users") or {}).items() if isinstance(v, dict)}
    enabled = [d for d in depts if d.get("enabled", True)]
    contacts = sum(1 for d in enabled if (d.get("email") and not str(d["email"]).endswith("@" + org.PLACEHOLDER_DOMAIN)) or d.get("phone"))
    his = h.get("his_test") if isinstance(h.get("his_test"), dict) else {}
    return {"hospital": (f"{h.get('name')} ({h.get('level')}" + (", PM-JAY" if h.get("pmjay_empanelled") else "") + ")") if h.get("name") else "not named yet",
            "departments": f"{sum(1 for d in enabled if d.get('group') == 'treating')} treating, {sum(1 for d in enabled if d.get('group') == 'supporting')} supporting; contacts for {contacts}",
            "people": f"{len(users)} login(s): {sum(1 for v in users.values() if v.get('departments'))} placed, {sum(1 for v in users.values() if v.get('coordinator'))} coordinator(s), {len(o.get('admins') or [])} hospital admin(s)",
            "his": ("answers" if his.get("ok") else ("failed: " + str(his.get("error") or ""))[:120]) if his else "not tested",
            "board": f"{len(h.get('board_heads') or [])} head(s), {sum(1 for v in users.values() if v.get('coordinator'))} coordinator(s)"}


def _done(o: dict) -> dict:
    h = o["hospital"]
    stamps = h.get("setup_steps") if isinstance(h.get("setup_steps"), dict) else {}
    his = h.get("his_test") if isinstance(h.get("his_test"), dict) else {}
    return {"hospital": bool(stamps.get("hospital")) or (bool(h.get("name")) and isinstance(h.get("first_setup"), dict)),
            "departments": bool(stamps.get("departments")), "people": bool(stamps.get("people")) or bool(o.get("users")),
            "his": bool(stamps.get("his")) and bool(his.get("ok")), "board": bool(stamps.get("board"))}


def view(mgr=None) -> dict:
    o = org.load()
    h = o["hospital"]
    done, summ = _done(o), _summaries(o, mgr)
    his_cfg = his_client.settings()
    his = h.get("his_test") if isinstance(h.get("his_test"), dict) else {}
    users = {u: v for u, v in (o.get("users") or {}).items() if isinstance(v, dict)}
    return {"steps": [{"id": s, "label": STEP_LABELS[s], "done": done[s], "summary": summ[s]} for s in STEPS], "complete": all(done.values()),
            "hospital": {k: h.get(k) for k in ("name", "level", "type", "pmjay_empanelled", "fetch_window_months", "meeting_defaults")} | {"first_setup": h.get("first_setup")},
            "departments": [{"id": d["id"], "name": d["name"], "group": d.get("group"), "enabled": bool(d.get("enabled", True)), "email": d.get("email") or "", "phone": d.get("phone") or "",
                             "receives_requests": bool(d.get("receives_requests"))} for d in o["departments"]],
            "board": {"coordinators": sorted(u for u, v in users.items() if v.get("coordinator")), "heads": list(h.get("board_heads") or []),
                      "meeting_defaults": h.get("meeting_defaults") or dict(org.DEFAULT_MEETING)},
            "his": {"url": his_cfg.get("url") or "", "kind": his_cfg.get("kind"), "enabled": bool(his_cfg.get("enabled")), "has_token": bool(his_client.token(his_cfg)),
                    "tested_at": his.get("at") or "", "ok": bool(his.get("ok")) if his else None, "error": his.get("error") or ""},
            "levels": list(org.LEVELS), "types": list(org.TYPES), "weekdays": list(org.MEETING_WEEKDAYS)}


@router.get("/setup")
async def get_setup(request: Request):
    r = roles(request); need(r, "manage_org")
    return view(getattr(request.app.state, "auth_manager", None))


@router.post("/setup/hospital")
async def setup_hospital(request: Request):
    """{name, level, type?, pmjay_empanelled}: saved at once; answers the first set-up (org.first_setup) when it is still open."""
    r = roles(request); need(r, "manage_org"); b = await body(request)
    name = " ".join(str(b.get("name") or "").split())
    if not name:
        fail(400, "Give the hospital's name.", "name_required")
    level = str(b.get("level") or "essential").strip().lower()
    if level not in org.LEVELS:
        fail(400, f"Hospital level must be one of: {', '.join(org.LEVELS)}.", "bad_level")
    pmjay = b.get("pmjay_empanelled", True)
    if not isinstance(pmjay, bool):
        fail(400, "PM-JAY empanelled must be true or false.", "bad_value")
    o = copy.deepcopy(org.load())
    if not isinstance(o["hospital"].get("first_setup"), dict):
        try:
            org.first_setup(r["user"], pmjay, name=name, level=level)
        except (org.SetupDone, ValueError) as e:
            fail(400, str(e), "bad_value")
        o = copy.deepcopy(org.load())
    o["hospital"].update({"name": name, "level": level, "type": str(b.get("type") or "") if b.get("type") in org.TYPES else o["hospital"].get("type", ""), "pmjay_empanelled": pmjay})
    if b.get("fetch_window_months") is not None:
        o["hospital"]["fetch_window_months"] = b.get("fetch_window_months")
    _stamp(o, "hospital", r["user"])
    _save(o, r["user"], "hospital")
    return {"ok": True, "step": "hospital", **view()}


@router.post("/setup/departments")
async def setup_departments(request: Request):
    """{enabled[]: department ids the hospital has, contacts{dept: {email, phone}}}: the others are kept but marked disabled."""
    r = roles(request); need(r, "manage_org"); b = await body(request)
    o = copy.deepcopy(org.load())
    enabled = b.get("enabled")
    if enabled is not None:
        if not isinstance(enabled, list):
            fail(400, "enabled must be a list of department ids.", "bad_value")
        ids = {org.department_id(x) for x in enabled if isinstance(x, str)}
        ids.discard(None)
        unknown = [x for x in enabled if isinstance(x, str) and not org.department_id(x)]
        if unknown:
            fail(400, f"Unknown department(s): {', '.join(unknown)}.", "bad_value")
        placed = {d for v in (o.get("users") or {}).values() if isinstance(v, dict) for d in (v.get("departments") or {})}
        for d in o["departments"]:
            d["enabled"] = d["id"] in ids or (d["id"] in placed)  # a department with people placed in it stays enabled
    contacts = b.get("contacts") or {}
    if not isinstance(contacts, dict):
        fail(400, "contacts must map a department to {email, phone}.", "bad_value")
    by_id = {d["id"]: d for d in o["departments"]}
    for key, v in contacts.items():
        did = org.department_id(key)
        if not did or did not in by_id:
            fail(400, f"Unknown department '{key}'.", "bad_value")
        if not isinstance(v, dict):
            fail(400, f"The contacts of {org.department_name(did)} must be {{email, phone}}.", "bad_value")
        if "email" in v:
            by_id[did]["email"] = str(v.get("email") or "").strip()
        if "phone" in v:
            by_id[did]["phone"] = str(v.get("phone") or "").strip()
    _stamp(o, "departments", r["user"])
    _save(o, r["user"], "departments")
    return {"ok": True, "step": "departments", **view()}


def _create_one(mgr, r, a: dict, url: str = accounts.LOGIN_URL) -> dict:
    if not isinstance(a.get("departments") or {}, dict):
        raise accounts.AccountError(400, "departments must map a department to doctor, head or resident.")
    if not isinstance(a.get("admin_of") or [], list):
        raise accounts.AccountError(400, "admin_of must be a list of departments.")
    email = str(a.get("email") or a.get("username") or "").strip().lower()
    out = accounts.create_account(mgr, r["user"], email, None, display_name=str(a.get("display_name") or ""), coordinator=bool(a.get("coordinator", False)),
                                  admin_of=a.get("admin_of") or [], departments=a.get("departments") or {}, root_admin=bool(a.get("root_admin", False)),
                                  auditor=bool(a.get("auditor", False)), outside_expert=bool(a.get("outside_expert", False)), end_date=str(a.get("end_date") or ""),
                                  email=str(a.get("email") or ""), hospital=org.hospital().get("name") or "", url=url, **_limits())
    return {"email": out.get("email") or email, "username": out["username"], "created": out["created"], "mailto": out.get("mailto") or "",
            "must_change_password": bool(out.get("must_change_password")), "roles": {k: out.get(k) for k in ("departments", "admin_of", "coordinator", "root_admin", "auditor", "outside_expert", "end_date")}}


@router.post("/setup/people")
async def setup_people(request: Request):
    """{accounts[{email, display_name, departments{dept: doctor|head|resident}, coordinator?, admin_of[], root_admin?, auditor?, end_date?}]}
    -> {created[{email, username, mailto}], errors[{email, message}]}. The first password is inside the mailto only."""
    r = roles(request); need(r, "manage_org"); b = await body(request)
    mgr = auth_manager(request)
    rows = b.get("accounts")
    if not isinstance(rows, list) or not rows:
        fail(400, "Send accounts: a list of people to invite.", "bad_value")
    created, errors = [], []
    for a in rows[:200]:
        if not isinstance(a, dict):
            errors.append({"email": "", "message": "Each account must be an object."})
            continue
        try:
            created.append(_create_one(mgr, r, a, login_url(request)))
        except accounts.AccountError as e:
            errors.append({"email": str(a.get("email") or a.get("username") or ""), "message": str(e)})
        except ValueError as e:
            errors.append({"email": str(a.get("email") or a.get("username") or ""), "message": str(e)})
    o = copy.deepcopy(org.load())
    _stamp(o, "people", r["user"])
    _save(o, r["user"], "people")
    return {"ok": not errors, "step": "people", "created": created, "errors": errors, **view(mgr)}


async def run_his_test(by: str = "") -> dict:
    """Ping the configured HIS, read its hospital record and count its patients and reports with cheap searches; recorded in org.json."""
    t0 = time.monotonic()
    out = {"ok": False, "hospital_name": "", "patients": None, "reports": None, "latency_ms": 0, "error": "", "fhir_version": "", "token_ok": None}
    c = his_client.client()
    if c is None:
        out["error"] = "No hospital information system is configured or it is disabled."
    else:
        try:
            ping = await c.ping()
            out.update({"ok": bool(ping.get("ok")), "error": ping.get("error") or "", "fhir_version": ping.get("fhir_version") or "", "token_ok": ping.get("token_ok")})
            if out["ok"]:
                try:
                    out["hospital_name"] = (await c.hospital()).get("name") or ping.get("name") or ""
                except Exception as e:
                    out["hospital_name"] = ping.get("name") or ""
                    out["error"] = f"hospital record: {type(e).__name__}: {str(e)[:120]}"
                out["patients"], out["reports"] = await _counts(c)
                counts = ping.get("counts") if isinstance(ping.get("counts"), dict) else None
                if counts and out["patients"] is None and out["reports"] is None:  # a folder method (his_adapters) counts what it read
                    out["patients"], out["reports"] = counts.get("patients"), counts.get("reports")
        except Exception as e:
            out["error"] = f"{type(e).__name__}: {str(e)[:160]}"
    out["latency_ms"] = round((time.monotonic() - t0) * 1000, 1)
    try:
        o = copy.deepcopy(org.load())
        o["hospital"]["his_test"] = {"at": org.now_iso(), "ok": out["ok"], "error": out["error"], "hospital_name": out["hospital_name"], "patients": out["patients"], "by": by}
        if out["ok"]:
            _stamp(o, "his", by)
        org.save(o, by)
        if out["ok"]:
            org.audit("setup_step", by, step="his")
    except ValueError:
        pass
    org.audit("his_test", by, ok=out["ok"], error=out["error"], latency_ms=out["latency_ms"])
    return out


async def _counts(c) -> tuple:
    """Patient and DiagnosticReport totals through a count-only search (FHIR _summary=count); None when the HIS does not say."""
    get_json, mk = getattr(c, "_get_json", None), getattr(c, "_client", None)
    if not callable(get_json) or not callable(mk):
        return None, None
    totals = []
    try:
        async with mk() as hc:
            for res in ("Patient", "DiagnosticReport"):
                try:
                    b = await get_json(hc, res, [("_summary", "count")])
                    t = b.get("total") if isinstance(b, dict) else None
                    if t is None:
                        b = await get_json(hc, res, [("_count", "1")])
                        t = b.get("total") if isinstance(b, dict) else None
                    totals.append(int(t) if isinstance(t, int) else None)
                except Exception:
                    totals.append(None)
    except Exception:
        return None, None
    return tuple(totals) if len(totals) == 2 else (None, None)


@router.post("/his/test")
async def his_test(request: Request):
    r = roles(request); need(r, "manage_org")
    return await run_his_test(r["user"])


HIS_FIELDS = ("label", "url", "token", "preset", "base_path", "identifier_systems", "auth", "username", "password", "api_key_header", "api_key",
              "token_url", "client_id", "client_secret", "scope", "folder", "pacs_url")


@router.get("/his/kinds")
async def his_kinds(request: Request):
    """"Choose your hospital system": the connection methods (kind, label, description, fields, what each cannot do), the hospital systems
    to pick from (presets) and what is saved now. For those who may save the connection; never a secret (only "set" / "not set")."""
    r = roles(request); need(r, "manage_org")
    from tumour_board.his_adapters import _common, registry
    cfg = his_client.settings()
    return {"kinds": registry.describe(), "presets": registry.presets(),
            "current": {"kind": cfg.get("kind"), "preset": (cfg.get("adapter") or {}).get("preset") or "", "enabled": bool(cfg.get("enabled")),
                        "settings": his_client.public(cfg)},
            "folder_roots": [str(p) for p in _common.folder_roots()],
            "remote_allowed": bool(r.get("admin")) or bool(his_client.allowed_hosts())}


def _his_payload(b: dict) -> tuple:
    """The settings a POST /setup/his or POST /his/try body names, as save_settings takes them, and whether they are a his_adapters kind
    (whose messages are capitalised). {kind} or {preset} (GET /his/kinds) picks the connection method; the old {url, token} body is a
    "fhir" connection exactly as before. A bad choice fails 400 here, before anything is tested or saved."""
    if str(b.get("kind") or "").strip() or str(b.get("preset") or "").strip():
        from tumour_board.his_adapters import registry
        pre = registry.preset(str(b.get("preset") or "").strip()) if str(b.get("preset") or "").strip() else None
        if str(b.get("preset") or "").strip() and not pre:
            fail(400, "That hospital system is not in the list.", "bad_his")
        kind = str(b.get("kind") or "").strip().lower() or pre["kind"]
        if registry.is_adapter_kind(kind):
            return {k: b[k] for k in HIS_FIELDS if k in b} | {"kind": kind, "enabled": True}, True
        if kind != "fhir":
            fail(400, "Choose a hospital system from the list.", "bad_his")
        if pre and not str(b.get("url") or "").strip():
            b = {**b, "url": (pre.get("defaults") or {}).get("url") or ""}
    url = str(b.get("url") or "").strip()
    if not url:
        fail(400, "Give the hospital system's URL.", "url_required")
    payload = {"kind": "fhir", "url": url, "enabled": True}
    if str(b.get("token") or "").strip():
        payload["token"] = str(b["token"]).strip()
    if str(b.get("label") or "").strip():
        payload["label"] = str(b["label"]).strip()
    return payload, False


def _his_error(e: ValueError, adapter: bool) -> str:
    return str(e)[:1].upper() + str(e)[1:] if adapter else str(e)


@router.post("/setup/his")
async def setup_his(request: Request):
    """{url, token?}: saves the connection (the token never comes back) and runs the test; the step is done only when the test passes.
    With {"kind"} or {"preset"} (GET /his/kinds) the fields of that connection method are saved instead: a plain FHIR server, an HL7 v2
    folder, a report folder or ABDM bundles. Secrets go to owner-only files and never come back.
    Optional `tested_fingerprint` (from POST /his/try, "Choose your hospital system"): the save is refused 409 unless these are exactly
    the values that were tested; a body without it behaves as before."""
    r = roles(request); need(r, "manage_org"); b = await body(request)
    payload, adapter = _his_payload(b)
    tested = str(b.get("tested_fingerprint") or "").strip()
    if tested:
        try:
            clean = his_client.trial_settings(payload, allow_remote=bool(r.get("admin")))
        except ValueError as e:
            fail(400, _his_error(e, adapter), "bad_his")
        if not hmac.compare_digest(tested.encode(), his_client.fingerprint(clean).encode()):
            fail(409, "Test these settings again before using them.", "untested")
    try:
        his_client.save_settings(payload, by=r["user"], allow_remote=bool(r.get("admin")))
    except ValueError as e:
        fail(400, _his_error(e, adapter), "bad_his")
    test = await run_his_test(r["user"])
    return {"ok": test["ok"], "step": "his", "test": test, **view()}


# ---- "Choose your hospital system": try settings without saving them (docs/new-case/DESIGN.md N7) ---------------------------------
TRY_SECONDS = 15          # the whole try (sign-in, counts, one patient) so the screen never hangs
TRY_HTTP_SECONDS = 10     # one request to the hospital system
_TRY_TRANSPORT = None     # tests put an httpx.MockTransport here
TRY_LIMIT = RateLimit(20, 10 * 60)  # POST /his/try per login (review of 17 Nov 2026)


def _plain(msg: str) -> str:
    msg = " ".join(str(msg or "").split())[:300]
    return msg[:1].upper() + msg[1:] if msg else ""


def _what_to_check(error: str, kind: str) -> str:
    """One line on what to check, from the plain error (never a secret: the messages of his_client and his_adapters carry none)."""
    from tumour_board.his_adapters import registry
    e = error.lower()
    if "cannot reach" in e:
        return "Check the server address and port, and that the hospital system is running and can be reached from this server."
    if "refused the token" in e or "token endpoint" in e or "refused the client" in e:
        return "Check the sign-in details: the token, user name and password, API key or client id and secret the hospital gave."
    if "did not answer in time" in e or "longer than" in e:
        return "The hospital system is slow or busy. Try again; if it stays slow, ask the hospital IT team to check it."
    if "folder" in e:
        return "Check that the folder exists on this server, inside the allowed folder root, and that Vaidyx-TB may read it."
    if "not a capabilitystatement" in e or "not json" in e or "not a fhir" in e or "http 404" in e:
        return "Check the server address and the FHIR base path: the address must lead to the FHIR R4 API."
    if kind in registry.FOLDER_KINDS:
        return "Check the folder and the files in it."
    return "Check the address and the sign-in details, then test again."


async def _sample(c, identifier: str, step) -> dict:
    """One patient by an exact identifier (UHID, IP / OP No., ABHA): only whether it is found, how many visits and reports, and the
    date of the newest report. No name, initials, age, sex, report title or identifier of the system's own: those who test a hospital
    system are the Vaidyx admin and the hospital admin, and neither sees patient data (admin consoles D5; owner, 17 Nov 2026: the
    hospital admin is IT, the MDT Coordinator handles patient data). The counts are enough to show the connection reads real records.
    Answers {found: false} when nothing matches; a problem with this one patient never fails the whole try."""
    out = {"found": False, "identifier": identifier}
    try:
        p = await step(c.find_patient(identifier))
        if not p:
            return out
        encs = await step(c.encounters(p.get("id") or ""))
        reps = await step(c.reports(p.get("id") or ""))
    except asyncio.TimeoutError:
        return out | {"error": f"The hospital system took longer than {TRY_SECONDS} seconds to answer for this patient."}
    except his_client.HISError as e:
        return out | {"error": _plain(str(e))}
    except Exception as e:  # an adapter bug must not hide the connection result
        return out | {"error": f"The patient could not be read ({type(e).__name__})."}
    current = [x for x in reps if isinstance(x, dict) and x.get("current", True)] or [x for x in reps if isinstance(x, dict)]
    when = lambda x: str(x.get("issued") or x.get("effective") or "")
    newest = max(current, key=when, default=None)
    return {"found": True, "identifier": identifier, "visits": len(encs or []), "reports": len({x.get("id") for x in reps if isinstance(x, dict)}),
            "newest_report_date": when(newest)[:10] if newest else ""}


async def run_his_try(clean: dict, identifier: str = "") -> dict:
    """Test settings from his_client.trial_settings without saving anything: sign in, count patients and reports when the system can,
    and read one patient when an identifier is given. Never raises; the error is in plain words with what to check."""
    t0 = time.monotonic()
    out = {"ok": False, "checked_at": org.now_iso(), "kind": clean.get("kind"), "label": clean.get("label") or "",
           "preset": (clean.get("adapter") or {}).get("preset") or "", "ping": {}, "counts": None, "error": "", "hint": "",
           "fingerprint": his_client.fingerprint(clean), "latency_ms": 0}
    deadline = time.monotonic() + TRY_SECONDS

    async def step(coro):
        left = deadline - time.monotonic()
        if left <= 0:
            coro.close()
            raise asyncio.TimeoutError
        return await asyncio.wait_for(coro, left)

    try:
        c = his_client.trial_client(clean, transport=_TRY_TRANSPORT, timeout=TRY_HTTP_SECONDS)
        if c is None:
            out["error"] = "This kind of connection cannot be tested here. Choose a hospital system from the list."
        else:
            ping = await step(c.ping())
            out["ping"] = {k: ping.get(k) for k in ("ok", "name", "fhir_version", "token_ok")} | {"latency_ms": round((time.monotonic() - t0) * 1000, 1)}
            if not ping.get("ok"):
                out["error"] = _plain(ping.get("error") or "The hospital system did not answer.")
            else:
                out["ok"] = True
                try:
                    pats, reps = await step(_counts(c))
                except asyncio.TimeoutError:
                    pats, reps = None, None
                counts = ping.get("counts") if isinstance(ping.get("counts"), dict) else None
                if counts and pats is None and reps is None:  # a folder method counts what it read
                    pats, reps = counts.get("patients"), counts.get("reports")
                if pats is not None or reps is not None:
                    out["counts"] = {"patients": pats, "reports": reps} | ({"skipped": counts.get("skipped")} if counts and counts.get("skipped") else {})
                if identifier:
                    out["sample"] = await _sample(c, identifier, step)
    except asyncio.TimeoutError:
        out["ok"], out["error"] = False, f"The hospital system took longer than {TRY_SECONDS} seconds to answer."
    except his_client.HISError as e:
        out["ok"], out["error"] = False, _plain(str(e))
    except Exception as e:
        out["ok"], out["error"] = False, f"The test could not run ({type(e).__name__})."
    if out["error"] and not out["ok"]:
        out["hint"] = _what_to_check(out["error"], str(clean.get("kind") or ""))
    if not out["ok"]:
        out["fingerprint"] = ""  # only a passing test can be used to save
    out["latency_ms"] = round((time.monotonic() - t0) * 1000, 1)
    return out


@router.post("/his/try")
async def his_try(request: Request):
    """{preset? | kind?, fields..., identifier?}: the same body as POST /setup/his, tested WITHOUT saving (nothing is written but the
    audit line). -> {ok, checked_at, kind, label, ping{}, counts{patients, reports}?, sample{found, identifier (as typed), visits,
    reports, newest_report_date}? (with an identifier), error?, hint?, fingerprint}. The fingerprint goes back in POST /setup/his as
    tested_fingerprint so the save is exactly what passed. Same gate and rules as saving: manage_org, the host rule (another host only
    for a Vaidyx admin), the folder roots, a secret left empty keeps the saved one only for the same kind and server. The sample shows
    no patient data to anyone (see _sample). At most TRY_LIMIT tries per login: each try signs in to the hospital system and may read
    a patient, so a loop must not hammer it or probe numbers (429)."""
    r = roles(request); need(r, "manage_org")
    TRY_LIMIT.check(r["user"], "Too many tests in a short time. Wait a few minutes and test again.")
    b = await body(request)
    identifier = " ".join(str(b.get("identifier") or "").split())[:80]
    payload, adapter = _his_payload(b)
    try:
        clean = his_client.trial_settings(payload, allow_remote=bool(r.get("admin")))
    except ValueError as e:
        org.audit("his_try", r["user"], his_kind=payload.get("kind"), preset=str(b.get("preset") or "")[:40], ok=False, refused=_his_error(e, adapter)[:200])
        fail(400, _his_error(e, adapter), "bad_his")
    out = await run_his_try(clean, identifier)
    sample = out.get("sample") or {}
    org.audit("his_try", r["user"], his_kind=clean["kind"], preset=out["preset"], url=clean.get("url") or "", ok=out["ok"], error=out["error"][:200],
              identifier=identifier[:60] or None, found=bool(sample.get("found")) if identifier else None)
    return out


@router.post("/setup/board")
async def setup_board(request: Request):
    """{coordinators[], heads[], meeting_defaults{weekday?, time?, room?, minutes_per_case}}: the coordinator flags are replaced by the list."""
    r = roles(request); need(r, "manage_org"); b = await body(request)
    o = copy.deepcopy(org.load())
    if "heads" in b:
        if not isinstance(b["heads"], list) or not b["heads"]:
            fail(400, "Name at least one board head (a department).", "bad_value")
        heads = []
        for x in b["heads"]:
            did = org.department_id(x) if isinstance(x, str) else None
            if not did:
                fail(400, f"Unknown department '{x}'.", "bad_value")
            if did not in heads:
                heads.append(did)
        o["hospital"]["board_heads"] = heads
    if "coordinators" in b:
        if not isinstance(b["coordinators"], list):
            fail(400, "coordinators must be a list of logins.", "bad_value")
        want = {accounts.clean_username(x) if isinstance(x, str) else "" for x in b["coordinators"]} - {""}
        unknown = sorted(u for u in want if u not in o["users"])
        if unknown:
            fail(400, f"Not placed in the Tumour Board yet: {', '.join(unknown)}. Create the login first (People).", "bad_value")
        mixed = sorted(u for u in want if u in (o.get("admins") or []))
        if mixed:  # security review #5
            fail(409, f"{accounts.SEPARATE_LOGINS}: {', '.join(mixed)} is a hospital admin. Choose another login as MDT Coordinator.", "separate_logins")
        for u, v in o["users"].items():
            if isinstance(v, dict):
                v["coordinator"] = u in want
    if "meeting_defaults" in b:
        if not isinstance(b["meeting_defaults"], dict):
            fail(400, "meeting_defaults must be an object.", "bad_value")
        o["hospital"]["meeting_defaults"] = {**(o["hospital"].get("meeting_defaults") or {}), **b["meeting_defaults"]}
    _stamp(o, "board", r["user"])
    _save(o, r["user"], "board")
    return {"ok": True, "step": "board", **view()}


# ---- accounts ----------------------------------------------------------------------------------------------------------------------

@router.get("/accounts")
async def list_accounts(request: Request):
    r = roles(request); need(r, "manage_org")
    mgr = getattr(request.app.state, "auth_manager", None)
    o = org.load()
    rows = []
    for u, v in sorted(o["users"].items()):
        rl = org.roles(u)
        rows.append({"username": u, **v, "root_admin": u in o["admins"], "account": accounts.account_exists(mgr, u) if mgr else None,
                     "vaidyx_admin": accounts.is_vaidyx_admin(mgr, u), "must_change_password": accounts.must_change(mgr, u) if mgr else False,
                     "expired": bool(rl.get("expired")), "is_email": accounts.is_email(u)})
    return {"accounts": rows, "admins": o["admins"], "reset_note": accounts.RESET_NOTE}


@router.post("/accounts")
async def create_account(request: Request):
    """{email, display_name, departments{dept: doctor|head|resident}, coordinator?, admin_of[], root_admin?, auditor?, outside_expert?, end_date?}
    -> {username, mailto}: a plain login with a generated first password (must change), the password only inside the mailto."""
    r = roles(request); need(r, "manage_org"); b = await body(request)
    mgr = auth_manager(request)
    return {"ok": True, **_call(_create_one, mgr, r, b, login_url(request))}


@router.post("/accounts/{username}/reset-password")
async def reset_password(username: str, request: Request):
    """A new first password in a mailto (must change at the next sign-in): a department admin for the people of their departments, the
    root admin for anyone."""
    r = roles(request)
    if not (org.can(r, "manage_org") or r.get("admin_of")):
        fail(403, "Only a department admin or the hospital admin resets a password.", "forbidden")
    mgr = auth_manager(request)
    b = await body(request) if (await request.body()) else {}
    out = _call(accounts.reset_password, mgr, r["user"], r, username, email=str(b.get("email") or ""), hospital=org.hospital().get("name") or "", url=login_url(request))
    return {"ok": True, **out}


@router.put("/accounts/{username}")
async def update_account(username: str, request: Request):
    """{disabled?, end_date?, coordinator?, auditor?, outside_expert?, root_admin?, admin_of?, departments?, display_name?} (root admin)."""
    r = roles(request); need(r, "manage_org"); b = await body(request)
    mgr = getattr(request.app.state, "auth_manager", None)
    return {"ok": True, **_call(accounts.update_account, mgr, r["user"], r, username, b)}


# ---- a department's people (department admin): residents with end dates --------------------------------------------------------------

def _dept(dept: str) -> str:
    did = org.department_id(dept)
    if not did:
        fail(404, "Unknown department", "not_found")
    return did


@router.get("/departments/{dept}/people")
async def department_people(dept: str, request: Request):
    r = roles(request); did = _dept(dept); need(r, "manage_department", did)
    mgr = getattr(request.app.state, "auth_manager", None)
    return {"department": org.department(did), "people": accounts.department_doctors(did, mgr), "can_reset": True, "roles": list(org.PLACEMENTS)}


@router.post("/departments/{dept}/people")
async def add_person(dept: str, request: Request):
    """{email | username, display_name?, role: doctor|head|resident, end_date?} -> {username, mailto, created}: a new login gets a generated
    first password inside the mailto; an existing plain login is placed here."""
    r = roles(request); did = _dept(dept); need(r, "manage_department", did); b = await body(request)
    mgr = auth_manager(request)
    login = str(b.get("email") or b.get("username") or "").strip().lower()
    role = str(b.get("role") or "member")
    _call(accounts.check_placement, did, role)
    end_date = str(b.get("end_date") or "")
    generated = ""
    u = _call(accounts.clean_username, login)
    if not accounts.account_exists(mgr, u):
        generated = accounts.generate_password()
    made = _call(accounts.ensure_account, mgr, u, generated or None, r["user"], **_limits())
    flagged = accounts._first_password(mgr, u, generated, r["user"]) if made["created"] and generated else False
    placed = _call(accounts.place_doctor, r["user"], did, u, role=role, display_name=b.get("display_name"), caller=r, created=made["created"], end_date=end_date or None)
    to = str(b.get("email") or "").strip().lower() or (u if accounts.is_email(u) else "")
    return {"ok": True, "created": made["created"], "mailto": accounts.mailto_for(to, u, generated, url=login_url(request), hospital=org.hospital().get("name") or "") if made["created"] and generated else "",
            "must_change_password": flagged, **placed}


@router.put("/departments/{dept}/people/{username}")
async def update_person(dept: str, username: str, request: Request):
    """{role?, disabled?, end_date?}"""
    r = roles(request); did = _dept(dept); need(r, "manage_department", did); b = await body(request)
    out = _call(accounts.update_doctor, r["user"], r, did, username, role=b.get("role"), disabled=b.get("disabled"), mgr=getattr(request.app.state, "auth_manager", None),
                end_date=b.get("end_date"))
    return {"ok": True, **out}


@router.delete("/departments/{dept}/people/{username}")
async def remove_person(dept: str, username: str, request: Request):
    r = roles(request); did = _dept(dept); need(r, "manage_department", did)
    return {"ok": True, **_call(accounts.remove_doctor, r["user"], r, did, username)}
