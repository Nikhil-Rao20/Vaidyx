"""Specialty knowledge packs (V1 item 5.5): schema and validation, India-first order, one pack per agent role, checklist
quotes verbatim on their pages, and the pack file is never loaded as a protocol."""
import copy, json, re

import pytest

from tumour_board import agents, config, guidelines, packs, protocol

KNOWN_INDIAN = {"ncg_india", "icmr", "pmjay", "iria", "tmc"}


def _raw():
    return json.loads((config.PROTOCOL_DIR / packs.PACK_FILE).read_text())


def _norm(s):
    return re.sub(r"\s+", " ", s).strip()


def test_load_validates_and_every_role_has_a_pack():
    data = packs.load()
    assert data["version"] and "reference only" in data["note"].lower()
    assert set(agents.ROLES) <= set(data["packs"])
    for role in agents.ROLES:
        pk = packs.pack(role)
        assert pk["role"] == role and pk["label"] and pk["sources"]
        assert isinstance(pk["checklists"], dict)
        if not pk["checklists"]:
            assert pk["checklist_note"], role  # a pack without a checklist says why


def test_india_first_in_every_pack_and_indian_source_present():
    for role in agents.ROLES:
        regions = [s["region"] for s in packs.pack(role)["sources"]]
        assert regions[0] == "India", role
        first_intl = next(i for i, r in enumerate(regions) if r != "India")
        assert all(r != "India" for r in regions[first_intl:]), role
        for s in packs.pack(role)["sources"]:
            assert s["folder"] in guidelines.SOURCES
            assert s["org"] == guidelines.SOURCES[s["folder"]][0] and s["region"] == guidelines.SOURCES[s["folder"]][1]


def test_plan_folders_per_pack():
    folders = lambda role: [f for f, _ in packs.allowed_sources(role)]
    assert folders("radiology") == ["iria", "ncg_india", "acr_appropriateness", "acr_rads", "rcr", "recist"]
    assert folders("pathology") == ["ncg_india", "icmr", "tmc", "cap_protocols", "rcpath", "iccr", "asco_cap"]
    for role in ("medical_oncology", "surgical_oncology", "radiation_oncology"):
        assert folders(role) == ["ncg_india", "icmr", "tmc", "pmjay", "esmo", "nice"]
    assert folders("nuclear_medicine") == ["ncg_india", "iria", "acr_appropriateness"]


def test_known_indian_folders_are_tagged_india():
    for f in KNOWN_INDIAN & set(guidelines.SOURCES):
        assert guidelines.SOURCES[f][1] == "India", f


def test_allowed_sources_shape():
    src = packs.allowed_sources("radiology")
    assert src[0] == ("iria", None)
    assert src[1] == ("ncg_india", frozenset({"synoptic-reporting-radiology-template.pdf"}))
    assert all(isinstance(f, str) and (files is None or isinstance(files, frozenset)) for f, files in src)
    with pytest.raises(KeyError):
        packs.allowed_sources("cardiology")
    with pytest.raises(KeyError):
        packs.pack("cardiology")


def test_checklists_and_text():
    cl = packs.checklist("radiology", "lung_nsclc")
    assert cl["region"] == "India" and cl["org"] == guidelines.SOURCES["iria"][0]
    assert cl["file"].startswith("iria/") and 8 <= len(cl["items"]) <= 14
    txt = packs.checklist_text("radiology", "lung_nsclc")
    assert txt.startswith("REPORTING CHECKLIST (reference: ICRI / IRIA synoptic reporting in lung cancer, India, pp. 46-47).")
    assert "never to interpret images, stage or recommend" in txt
    assert "\n- Lung mass: location, size, shape, consistency" in txt
    assert len(txt.splitlines()) == 1 + len(cl["items"])
    path = packs.checklist("pathology", "breast")
    assert path["region"] == "International" and path["file"].startswith("cap_protocols/")
    assert "International" in packs.checklist_text("pathology", "breast")
    for role in ("medical_oncology", "surgical_oncology", "radiation_oncology", "nuclear_medicine"):
        assert packs.checklist(role, "lung_nsclc") is None and packs.checklist_text(role, "lung_nsclc") == ""
    assert packs.checklist("radiology", "no_such_protocol") is None


def test_checklist_items_are_reporting_elements_not_actions():
    """Short element names, plain words, no em dashes; staging or impressions only as 'documented in the report'."""
    for role in agents.ROLES:
        for pid, cl in packs.pack(role)["checklists"].items():
            assert pid in {p["id"] for p in protocol.list_protocols()}
            assert 8 <= len(cl["items"]) <= 14, (role, pid)
            for it in cl["items"]:
                assert "—" not in it["text"] and len(it["text"]) <= 90
                low = it["text"].lower()
                if re.search(r"\bstage\b|impression|bi-rads|recommend", low):
                    assert "documented" in low, it["text"]
                assert "recommend" not in low


def test_describe():
    d = packs.describe()
    assert [x["role"] for x in d][:1] == ["radiology"] and {x["role"] for x in d} >= set(agents.ROLES)
    rad = next(x for x in d if x["role"] == "radiology")
    assert rad["sources"][0]["region"] == "India"
    assert rad["checklists"]["breast"]["title"].startswith("ICRI / IRIA") and rad["checklists"]["breast"]["pages"] == "pp. 52-54"
    onc = next(x for x in d if x["role"] == "medical_oncology")
    assert onc["checklists"] == {} and "Pre-Authorization" in onc["checklist_note"]


@pytest.mark.parametrize("mutate,msg", [
    (lambda d: d["packs"]["radiology"]["sources"].append({"folder": "no_such_folder"}), "unknown guideline folder"),
    (lambda d: d["packs"]["pathology"]["sources"].append({"folder": "icmr"}), "after international"),
    (lambda d: d["packs"].pop("nuclear_medicine"), "no pack for role"),
    (lambda d: d["packs"]["radiology"]["checklists"].__setitem__("prostate", d["packs"]["radiology"]["checklists"]["breast"]), "not a protocol"),
    (lambda d: d["packs"]["radiology"]["checklists"]["breast"]["items"][0].pop("page"), "has no page"),
    (lambda d: d["packs"]["radiology"]["checklists"]["breast"]["items"][0].__setitem__("quote", "  "), "has no quote"),
    (lambda d: d["packs"]["radiology"]["sources"][1].__setitem__("files", "x.pdf"), "files"),
    (lambda d: d["packs"]["pathology"]["checklists"]["breast"].__setitem__("file", "nowhere/x.pdf"), "known guideline folder"),
])
def test_validation_errors(mutate, msg):
    d = copy.deepcopy(_raw())
    mutate(d)
    with pytest.raises(ValueError, match=msg):
        packs._validate(d)


def test_validation_names_the_pack():
    d = copy.deepcopy(_raw())
    d["packs"]["surgical_oncology"]["sources"].insert(0, {"folder": "esmo"})
    with pytest.raises(ValueError, match="pack surgical_oncology"):
        packs._validate(d)


def test_load_is_cached_on_mtime(tmp_path, monkeypatch):
    d = tmp_path / "protocols"
    d.mkdir()
    for f in config.PROTOCOL_DIR.glob("*.json"):
        (d / f.name).write_text(f.read_text())
    monkeypatch.setattr(config, "PROTOCOL_DIR", d)
    first = packs.load()
    assert packs.load() is first
    bad = json.loads((d / packs.PACK_FILE).read_text())
    bad["packs"]["radiology"]["sources"].append({"folder": "nowhere"})
    (d / packs.PACK_FILE).write_text(json.dumps(bad))
    import os
    st = (d / packs.PACK_FILE).stat()
    os.utime(d / packs.PACK_FILE, ns=(st.st_atime_ns, st.st_mtime_ns + 10_000_000))
    with pytest.raises(ValueError, match="unknown guideline folder"):
        packs.load()
    monkeypatch.undo()
    assert packs.load()["packs"]["radiology"]["sources"][-1] == {"folder": "recist"}


def test_pack_file_is_not_a_protocol():
    assert not protocol._is_protocol(_raw())
    assert not protocol.exists("specialty_packs")
    assert "specialty_packs" not in {p["id"] for p in protocol.list_protocols()}
    assert "NCCN" not in (config.PROTOCOL_DIR / packs.PACK_FILE).read_text()


def test_every_checklist_quote_is_verbatim_on_its_page():
    root = config.GUIDELINE_DIR
    if not root.is_dir():
        pytest.skip("guideline library not on this machine")
    pypdf = pytest.importorskip("pypdf")
    readers = {}
    checked = 0
    for role, pk in _raw()["packs"].items():
        for pid, cl in pk["checklists"].items():
            path = root / cl["file"]
            assert path.is_file(), cl["file"]
            assert cl["file"].split("/")[0] in guidelines.SOURCES
            r = readers.setdefault(path, pypdf.PdfReader(str(path)))
            pages = {}
            for it in cl["items"]:
                if it["page"] not in pages:
                    pages[it["page"]] = _norm(r.pages[it["page"] - 1].extract_text())
                assert _norm(it["quote"]) in pages[it["page"]], (role, pid, it)
                checked += 1
    assert checked >= 6 * 8
