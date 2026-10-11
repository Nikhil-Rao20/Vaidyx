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
