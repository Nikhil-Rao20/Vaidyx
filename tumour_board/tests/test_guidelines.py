"""guidelines: the cached index is rebuilt when the files or the index version change, and a rebuild re-embeds only the chunks
whose text changed (V1 item 5.1). A fake embedder stands in for the embedding model; the guideline folder is a temporary one."""
import json

import numpy as np
import pytest

from tumour_board import config, guidelines, search

PARA = "The National Cancer Grid recommends contrast enhanced CT of the thorax and upper abdomen for staging of lung cancer."


@pytest.fixture
def lib(tmp_path, monkeypatch):
    root = tmp_path / "guidelines"
    (root / "ncg_india").mkdir(parents=True)
    (root / "esmo").mkdir()
    (root / "ncg_india" / "lung.txt").write_text(PARA + "\n\n" + "Brain MRI is optimal for staging in non-small cell lung cancer patients.")
    (root / "esmo" / "nsclc.txt").write_text("ESMO: molecular testing for EGFR, ALK and ROS1 is recommended in advanced non-squamous NSCLC.")
    monkeypatch.setattr(config, "GUIDELINE_DIR", root)
    calls = []

    def fake_embed(texts, prefix=""):
        calls.append(list(texts))
        return np.array([[len(t) % 7 + 1.0, t.count("a") + 1.0] + [0.0] * 766 for t in texts], np.float32)
    monkeypatch.setattr(search, "_embed", fake_embed)
    return root, calls


def test_new_folder_is_indian():
    assert guidelines.SOURCES["tmc"][1] == "India"
    assert all(guidelines.SOURCES[f][1] == "India" for f in ("ncg_india", "icmr", "pmjay", "iria", "tmc"))


def test_cache_reused_when_nothing_changed(lib):
    root, calls = lib
    a = guidelines.GuidelineIndex()
    n = sum(map(len, calls))
    assert n == len(a.chunks) == 2
    calls.clear()
    b = guidelines.GuidelineIndex()
    assert calls == [] and [c["text"] for c in b.chunks] == [c["text"] for c in a.chunks]
    assert np.allclose(a.emb, b.emb)


def test_new_file_embeds_only_its_chunks(lib):
    root, calls = lib
    a = guidelines.GuidelineIndex()
    calls.clear()
    (root / "ncg_india" / "head_neck.txt").write_text("Oral cavity cancer: neck dissection is recommended for clinically node positive disease.")
    b = guidelines.GuidelineIndex()
    assert len(b.chunks) == 3 and sum(map(len, calls)) == 1 and "Oral cavity" in calls[0][0]
    assert b.reused == 2
    old = {c["file"]: a.emb[i] for i, c in enumerate(a.chunks)}
    for i, c in enumerate(b.chunks):
        if c["file"] in old:
            assert np.allclose(b.emb[i], old[c["file"]])


def test_version_bump_rebuilds_with_reuse(lib, monkeypatch):
    root, calls = lib
    guidelines.GuidelineIndex()
    calls.clear()
    monkeypatch.setattr(guidelines, "INDEX_VERSION", guidelines.INDEX_VERSION + 1)
    b = guidelines.GuidelineIndex()
    assert calls == [] and b.reused == 2  # same chunks, new version: rebuilt from the files, vectors reused
    assert json.loads((config.DATA_ROOT / "embed_cache" / "guidelines_index.json").read_text())["version"] == guidelines.INDEX_VERSION


def test_old_cache_without_keys_is_reused_through_its_chunk_list(lib, monkeypatch):
    root, calls = lib
    a = guidelines.GuidelineIndex()
    cdir = config.DATA_ROOT / "embed_cache"
    np.savez(cdir / "guidelines.npz", emb=a.emb, sig=np.array("old"))  # a cache written before 5.1: no keys
    d = json.loads((cdir / "guidelines_index.json").read_text()); d.pop("version"); (cdir / "guidelines_index.json").write_text(json.dumps(d))
    calls.clear()
    b = guidelines.GuidelineIndex()
    assert calls == [] and b.reused == 2


def test_india_boost_ranks_indian_source_first(lib):
    idx = guidelines.GuidelineIndex()
    hits = idx.search("staging lung cancer CT thorax", 3)
    assert hits[0]["region"] == "India" and hits[0]["file"].startswith("ncg_india/")


# ---------------------------------------------------------------- bibliography filter (V1 item 5.2)
REFERENCES = [  # entries the filter of V1 item 5.1 let through (from the library)
    "9. Eisenhauer EA, Therasse P , Bogaerts J, et al. New response evaluation\ncriteria in solid tumours: revised RECIST guideline (version 1.1). Eur J\n"
    "Cancer. 2009;45(2):228-247 .",
    "45. Dhillon S. Lazertinib: ﬁrst approval. Drugs. 2021;81(9):1107-1113 .",
    "27 . Huo L. A practical approach to grossing breast specimens. Ann  \nDiagn Pathol 2011;1 5:291–301.",
    "Reck M, Heigener DF, Mok T, Soria JC, Rabe KF. Management of non-small-cell lung cancer: recent developments. [Review]. Lancet. "
    "382(9893):709-19, 2013 Aug 24.",
    "Fitzgerald TL, Brinkley J, Zervos EE. “Pushing the envelope beyond a centimeter in rectal cancer: 48.  \noncologic implications of close, "
    "but negative margins.” J Am Coll Surg 213(5) (2011): 589-595.",
    "16. Loch T. Urologic imaging for localised prostate cancer in 2007. World J Urol 2007; 25:121–9",
    "Rosselli Del Turco M, Palli D, Cariddi A et al. Intensive diagnostic follow-up after treatment of primary breast cancer. A 49.  \n"
    "randomized trial. National Research Council Project on Breast Cancer follow-up. JAMA. 1994;271(20):1593-7.",
]
PROSE = [  # guideline text with inline citations or links: kept
    "*****Tamoxifen for five years in pre-menopausal women is standard adjuvant endocrine therapy. Aromatase \ninhibitor (AI) containing regimens "
    "(Tam-AI switch or 5 years of AI) constitute standard adjuvant endocrine \ntherapy in post-menopausal patients. The ATLAS trial has now established "
    "the role of tamoxifen beyond \n5 years and this option should be offered to those with high recurrence risk (Lancet. 2013;381:805–\n816). "
    "Consider extended adjuvant therapy with letrozole after 5 years of tamoxifen in node positive post-\nmenopausal women.",
    "Axilla: It is a common practice in many Indian centres to treat axilla for all node +ve cases, possibly due \nto sub-optimal axillary surgery "
    "or histopathological evaluation in practice settings. Recently the \nEORTC-AMAROS trial (Donker et al, Lancet Oncol. 2014) shows that in T1-2 "
    "clinically node negative \nwith sentinel node biopsy +ve, axillary RT results in excellent disease control.",
    "RESULTS\nA. Scienti ﬁc adaptations of the ESMO recommendations\nIn the initial pre-meeting survey, the 20 voting Asian experts\nreported on "
    "the ‘acceptability’ of the 97 recommendations\nfor the diagnosis, treatment and follow-up of patients with\nearly breast cancer from the "
    "most recent ESMO Clinical\nPractice Guidelines 20 (Supplementary Table S2 , available at\nhttps://doi.org/10.1016/j.esmoop.2024.102974), in the\n"
    "eight categories outlined in the text below and in Table 1.",
    "aA chest X-ray is an acceptable alternative to CT chest since there is no clear evidence to favour the latter. Optional- MRI can be problem "
    "solving for \nhepatic metastases if CT is equivocal; adding DWI improves accuracy (evidence from meta-analysis).",
    PARA,
]


@pytest.mark.parametrize("text", REFERENCES)
def test_bibliography_entries_are_removed(text):
    assert guidelines._is_reference_list(text)


@pytest.mark.parametrize("text", PROSE)
def test_guideline_prose_with_citations_is_kept(text):
    assert not guidelines._is_reference_list(text)
    assert guidelines._citation_coverage(text) < 0.5


def test_reference_paragraphs_are_dropped_at_build(lib):
    root, calls = lib
    (root / "esmo" / "nsclc.txt").write_text("Molecular testing for EGFR, ALK and ROS1 is recommended in advanced non-squamous NSCLC.\n\n" + REFERENCES[0])
    idx = guidelines.GuidelineIndex()
    esmo = [c["text"] for c in idx.chunks if c["file"].startswith("esmo/")]
    assert esmo and all("Eisenhauer" not in t for t in esmo) and "EGFR" in esmo[0]
