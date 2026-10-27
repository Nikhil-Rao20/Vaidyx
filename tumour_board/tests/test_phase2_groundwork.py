"""The shared groundwork for the Phase 2 cancer checklists (night-v3 item 2.1): the hard-coded lists know the new facts, document types and
cancers (the patient at a glance, the report groups and sections, the cancer-against-the-reports warning, the guideline cancer words,
the follow-up task words, the HIS label table, the units and the owner aliases). Synthetic values only."""
import json

import pytest

from tumour_board import config, followup, guidelines, his_client, protocol, slots, steps, units

# the 72 facts the research note (docs/night-v3/research/01_cancer_checklists.md) proposed for Phase 2
NEW_FACTS = (
    "tumour_site_colon", "nodes_examined", "obstruction_perforation", "tumour_site_stomach", "cdh1_result", "tumour_location_oesophagus",
    "siewert_type", "trg", "lirads_category", "inr", "hbsag", "anti_hcv", "hbv_core_ab", "afp", "pivka", "child_pugh_class", "varices_finding",
    "hvpg_mmhg", "flr_percent", "gb_mass", "ca19_9", "vessel_involvement", "bile_duct_involvement", "cystic_duct_margin", "ca125", "beta_hcg",
    "ldh", "inhibin_b", "he4", "brca_status", "p53", "pole", "psa", "gleason_isup", "positive_cores", "hrd_status", "corrected_calcium",
    "embryonal_component", "igcccg_group", "fertility_preservation", "testosterone", "lh", "fsh", "cord_mobility", "laryngeal_function",
    "laryngeal_subsite", "bethesda_category", "thyroglobulin", "calcitonin", "tirads", "extrathyroid_extension", "b_symptoms",
    "molecular_markers_haem", "bone_marrow_result", "deauville_score", "csf_cytology", "flow_cytometry_result", "cytogenetics_result",
    "beta2_microglobulin", "anaplasia", "loh_1p_16q", "ophthalmic_examination", "rb_group", "germline_result", "alkaline_phosphatase",
    "sarcoma_fusion", "percent_necrosis", "tumour_depth", "kps", "idh_status", "codeletion_1p19q", "mgmt_promoter",
)
NEW_DOC_TYPES = ("bone_marrow", "flow_cytometry", "cytogenetics", "csf", "echocardiogram", "ophthalmology_note", "audiometry")
# every Phase 2 protocol id, built or still to come (plan section 4, Phase 2)
PHASE2_IDS = ("colorectal_colon", "stomach", "oesophagus", "liver_hcc", "gallbladder", "ovary", "corpus_uteri", "prostate", "kidney", "germ_cell",
              "larynx", "thyroid", "lymphoma", "leukaemia", "wilms", "retinoblastoma", "bone_sarcoma", "soft_tissue_sarcoma", "brain_cns",
              "generic_haem")
GLANCE_TO_SECTION = {"diagnosis": {"pathology", "labs"}, "extent": {"imaging", "presenting", "other", "pathology"},
                     "fitness": {"presenting", "labs", "imaging"}, "background": {"presenting", "prior_treatment"}}


def _protocol_ids():
    return {p["id"] for p in protocol.list_protocols()}


# ---- the catalogue and the patient at a glance ----------------------------------------------------------------------------------------

def test_the_new_facts_and_document_types_are_in_the_catalogue():
    cat = protocol.facts()
    assert len(NEW_FACTS) == 72 == len(set(NEW_FACTS))
    assert [f for f in NEW_FACTS if f not in cat] == []
    assert set(NEW_DOC_TYPES) <= set(protocol.doc_types()) and protocol.doc_types()[-1] == "other"


def test_every_new_fact_is_at_a_glance_exactly_once_and_has_a_section():
    order = [f for _, _, fs in steps.GLANCE for f in fs]
    assert len(order) == len(set(order)), sorted({f for f in order if order.count(f) > 1})
    assert [f for f in NEW_FACTS if order.count(f) != 1] == []
    assert [f for f in order if f not in protocol.facts()] == []  # nothing at a glance the catalogue does not know
    assert [f for f in NEW_FACTS if f not in slots.FACT_SECTION] == []
    assert set(slots.FACT_SECTION.values()) <= set(slots.SECTION_LABEL)
    group = {f: g for g, _, fs in steps.GLANCE for f in fs}
    off = [(f, group[f], slots.FACT_SECTION[f]) for f in NEW_FACTS if slots.FACT_SECTION[f] not in GLANCE_TO_SECTION[group[f]]]
    assert off == []
    assert set(steps.STAGE_FACTS) == {"recorded_stage", "figo_stage"}  # no new stage fact: Vaidyx never computes a stage


def test_lab_facts_sit_with_the_labs():
    for f in ("psa", "ca125", "afp", "beta_hcg", "ldh", "ca19_9", "inr", "hbsag", "alkaline_phosphatase", "testosterone"):
        assert slots.FACT_SECTION[f] == "labs", f
    for f in ("kps", "b_symptoms", "child_pugh_class", "igcccg_group", "laryngeal_function", "fertility_preservation"):
        assert slots.FACT_SECTION[f] == "presenting", f
    assert slots.FACT_SECTION["ophthalmic_examination"] == slots.FACT_SECTION["rb_group"] == "other"


# ---- document types: report groups, sections, follow-up --------------------------------------------------------------------------------

def test_every_document_type_has_a_group_and_a_section():
    grouped = set().union(*(types for _, _, types in steps.DOC_GROUPS))
    assert [t for t in protocol.doc_types() if t not in grouped and t != "other"] == []
    assert [t for t in protocol.doc_types() if t not in slots.DOC_SECTION] == []
    assert {"bone_marrow", "flow_cytometry", "cytogenetics", "csf"} <= dict((g, ts) for g, _, ts in steps.DOC_GROUPS)["pathology"]
    assert {"echocardiogram", "ophthalmology_note", "audiometry"} <= dict((g, ts) for g, _, ts in steps.DOC_GROUPS)["notes"]
    assert steps.doc_group({"classification": {"doc_type": "bone_marrow"}}) == "pathology"
    assert slots.DOC_SECTION["csf"] == "pathology" and slots.DOC_SECTION["echocardiogram"] == "other"


@pytest.mark.parametrize("task,types", [
    ("Bone marrow aspiration and biopsy", {"bone_marrow"}),
    ("Flow cytometry immunophenotyping of peripheral blood", {"flow_cytometry"}),
    ("Karyotype on the marrow sample", {"cytogenetics", "bone_marrow"}),
    ("HER2 FISH", {"molecular"}),  # a lone FISH stays molecular
    ("CSF cytology after lumbar puncture", {"csf"}),
    ("2D echo before anthracyclines", {"echocardiogram"}),
    ("Pure tone audiometry before cisplatin", {"audiometry"}),
    ("Eye examination under anaesthesia", {"ophthalmology_note"}),
    ("EUA and cystoscopy", {"endoscopy"}),  # a cervix examination under anaesthesia is not an eye examination
    ("Follow up in OPD", set()),
])
def test_follow_up_task_words(task, types):
    assert followup.task_doc_types(task) == types


def test_the_new_types_are_requestable():
    assert set(NEW_DOC_TYPES) <= set(followup.REQUESTABLE) and set(followup.REQUESTABLE) <= set(protocol.doc_types())


# ---- the cancer chosen against the report titles ------------------------------------------------------------------------------------

def test_site_words_and_names_cover_the_same_cancers():
    assert set(steps.SITE_WORDS) == set(steps.SITE_NAME)
    assert set(steps.SITE_WORDS) <= _protocol_ids() | set(PHASE2_IDS)
    for pid in _protocol_ids():
        if pid in steps.SITE_WORDS:
            assert steps.SITE_NAME.get(pid), pid
    # the blood cancers and the sarcomas name a body part in their titles, not the disease: no warning for them (the safer side)
    assert not {"lymphoma", "leukaemia", "bone_sarcoma", "soft_tissue_sarcoma", "generic_haem"} & set(steps.SITE_WORDS)
    assert all(w == w.lower() for ws in steps.SITE_WORDS.values() for w in ws)


def _doc(doc_id, title):
    return {"doc_id": doc_id, "title": title, "date": "2026-10-20", "check": {"status": "checked", "reasons": []}, "final": {"preliminary": False}}


def _view():
    return {"sections": []}


@pytest.fixture
def labels(monkeypatch):
    """A protocol label for the warning text even before that checklist file is written."""
    real = protocol.get

    def get(pid):
        try:
            return real(pid)
        except FileNotFoundError:
            return {"id": pid, "label": pid.replace("_", " ").capitalize()}
    monkeypatch.setattr(protocol, "get", get)


def test_a_colon_case_with_a_colonoscopy_and_a_ct_abdomen_has_no_warning(labels):
    docs = [_doc("D1", "COLONOSCOPY REPORT"), _doc("D2", "CECT ABDOMEN AND PELVIS"), _doc("D3", "HISTOPATHOLOGY REPORT")]
    assert steps.warnings({"protocol": "colorectal_colon"}, docs, _view()) == []
    # the rectum checklist shares the colon words: related cancers only prevent a warning
    assert steps.warnings({"protocol": "colorectal_rectum"}, docs, _view()) == []


def test_a_kidney_case_whose_titles_say_prostate_twice_is_warned(labels):
    docs = [_doc("D1", "MRI PROSTATE (MULTIPARAMETRIC)"), _doc("D2", "TRUS GUIDED PROSTATE BIOPSY: HISTOPATHOLOGY"), _doc("D3", "CBC")]
    w = steps.warnings({"protocol": "kidney"}, docs, _view())
    assert [x["kind"] for x in w] == ["cancer_mismatch"]
    assert w[0]["text"].startswith("The reports mention the prostate (") and "none mention the kidney." in w[0]["text"]
    # one renal title settles it; and a Wilms tumour case with renal titles is not warned either
    assert steps.warnings({"protocol": "kidney"}, docs + [_doc("D4", "CECT ABDOMEN (RENAL MASS PROTOCOL)")], _view()) == []
    assert steps.warnings({"protocol": "wilms"}, [_doc("D1", "CECT ABDOMEN: LEFT RENAL MASS"), _doc("D2", "NEPHRECTOMY HISTOPATHOLOGY")], _view()) == []


def test_a_lymphoma_case_is_never_warned_by_site_words(labels):
    docs = [_doc("D1", "MRI PROSTATE"), _doc("D2", "PROSTATE BIOPSY")]
    assert steps.warnings({"protocol": "lymphoma"}, docs, _view()) == []


# ---- guideline cancer words ---------------------------------------------------------------------------------------------------------

def test_cancer_words_name_protocols():
    known = _protocol_ids() | set(PHASE2_IDS)
    assert set(guidelines.CANCER_WORDS) <= known
    assert set(PHASE2_IDS) <= set(guidelines.CANCER_WORDS)
    assert all(ws and all(w == w.lower() for w in ws) for ws in guidelines.CANCER_WORDS.values())
    assert "urolog" in guidelines.CANCER_WORDS["prostate"] and "hematolymphoid" in guidelines.CANCER_WORDS["lymphoma"]


def test_the_ncg_books_match_their_cancers():
    books = {"colorectal_colon": "management-of-colorectal-cancer.pdf", "stomach": "ncg-gi-draft-2021-gastric-cancer.pdf",
             "oesophagus": "ncg-guidelines-for-thoracic-cancer-2019.pdf", "liver_hcc": "ncg-gi-hepatocellular-carcinoma.docx",
             "gallbladder": "ncg-gi-draft-2021-gall-bladder-cancer.pdf", "ovary": "ncg-guidelines-for-gynecological-cancer-2019.docx",
             "corpus_uteri": "ncg-guidelines-for-gynecological-cancer-2019.docx", "prostate": "ncg-guidelines-for-urological-malignancies-2019.pdf",
             "kidney": "ncg-guidelines-for-urological-malignancies-2019.pdf", "germ_cell": "ncg-guidelines-for-urological-malignancies-2019.pdf",
             "larynx": "ncg-guidelines-for-head-neck-cancer-2019.pdf", "lymphoma": "ncg-guidelines-for-adult-hematolymphoid-2019.pdf",
             "leukaemia": "ncg-guidelines-for-adult-hematolymphoid-2019.pdf", "wilms": "ncg-guidelines-for-pediatric-haematolymphoid-solid-tumours-2019.pdf",
             "retinoblastoma": "ncg-guidelines-for-pediatric-haematolymphoid-solid-tumours-2019.pdf",
             "bone_sarcoma": "ncg-guidelines-for-bone-soft-tissue-tumours-2019.pdf", "soft_tissue_sarcoma": "ncg-guidelines-for-bone-soft-tissue-tumours-2019.pdf"}
    for pid, f in books.items():
        name = f.lower() + " " + f.rsplit(".", 1)[0].replace("-", " ").replace("_", " ")
        assert any(w in name for w in guidelines.CANCER_WORDS[pid]), (pid, f)


def test_guideline_queries_for_every_new_cancer(monkeypatch):
    from tumour_board import store
    for pid in PHASE2_IDS:
        monkeypatch.setattr(store, "get_case", lambda cid, pid=pid: {"protocol": pid})
        monkeypatch.setattr(store, "get_state", lambda cid: {})
        monkeypatch.setattr(protocol, "get", lambda p: {"id": p, "label": p})
        qs = guidelines.queries_for_case("TB-X")
        assert len(qs) == 2 and all("treat" not in q.lower() for q in qs), (pid, qs)


# ---- the HIS label table and LOINC codes --------------------------------------------------------------------------------------------

@pytest.mark.parametrize("label,fact", [
    ("Serum PSA (total)", "psa"), ("Free PSA", "psa"), ("CA 19-9", "ca19_9"), ("CA19.9", "ca19_9"), ("CA-125", "ca125"), ("CA 125", "ca125"),
    ("Beta-2 microglobulin", "beta2_microglobulin"), ("Beta HCG", "beta_hcg"), ("Alpha fetoprotein (AFP)", "afp"), ("PIVKA-II", "pivka"),
    ("Anti-HBc (total)", "hbv_core_ab"), ("LDH", "ldh"), ("Alkaline phosphatase", "alkaline_phosphatase"), ("ALK PHOS", "alkaline_phosphatase"),
    ("ALK rearrangement", "alk"), ("Anaplastic lymphoma kinase (ALK)", "alk"), ("Anaplasia", "anaplasia"), ("Inhibin B", "inhibin_b"),
    ("HE4", "he4"), ("Serum thyroglobulin", "thyroglobulin"), ("Calcitonin", "calcitonin"), ("PT / INR", "inr"),
    ("Serum calcium (corrected)", "corrected_calcium"), ("Serum testosterone", "testosterone"), ("LH", "lh"), ("FSH", "fsh"),
    ("Gleason score", "gleason_isup"), ("ISUP grade group", "gleason_isup"), ("Grade", "grade"), ("Positive cores", "positive_cores"),
    ("Bethesda category", "bethesda_category"), ("TI-RADS", "tirads"), ("LI-RADS category", "lirads_category"), ("BI-RADS category", ""),
    ("Child-Pugh class", "child_pugh_class"), ("Deauville score", "deauville_score"), ("B symptoms", "b_symptoms"),
    ("Karnofsky performance status", "kps"), ("ECOG performance status", "ecog"), ("IDH1/2 mutation", "idh_status"),
    ("MGMT promoter methylation", "mgmt_promoter"), ("1p/19q codeletion", "codeletion_1p19q"), ("BRCA1/BRCA2", "brca_status"),
    ("p53 (IHC)", "p53"), ("POLE mutation", "pole"), ("Lymph nodes examined", "nodes_examined"), ("Lymph nodes", "nodal_findings"),
    ("Vocal cord mobility", "cord_mobility"), ("Laryngeal subsite", "laryngeal_subsite"), ("Retinoblastoma group (ICRB)", "rb_group"),
    ("Tumour regression grade", "trg"), ("Cystic duct margin", "cystic_duct_margin"), ("Resection margins", "margins"),
    ("Haemoglobin (Hb)", "haemoglobin"), ("Viral markers: HIV, HBsAg, anti-HCV", "hiv_status"),
])
def test_his_labels(label, fact):
    assert his_client.fact_for(None, label) == fact


def test_his_codes_name_known_facts_and_types():
    t = his_client.codes()
    facts, types = set(protocol.facts()), set(protocol.doc_types())
    assert set(t["fact_by_loinc"].values()) <= facts and {f for _, f in t["fact_by_label"]} <= facts
    assert set(t["doc_type_by_loinc"].values()) <= types and set(t["pathology_family"]["types"]) <= types
    assert {"bone_marrow", "flow_cytometry", "cytogenetics", "csf"} <= set(t["pathology_family"]["types"])
    assert his_client.fact_for({"code": "2857-1"}) == "psa" and his_client.fact_for({"code": "24108-3"}) == "ca19_9"
    assert his_client.fact_for({"code": "10334-1"}) == "ca125" and his_client.fact_for({"code": "6768-6"}) == "alkaline_phosphatase"


# ---- units, keywords and the classify prompt ----------------------------------------------------------------------------------------

def test_new_analytes_have_known_units():
    t = units.table()
    spellings = {u for f in t["families"].values() for u in f["units"]}
    for a in ("psa", "ca125", "afp", "beta_hcg", "ldh", "ca19_9", "thyroglobulin", "calcitonin", "alkaline_phosphatase", "beta2_microglobulin",
              "corrected_calcium", "testosterone", "inr"):
        assert a in t["analytes"] and t["analytes"][a]["labels"], a
        assert set(t["analytes"][a]["units"]) <= spellings, a
    assert units.same_quantity("beta-hCG 12 mIU/mL", "12 IU/L") and units.same_quantity("ALP 110 U/L", "110 IU/L")
    assert units.same_quantity("35 U/mL", "35 kU/L") and not units.same_quantity("35 U/mL", "35 U/L")
    assert not units.same_quantity("AFP 12.1 ng/mL", "AFP 10 IU/mL")  # a rounded conversion: never by default
    assert units.same_quantity("AFP 12.1 ng/mL", "AFP 10 IU/mL", tol=0.02)
    assert units.numbers_equivalent("PSA 4.2", "Serum PSA 4.2 ng/mL") and not units.numbers_equivalent("PSA 4.3", "Serum PSA 4.2 ng/mL")


def test_keyword_table_and_classify_prompt_know_the_new_types():
    raw = json.loads((config.PROTOCOL_DIR / "doc_type_keywords.json").read_text())
    assert set(NEW_DOC_TYPES) <= set(raw["types"])
    note = " ".join(raw["_note"])
    assert "FISH" in note and "cytogenetics beats molecular" in note
    src = (config.PROTOCOL_DIR.parent / "extract.py").read_text()
    for t in NEW_DOC_TYPES:
        assert f'"- {t}: ' in src or f"\\n- {t}: " in src, t
