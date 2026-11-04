"""Create (or refresh) the doctors' instance of Vaidyx-TB on the H200 (deployment Plan B, see deploy/README.md).

Separate from the internal app (:7000) and the public demo (:7100):

  <root>/vaidyx_data     its own Vaidyx accounts (VAIDYX_DATA_DIR); no Vaidyx admin is created
  <root>/tumour_board    its own Tumour Board data: copies of synthetic Case Files only (allow-list below)
  <root>/guidelines      hard links to the guideline library, without licensed material (AJCC)

Accounts: the Tumour Board role logins of the internal demo (tb-root, tb-mdt, department admins and doctors) as plain
Vaidyx users with new random passwords, written to ~/vaidyx/.tb_deploy_logins (mode 600, tab separated:
user, password, display name, roles). This script never prints a password.

Run with the app venv:
  /data/vaidyx/venv/app/bin/python deploy/h200/setup_instance.py --app /data/vaidyx/tb_deploy/app [--reset-cases]
"""
import argparse
import json
import os
import re
import secrets
import shutil
import string
import sys
from pathlib import Path

SRC_REPO = Path("/home/bharath.tangella/vaidyx/Vaidyx")          # the internal instance (read only)
SRC_TB = SRC_REPO / "data" / "tumour_board"
SRC_GUIDE = Path("/data/vaidyx/tb_resources/guidelines")
ROOT = Path(os.getenv("VX_DEPLOY_ROOT", "/data/vaidyx/tb_deploy"))
VDATA, TB, GUIDE = ROOT / "vaidyx_data", ROOT / "tumour_board", ROOT / "guidelines"
# The public site's own copy of the synthetic demo hospital (HIMS): its own data, access key, passwords and port, so the internal
# development HIMS (:7130) is never reached from outside.
SRC_HIMS = SRC_REPO / "data" / "his_mock"
HIMS = ROOT / "his_mock"
HIMS_PORT = 7330
HIMS_SKIP = ("sessions.json", "write_token", "desk_audit.jsonl", "his_audit.jsonl", "ui_shots")
LOGINS = Path.home() / "vaidyx" / ".tb_deploy_logins"

# Synthetic Case Files only. The real case (TB-2026-bharath) and the test clutter never come here.
CASE_ALLOW = re.compile(r"^(TB-00[1-8]|TB-DEMO-[A-Z0-9]+|HIST-\d{2})$")
NEVER = {"TB-2026-bharath"}
CONFIG_FILES = ("models.json", "model_cards.json", "his.json", "audio_token.json", "pubmed.json", "hospital_logo.png")
CONFIG_DIRS = ("skills",)
NOT_SHARED = {"ajcc"}  # licensed material stays on the internal instance

ROLE_USERS = {  # username: (display name, roles as in org.json)
    "tb-root": ("Root admin (demo)", {"root_admin": True}),
    "tb-mdt": ("MDT Coordinator (demo)", {"coordinator": True}),
    "tb-rad-admin": ("Radiology admin (demo)", {"admin_of": ["radiology"]}),
    "tb-rad-doc": ("Dr Radiology (demo)", {"departments": {"radiology": "doctor"}}),
    "tb-path-admin": ("Pathology admin (demo)", {"admin_of": ["pathology"]}),
    "tb-path-head": ("Dr Pathology head (demo)", {"departments": {"pathology": "head"}}),
    "tb-breast-admin": ("Breast Surgery admin (demo)", {"admin_of": ["breast_surgery"]}),
    "tb-breast-doc": ("Dr Breast Surgery (demo)", {"departments": {"breast_surgery": "doctor"}}),
    "tb-medonc-doc": ("Dr Medical Oncology (demo)", {"departments": {"medical_oncology": "doctor"}}),
    "tb-gynonc-doc": ("Dr Gynaecologic Oncology (demo)", {"departments": {"gynaecologic_oncology": "doctor"}}),
    "tb-micro-doc": ("Dr Microbiology (demo)", {"departments": {"microbiology": "doctor"}}),
    "tb-pulmo-doc": ("Dr Pulmonology (demo)", {"departments": {"pulmonology": "doctor"}}),
    "tb-crs-doc": ("Dr Colorectal Surgery (demo)", {"departments": {"colorectal_surgery": "doctor"}}),
    # A guest reviewer with anonymized real files (5 Nov 2026): private Case Files only, two-factor sign-in first. The department
    # only sets the owning department of their Case Files; change it to the reviewer's specialty in org.json if wanted.
    "tb-guest-1": ("Guest reviewer 1", {"departments": {"medical_oncology": "doctor"}, "real_data": True}),
}
NO_TOOLS = {"can_use_bash": False, "can_use_browser": False, "can_use_research": False, "can_generate_images": False,
            "can_use_agent": False, "can_manage_memory": False}


def password(n: int = 18) -> str:
    a = string.ascii_letters + string.digits
    return "".join(secrets.choice(a) for _ in range(n))


def copy_cases(reset: bool) -> list[str]:
    (TB / "cases").mkdir(parents=True, exist_ok=True)
    picked = sorted(p.name for p in (SRC_TB / "cases").iterdir() if p.is_dir() and CASE_ALLOW.match(p.name) and p.name not in NEVER)
    for cid in picked:
        dst = TB / "cases" / cid
        if dst.exists() and reset:
            shutil.rmtree(dst)
        if not dst.exists():
            shutil.copytree(SRC_TB / "cases" / cid, dst)
    here = sorted(p.name for p in (TB / "cases").iterdir())
    bad = [c for c in here if c in NEVER]
    if bad:
        sys.exit(f"refusing to continue: a protected Case File is in the doctors' data root: {bad}")
    return here


def copy_config():
    for f in CONFIG_FILES:
        if (SRC_TB / f).exists():
            shutil.copy2(SRC_TB / f, TB / f)
            if f.endswith(".json") and f != "models.json":
                os.chmod(TB / f, 0o600)
    for d in CONFIG_DIRS:
        if (SRC_TB / d).is_dir():
            shutil.copytree(SRC_TB / d, TB / d, dirs_exist_ok=True)
    if not (TB / "embed_cache").exists():
        shutil.copytree(SRC_TB / "embed_cache", TB / "embed_cache", ignore=shutil.ignore_patterns("pre-v1-*", "v1-*"))


def write_org():
    org = json.loads((SRC_TB / "org.json").read_text())
    users = {}
    for u, (_name, roles) in ROLE_USERS.items():
        src = (org.get("users") or {}).get(u, {})
        users[u] = {**src, **{k: v for k, v in roles.items() if k != "root_admin"}, "disabled": False}
        users[u].setdefault("display_name", _name)
    org["users"] = users
    org["admins"] = [u for u, (_n, r) in ROLE_USERS.items() if r.get("root_admin")]
    (TB / "org.json").write_text(json.dumps(org, indent=1))
    os.chmod(TB / "org.json", 0o600)
    prof_src = SRC_TB / "profiles.json"
    if prof_src.exists():
        prof = json.loads(prof_src.read_text())
        (TB / "profiles.json").write_text(json.dumps({u: v for u, v in prof.items() if u in ROLE_USERS}, indent=1))
        os.chmod(TB / "profiles.json", 0o600)


def link_guidelines():
    GUIDE.mkdir(parents=True, exist_ok=True)
    for p in GUIDE.iterdir():
        shutil.rmtree(p) if p.is_dir() and not p.is_symlink() else p.unlink()
    for p in SRC_GUIDE.iterdir():
        if p.is_dir() and p.name not in NOT_SHARED and not p.name.startswith("_"):
            shutil.copytree(p, GUIDE / p.name, copy_function=os.link)


def make_accounts(app: Path) -> int:
    os.environ["VAIDYX_DATA_DIR"] = str(VDATA)
    sys.path.insert(0, str(app))
    os.chdir(app)
    from core.auth import AuthManager  # noqa: E402  (the pinned copy's own code)
    from src.constants import AUTH_FILE  # noqa: E402
    assert Path(AUTH_FILE).parent == VDATA, AUTH_FILE
    am = AuthManager(AUTH_FILE)
    existing = {}
    if LOGINS.exists():
        for line in LOGINS.read_text().splitlines():
            parts = line.split("\t")
            if len(parts) >= 2 and not line.startswith("#"):
                existing[parts[0]] = parts[1]
    rows, made = [], 0
    for u, (name, roles) in ROLE_USERS.items():
        if u not in am.users:
            p = password()
            am.create_user(u, p, is_admin=False)
            existing[u] = p
            made += 1
        privs = dict(am.get_privileges(u))
        privs.update(NO_TOOLS)
        am.set_privileges(u, privs)
        if am.is_admin(u):
            sys.exit(f"refusing to continue: {u} is a Vaidyx admin")
        rows.append("\t".join([u, existing.get(u, "(unchanged, see earlier file)"), name, json.dumps(roles)]))
    am.signup_enabled = False
    LOGINS.parent.mkdir(parents=True, exist_ok=True)
    tmp = LOGINS.with_suffix(".tmp")
    tmp.write_text("# Vaidyx-TB doctors' instance logins (deployment). user<TAB>password<TAB>name<TAB>roles\n" + "\n".join(rows) + "\n")
    os.chmod(tmp, 0o600)
    tmp.replace(LOGINS)
    return made


def setup_hims(app: Path) -> str:
    """Copy the synthetic HIMS once (a new access key, new passwords for its 9 staff logins, no sessions or audit from the internal
    one) and point the instance's his.json at it. Returns what was done."""
    import subprocess
    done = "kept"
    if not HIMS.exists():
        shutil.copytree(SRC_HIMS, HIMS, ignore=shutil.ignore_patterns(*HIMS_SKIP))
        (HIMS / "token").write_text(secrets.token_urlsafe(32) + "\n")
        os.chmod(HIMS / "token", 0o600)
        subprocess.run([sys.executable, "-m", "his_mock.auth", "--reset"], cwd=app, check=True, capture_output=True,
                       env={**os.environ, "TB_HIS_MOCK_DATA": str(HIMS)})
        done = "copied"
    os.chmod(HIMS, 0o700)
    cfg = json.loads((TB / "his.json").read_text()) if (TB / "his.json").exists() else {"kind": "fhir", "enabled": True}
    cfg.update({"url": f"http://127.0.0.1:{HIMS_PORT}", "token": (HIMS / "token").read_text().strip(), "token_file": str(HIMS / "token")})
    (TB / "his.json").write_text(json.dumps(cfg, indent=1))
    os.chmod(TB / "his.json", 0o600)
    return done


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--app", required=True, type=Path, help="the pinned checkout the instance runs from")
    ap.add_argument("--reset-cases", action="store_true")
    a = ap.parse_args()
    for d in (VDATA, TB, GUIDE, ROOT / "logs"):
        d.mkdir(parents=True, exist_ok=True)
    os.chmod(ROOT, 0o700)
    cases = copy_cases(a.reset_cases)
    copy_config()
    hims = setup_hims(a.app.resolve())
    write_org()
    link_guidelines()
    made = make_accounts(a.app.resolve())
    print("doctors' instance ready:", ROOT)
    print("Case Files:", len(cases), "(", ", ".join(cases), ")")
    print("guideline folders:", sorted(p.name for p in GUIDE.iterdir()))
    print(f"demo hospital (HIMS): {hims}, {HIMS} on 127.0.0.1:{HIMS_PORT}; its staff logins in {HIMS / 'logins.tsv'} (mode 600)")
    print(f"accounts: {len(ROLE_USERS)} role logins ({made} new), plain users, no Vaidyx admin; passwords in {LOGINS} (mode 600)")


if __name__ == "__main__":
    main()
