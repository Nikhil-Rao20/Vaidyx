"""Agent skills: the specialty agents' role definitions as editable SKILL.md files (Agent Skills layout).

A skill says who an agent is and what it looks for: label, department, document types read first, the focus list and extra
guidance. It never says what an agent may do: the tools, the hard rules and the output checks stay in agents.py and are applied
after the skill text on every call. Roles are an allow-list in code (agents.ROLES): a skill cannot add a role.

Two layers: the repo defaults in tumour_board/skills/<role>/SKILL.md and a hospital edit in <data root>/skills/<role>/SKILL.md
(written from the UI by an admin, audited in org_audit.jsonl, previous versions kept as .bak). The hospital file wins when it
validates; a broken one is ignored with an audit entry and the default is used.
"""
import hashlib, json, re, shutil
from pathlib import Path

import yaml

from . import config, org, protocol

REPO_DIR = Path(__file__).resolve().parent / "skills"
AGENT_TOOLS = ("list_documents", "read_document", "search", "find_values", "get_facts", "get_gaps", "search_guidelines")  # fixed in agents.py
SKILL_FILE = "SKILL.md"
MAX_DESCRIPTION, MAX_BODY, MAX_NAME = 1024, 20000, 64
_FRONT = re.compile(r"\A---\s*\n(.*?)\n---\s*\n?(.*)\Z", re.S)
_HEADING = re.compile(r"^#\s+(.+?)\s*$", re.M)
_cache = {"key": None, "data": None}


def hospital_dir() -> Path:
    return Path(config.DATA_ROOT) / "skills"


def _roles():
    from .agents import ROLES  # lazy: agents imports skills
    return ROLES


def parse(text: str) -> dict:
    """The skill a SKILL.md text describes, or ValueError with a plain message. Validation only: no files are touched."""
    if not isinstance(text, str) or not text.strip():
        raise ValueError("empty skill file")
    m = _FRONT.match(text)
    if not m:
        raise ValueError("the file must start with a YAML frontmatter block between two '---' lines")
    try:
        fm = yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError as e:
        raise ValueError(f"frontmatter is not valid YAML: {str(e).splitlines()[0]}")
    if not isinstance(fm, dict):
        raise ValueError("frontmatter must be a mapping of fields")
    body = m.group(2)
    name = str(fm.get("name") or "").strip()
    if not name or len(name) > MAX_NAME or not re.fullmatch(r"[a-z][a-z0-9_-]*", name) or "--" in name or name.endswith("-"):
        raise ValueError("name: lower-case letters, digits, hyphens or underscores, up to 64 characters")
    name = name.replace("-", "_")  # the open standard writes hyphens; role ids use underscores (medical-oncology = medical_oncology)
    if name not in _roles():
        raise ValueError(f"name '{name}' is not a known agent role ({', '.join(_roles())}); a skill cannot add a role")
    tools = fm.get("allowed-tools", fm.get("allowed_tools"))
    if tools is not None:  # may only restrict the agent's fixed tool list, never add to it
        tools = tools.split() if isinstance(tools, str) else tools
        if not isinstance(tools, list) or not all(isinstance(t, str) for t in tools):
            raise ValueError("allowed-tools: space-separated tool names")
        unknown = [t for t in tools if t not in AGENT_TOOLS]
        if unknown:
            raise ValueError(f"allowed-tools names tools the agents do not have: {', '.join(unknown)} (available: {' '.join(AGENT_TOOLS)})")
        if not tools:
            raise ValueError("allowed-tools must keep at least one tool")
    desc = str(fm.get("description") or "").strip()
    if not desc:
        raise ValueError("description is required")
    if len(desc) > MAX_DESCRIPTION:
        raise ValueError(f"description is longer than {MAX_DESCRIPTION} characters")
    label = str(fm.get("label") or "").strip()
    if not label or len(label) > 80:
        raise ValueError("label is required (up to 80 characters)")
    dept = str(fm.get("department") or "").strip()
    if not dept:
        raise ValueError("department is required")
    if org.department_id(dept) is None and dept not in _protocol_departments():
        raise ValueError(f"department '{dept}' is neither a hospital department (org.json) nor a protocol department name")
    dts = fm.get("doc_types")
    if isinstance(dts, str):
        dts = [x.strip() for x in dts.split(",") if x.strip()]
    if not isinstance(dts, list) or not dts or not all(isinstance(x, str) for x in dts):
        raise ValueError("doc_types: a non-empty list of document types")
    known = set(protocol.doc_types())
    bad = [x for x in dts if x not in known]
    if bad:
        raise ValueError(f"doc_types not in the catalogue: {', '.join(bad)}")
    gq = str(fm.get("guideline_query") or "").strip()
    if len(gq) > 200:
        raise ValueError("guideline_query is longer than 200 characters")
    if len(body) > MAX_BODY:
        raise ValueError(f"the body is longer than {MAX_BODY} characters")
    sections = _sections(body)
    focus = [x for x in sections.get("focus", [])]
    if not focus:
        raise ValueError("a '# Focus' section with at least one bullet is required")
    guidance = [(h, items) for h, items in sections.items() if h != "focus" and items]
    version = fm.get("version", 1)
    return {"name": name, "description": desc, "label": label, "department": dept, "doc_types": list(dict.fromkeys(dts)),
            "guideline_query": gq, "version": str(version), "focus": focus, "guidance": guidance, "allowed_tools": list(tools) if tools else None,
            "license": str(fm.get("license") or ""), "compatibility": str(fm.get("compatibility") or "")[:500],
            "focus_text": ", ".join(focus), "sha": hashlib.sha256(text.encode()).hexdigest()[:12]}


def _protocol_departments():
    out = set()
    for p in protocol.list_protocols():
        try:
            for rec in protocol.records(protocol.get(p["id"])):
                if rec.get("department"):
                    out.add(rec["department"])
        except Exception:
            continue
    out |= {r["department"] for r in _roles().values()}
    return out


def _sections(body: str) -> dict:
    """{heading key: [bullet items]} for every '# Heading' of the body; a bullet is a line starting with '-' or '*'."""
    out, pos = {}, [(m.start(), m.end(), m.group(1)) for m in _HEADING.finditer(body)]
    for i, (s, e, h) in enumerate(pos):
        chunk = body[e:pos[i + 1][0] if i + 1 < len(pos) else len(body)]
        items = [re.sub(r"^\s*[-*]\s+", "", ln).strip() for ln in chunk.splitlines() if re.match(r"^\s*[-*]\s+\S", ln)]
        out[re.sub(r"[^a-z0-9]+", "_", h.lower()).strip("_")] = items
    return out


def _read(path: Path):
    return path.read_text(encoding="utf-8") if path.exists() else None


def _key():
    parts = []
    for base in (REPO_DIR, hospital_dir()):
        for role in _roles():
            p = _file(base, role)
            parts.append((str(p), p.stat().st_mtime_ns if p.exists() else None))
    return tuple(parts)


def _file(base: Path, role: str) -> Path:
    """<base>/<role>/SKILL.md, or the hyphenated folder of the open standard when that is the one present."""
    p = base / role / SKILL_FILE
    alt = base / role.replace("_", "-") / SKILL_FILE
    return alt if not p.exists() and alt.exists() else p


def load() -> dict:
    """{role: skill} for every role, the hospital file first when it validates, else the repo default, else None. Cached on the
    files' modification times."""
    key = _key()
    if _cache["key"] == key:
        return _cache["data"]
    out = {}
    for role in _roles():
        skill, origin, problem = None, None, ""
        for base, where in ((hospital_dir(), "hospital"), (REPO_DIR, "default")):
            text = _read(_file(base, role))
            if text is None:
                continue
            try:
                s = parse(text)
                if s["name"] != role:
                    raise ValueError(f"name '{s['name']}' does not match the folder '{role}'")
                skill, origin = s, where
                break
            except ValueError as e:
                problem = f"{where} skill for {role} ignored: {e}"
                if where == "hospital":
                    _audit({"kind": "skill_invalid", "role": role, "origin": where, "error": str(e)[:300]})
        if skill:
            skill = {**skill, "origin": origin, "path": str(_file(hospital_dir() if origin == "hospital" else REPO_DIR, role)), "problem": problem}
        out[role] = skill
    _cache.update(key=key, data=out)
    return out


def get(role: str):
    """The skill of a role, or None when neither file exists or validates (the caller falls back to agents.ROLES)."""
    return load().get(role)


def text(role: str, origin: str = None) -> str:
    """The raw SKILL.md text: the active one, or origin 'default' / 'hospital' explicitly ('' when absent)."""
    if origin == "default":
        return _read(_file(REPO_DIR, role)) or ""
    if origin == "hospital":
        return _read(_file(hospital_dir(), role)) or ""
    s = get(role)
    return _read(Path(s["path"])) if s else (_read(_file(REPO_DIR, role)) or "")


def describe() -> list:
    """For the UI: every role with its active skill, origin, hash and whether a hospital edit exists (even an invalid one)."""
    skills = load()
    out = []
    for role in _roles():
        s = skills.get(role)
        hosp = _file(hospital_dir(), role).exists()
        out.append({"role": role, "active": {k: s[k] for k in ("label", "department", "description", "doc_types", "guideline_query", "focus", "version", "sha", "origin", "allowed_tools")} if s else None,
                    "hospital_edit": hosp, "problem": (s or {}).get("problem", ""), "text": text(role), "default_text": text(role, "default")})
    return out


def _audit(ev: dict):
    p = Path(config.DATA_ROOT) / "org_audit.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    from .store import now_iso
    with open(p, "a") as f:
        f.write(json.dumps({"ts": now_iso(), **ev}, ensure_ascii=False, default=str) + "\n")


def save(role: str, new_text: str, by: str = "") -> dict:
    """Validate and write the hospital edit of a role (previous version kept as SKILL.md.<timestamp>.bak); audited. ValueError on
    an invalid file or a name that does not match the role."""
    if role not in _roles():
        raise ValueError("unknown role")
    s = parse(new_text)
    if s["name"] != role:
        raise ValueError(f"name '{s['name']}' does not match the role '{role}'")
    d = hospital_dir() / role
    d.mkdir(parents=True, exist_ok=True)
    p = d / SKILL_FILE
    if p.exists():
        from .store import now_iso
        shutil.copy2(p, d / f"{SKILL_FILE}.{now_iso().replace(':', '-')}.bak")
    tmp = p.with_suffix(".tmp")
    tmp.write_text(new_text, encoding="utf-8")
    tmp.replace(p)
    _audit({"kind": "skill_saved", "role": role, "by": by or "", "sha": s["sha"], "label": s["label"], "department": s["department"]})
    _cache["key"] = None
    return {**s, "origin": "hospital", "path": str(p)}


def reset(role: str, by: str = "") -> bool:
    """Remove the hospital edit of a role (kept as .bak); the repo default applies again. False when there was none."""
    if role not in _roles():
        raise ValueError("unknown role")
    p = _file(hospital_dir(), role)
    if not p.exists():
        return False
    from .store import now_iso
    shutil.move(str(p), str(p.with_name(f"{SKILL_FILE}.{now_iso().replace(':', '-')}.reset.bak")))
    _audit({"kind": "skill_reset", "role": role, "by": by or ""})
    _cache["key"] = None
    return True
