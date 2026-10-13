"""Agent skills (12 Oct): the six repo SKILL.md files load and match the code defaults, validation refuses what a skill may not
change (new roles, unknown document types, no focus), a hospital edit wins and is audited, a broken hospital edit is ignored
with an audit entry, and the hard rules stay in the system prompt whatever the skill says."""
import json

import pytest

from tumour_board import agents, config, skills

RULES = "Strict rules: use only what is written in the documents"


def _hospital(role, text):
    d = skills.hospital_dir() / role
    d.mkdir(parents=True, exist_ok=True)
    (d / skills.SKILL_FILE).write_text(text)
    skills._cache["key"] = None


def _audit():
    p = config.DATA_ROOT / "org_audit.jsonl"
    return [json.loads(l) for l in p.read_text().splitlines()] if p.exists() else []


def test_every_role_has_a_valid_default_skill_matching_the_code_defaults():
    loaded = skills.load()
    for role, code in agents.ROLES.items():
        s = loaded[role]
        assert s and s["origin"] == "default" and not s["problem"], role
        assert s["label"] == code["label"] and s["department"] == code["department"] and s["doc_types"] == code["doc_types"], role
        assert len(s["focus"]) >= 3 and s["description"] and s["sha"]
        assert s["guideline_query"] == agents.ROLE_QUERY[role], role


def test_spec_merges_the_skill_and_system_prompt_keeps_the_hard_rules():
    r = agents.spec("radiology")
    assert r["skill_origin"] == "default" and r["guidance"] and r["doc_types"] == agents.ROLES["radiology"]["doc_types"]
    sysm = agents._system("radiology")
    assert "Focus: modality and date of each study" in sysm
    assert "What to look for in the records:" in sysm and RULES in sysm
    assert "do not recommend, suggest or choose any treatment" in sysm


@pytest.mark.parametrize("bad,msg", [
    ("---\nname: cardiology\ndescription: x\nlabel: C\ndepartment: Radiology\ndoc_types: [ct]\n---\n# Focus\n- a\n", "not a known agent role"),
    ("---\nname: radiology\ndescription: x\nlabel: R\ndepartment: Radiology\ndoc_types: [ct, selfie]\n---\n# Focus\n- a\n", "doc_types not in the catalogue"),
    ("---\nname: radiology\ndescription: x\nlabel: R\ndepartment: Radiology\ndoc_types: [ct]\n---\n# Notes\n- a\n", "'# Focus' section"),
    ("---\nname: radiology\ndescription: x\nlabel: R\ndepartment: Astrology\ndoc_types: [ct]\n---\n# Focus\n- a\n", "neither a hospital department"),
    ("no frontmatter at all\n# Focus\n- a\n", "frontmatter"),
    ("---\nname: radiology\ndescription: x\nlabel: R\ndepartment: Radiology\ndoc_types: [ct]\n---\n# Focus\n- a\n" + "x" * 20001, "longer than 20000"),
])
def test_parse_refuses_what_a_skill_may_not_change(bad, msg):
    with pytest.raises(ValueError) as e:
        skills.parse(bad)
    assert msg in str(e.value)


HOSP = ("---\nname: radiology\ndescription: Hospital edit.\nlabel: Radio-diagnosis support\ndepartment: Radio-diagnosis\n"
        "doc_types: [ct, mri]\nguideline_query: CT report contents\nversion: 2\n---\n# Focus\n- contrast phase stated\n- slice thickness\n"
        "# What to look for in the records\n- the scanner model\n")


def test_hospital_edit_wins_is_audited_and_reset_restores_the_default():
    s = skills.save("radiology", HOSP, by="admin")
    assert s["origin"] == "hospital" and s["label"] == "Radio-diagnosis support" and s["doc_types"] == ["ct", "mri"]
    r = agents.spec("radiology")
    assert r["label"] == "Radio-diagnosis support" and r["focus"] == "contrast phase stated, slice thickness" and r["guideline_query"] == "CT report contents"
    assert r["skill_origin"] == "hospital" and r["skill_sha"] == s["sha"]
    sysm = agents._system("radiology")
    assert "the scanner model" in sysm and RULES in sysm  # guidance in, hard rules still there
    assert [e["kind"] for e in _audit()] == ["skill_saved"] and _audit()[0]["by"] == "admin"
    skills.save("radiology", HOSP.replace("version: 2", "version: 3"), by="admin")
    assert any(p.name.endswith(".bak") for p in (skills.hospital_dir() / "radiology").iterdir())  # previous version kept
    assert skills.reset("radiology", by="admin") is True
    assert agents.spec("radiology")["skill_origin"] == "default" and agents.spec("radiology")["label"] == "Radiology support"
    assert _audit()[-1]["kind"] == "skill_reset" and skills.reset("radiology") is False


def test_broken_hospital_edit_is_ignored_with_an_audit_entry():
    _hospital("pathology", "---\nname: pathology\ndescription: x\nlabel: P\ndepartment: Pathology\ndoc_types: [histopathology]\n---\n# Nothing\n")
    s = skills.get("pathology")
    assert s["origin"] == "default" and "hospital skill for pathology ignored" in s["problem"]
    assert _audit()[-1]["kind"] == "skill_invalid" and _audit()[-1]["role"] == "pathology"
    assert agents.spec("pathology")["label"] == "Pathology support"


def test_save_refuses_a_name_that_does_not_match_the_role():
    with pytest.raises(ValueError):
        skills.save("pathology", HOSP, by="admin")  # name: radiology inside
    assert not (skills.hospital_dir() / "pathology" / skills.SKILL_FILE).exists()


def test_describe_lists_every_role_with_text_and_edit_flag():
    d = {x["role"]: x for x in skills.describe()}
    assert set(d) == set(agents.ROLES)
    assert d["radiology"]["active"]["origin"] == "default" and d["radiology"]["text"].startswith("---") and not d["radiology"]["hospital_edit"]
    _hospital("radiology", HOSP)
    d = {x["role"]: x for x in skills.describe()}
    assert d["radiology"]["hospital_edit"] and d["radiology"]["active"]["origin"] == "hospital" and d["radiology"]["default_text"] != d["radiology"]["text"]


def test_hyphenated_name_and_allowed_tools_restrict_only():
    hy = HOSP.replace("name: radiology", "name: radiology").replace("guideline_query: CT report contents\n", "guideline_query: CT report contents\nallowed-tools: list_documents read_document find_values\n")
    s = skills.parse(hy)
    assert s["allowed_tools"] == ["list_documents", "read_document", "find_values"]
    with pytest.raises(ValueError) as e:
        skills.parse(hy.replace("find_values", "write_document"))
    assert "do not have" in str(e.value)
    assert skills.parse(HOSP.replace("name: radiology", "name: medical-oncology"))["name"] == "medical_oncology"
    with pytest.raises(ValueError):
        skills.parse(HOSP.replace("name: radiology", "name: radiology--x"))
    skills.save("radiology", hy, by="admin")
    assert agents.spec("radiology")["allowed_tools"] == ["list_documents", "read_document", "find_values"]
