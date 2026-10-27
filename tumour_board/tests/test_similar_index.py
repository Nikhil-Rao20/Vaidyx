"""night-v3 item 7.1: the Case profile index of Similar Case Files (tumour_board/similar.py, part 1). Profiles built by code from the
verified facts, the stage as recorded / confirmed / agreed, the board records and the Case summary; the index (profiles, index.json,
index.npz) kept up to date by signature; the candidates by BM25 plus dense vectors fused by RRF, same cancer group only, never the file
itself, the same patient or a linked file. Synthetic Case Files only; search._embed is a deterministic fake (fastembed never loads);
the real case is never opened (a hand-made protected directory in the temporary data root stands in for it)."""
import asyncio
import hashlib
import json
import re
from pathlib import Path

import numpy as np
import pytest

from tumour_board import config, postboard, published, scheduler, search, similar, store
from tumour_board.tests.util import add, fact, make_doc

DIM = 16


@pytest.fixture(autouse=True)
def fake_embed(monkeypatch):
    """search._embed replaced: a float32 vector from a hash of the text; every text embedded is counted."""
    calls = []

    def emb(texts, prefix=""):
        calls.append([prefix + t for t in texts])
        out = []
        for t in texts:
            h = hashlib.sha256((prefix + t).encode()).digest()
            out.append(np.frombuffer(h[:DIM], dtype=np.uint8).astype(np.float32) + 1.0)
        return np.array(out, dtype=np.float32)
    monkeypatch.setattr(search, "_embed", emb)
    similar._loaded.update(key=None, meta=None, matrix=None)
    return calls


def embedded(calls, prefix=""):
    """The chunk texts embedded (query embeddings carry the query prefix and are left out)."""
    return [t for c in calls for t in c if not t.startswith(similar.QUERY_PREFIX)]


_N = [0]


def mk(cid, protocol="breast", name=None, mrn=None, agesex="54 Y / F", setting="early", cancer_name=None, uhid=None,
       linked=None, listed=True):
    _N[0] += 1
    patient = {"name": name or f"SYNTHETIC, Asha Devi {'ABCDEFGHIJKLMNOPQRSTUVWXYZ'[_N[0] % 26]}{_N[0]}", "mrn": mrn or f"SYN-7{_N[0]:05d}", "agesex": agesex}
    if uhid:
        patient["ids"] = [{"kind": "uhid", "value": uhid}]
    c = store.create_case(cid, patient, protocol, created_by="test", setting=setting)
    if cancer_name:
        c["cancer_name"] = cancer_name
    if linked:
        c["linked_cases"] = [{"case_id": x} for x in linked]
    if not listed:
        c["listing"] = {"status": "awaiting_listing"}
    store.save_case(c)
    return cid


def record(cid, outcome="decision", text="Breast conserving surgery, then adjuvant chemotherapy.", board_date="2026-09-10", rid=None, **over):
    st = store.get_state(cid)
    rec = {"id": rid or f"B{len(st['board_records']) + 1:06d}", "outcome": outcome, "outcome_type": outcome, "decision_text": text,
           "intent": "curative", "modalities": ["surgery", "chemotherapy"], "sequence": "Surgery first", "board_date": board_date,
           "recorded_at": f"{board_date}T12:00:00", "rationale": "Early disease on imaging", "stage_as_agreed": "cT2 N0 M0", "version": 1, **over}
    st["board_records"].append(rec)
    store.save_state(cid, st)
    return rec


def breast_docs(cid, her2=None, distant=None, extra=None):
    ihc = {"er": fact("Positive (Allred 8/8)", quote="ER: Positive (Allred 8/8)")}
    if her2:
        ihc["her2"] = fact(her2, quote=f"HER2: {her2}")
    docs = [make_doc(f"D{cid[-3:]}01", "histopathology", date="2026-09-03", title="HISTOPATHOLOGY REPORT",
                     facts={"histologic_type": fact("Invasive ductal carcinoma", quote="Diagnosis: Invasive ductal carcinoma"),
                            "grade": fact("Grade 2", quote="Nottingham Grade 2")}),
            make_doc(f"D{cid[-3:]}02", "ihc", date="2026-09-04", title="IHC REPORT", facts=ihc)]
    ct = {"recorded_stage": fact("cT2 N0 M0", quote="Impression: stage as recorded cT2 N0 M0")}
    if distant:
        ct["distant_findings"] = fact(distant, quote=f"Findings: {distant}")
    docs.append(make_doc(f"D{cid[-3:]}03", "ct", date="2026-09-05", title="CT THORAX REPORT", facts=ct))
    add(cid, *docs, *(extra or []))


def decided(cid, **kw):
    """A listed breast Case File with reports and one board decision: eligible."""
    mk(cid, **kw)
    breast_docs(cid)
    record(cid)
    return cid


def case_summary(cid, sentences, n=1, built_at="2026-10-22T10:00:00"):
    st = store.get_state(cid)
    st.setdefault("artefacts", {})["case_summary"] = {"current": n, "case_id": cid, "versions": [
        {"n": n, "built_at": built_at, "review": {"status": "ai_draft"}, "edits": [],
         "sections": [{"id": "stage", "sentences": []}, {"id": "since", "title": "Treatment and follow-up since the board", "sentences": sentences}]}]}
    store.save_state(cid, st)


def index_keys():
    with np.load(similar._index_npz(), allow_pickle=False) as z:
        return [str(k) for k in z["keys"]]


def index_ids():
    return {c["case_id"] for c in json.loads(similar._index_json().read_text())["chunks"]}


# ---- 1. the profile --------------------------------------------------------------------------------------------------------------

def test_profile_fields_filled_from_the_records():
    cid = mk("TB-SIM-001", agesex="54 Y / F")
    dis = make_doc("DSIM00104", "discharge_summary", date="2026-10-20", title="DISCHARGE SUMMARY",
                   facts={"treatment_received": fact("Wide local excision", quote="Wide local excision done")})
    breast_docs(cid, extra=[dis])
    record(cid)
    case_summary(cid, [
        {"id": "ssince-1", "text": "The discharge summary records a wide local excision.",
         "citations": [{"doc_id": "DSIM00104", "quote": "Wide local excision done", "doc_title": "DISCHARGE SUMMARY", "date": "2026-10-20"}]},
        {"id": "ssince-2", "text": "Nothing documented since the board.", "citations": [], "code": True, "fixed": True}])
    p = similar.build_profile(cid)
    assert p["version"] == similar.VERSION and len(p["signature"]) == 16 and p["group"] == "breast" and p["group_label"] == "Breast cancer"
    assert p["cancer"] == "Breast cancer" and p["age_band"] == "50 to 59" and p["sex"] == "F"
    assert [(e["fact"], e["value"]) for e in p["histology"]] == [("histologic_type", "Invasive ductal carcinoma"), ("grade", "Grade 2")]
    er = next(e for e in p["biomarkers"] if e["fact"] == "er")
    assert er["quote"] == "ER: Positive (Allred 8/8)" and er["doc_title"] == "IHC REPORT" and er["month"] == "Sep 2026" and er["date"] == "2026-09-04"
    assert er["label"] == "Estrogen receptor (ER)" and er["confirmed"] is False and er["page"] == 0
    assert p["stage"][0] == {**p["stage"][0], "text": "cT2 N0 M0", "kind": "recorded", "label": "as recorded",
                             "quote": "Impression: stage as recorded cT2 N0 M0", "doc_title": "CT THORAX REPORT"}
    assert [s["kind"] for s in p["stage"]] == ["recorded", "agreed"] and p["stage"][1]["label"] == "as agreed by the board"
    d = p["decisions"][0]
    assert d["when"] == "Sep 2026" and d["outcome"] == "decision" and d["outcome_label"] == "Decision recorded"
    assert d["intent_label"] == "Curative" and d["modalities"] == ["Surgery", "Chemotherapy"] and d["text"].startswith("Breast conserving surgery")
    assert [t["value"] for t in p["treatments"]] == ["Wide local excision"]
    os_ = p["outcome_so_far"]
    assert os_["sentences"] == [{"text": "The discharge summary records a wide local excision.", "where": "DISCHARGE SUMMARY, Oct 2026",
                                 "source": {"sentence": "ssince-1", "section": "since"}}]
    assert os_["later_records"] == "1 record dated after the last board decision; latest Oct 2026"
    er_line = next(l for l in p["lines"] if l.get("fact") == "er")
    assert er_line["text"] == "ER: Positive (Allred 8/8)" and er_line["where"] == "IHC REPORT, Sep 2026" and er_line["where_full"] == "IHC REPORT, 04/09/2026"
    assert er_line["source"] == {"doc_id": "D00102", "page": 0, "start": 0, "end": len("ER: Positive (Allred 8/8)")}
    kinds = [l["kind"] for l in p["lines"]]
    assert kinds.index("fact") < kinds.index("stage") < kinds.index("summary") < kinds.index("decision")
    assert all(k == "decision" for k in kinds[kinds.index("decision"):]) and len(p["lines"]) <= similar.MAX_LINES
    assert [l["id"] for l in p["lines"]] == [f"L{i}" for i in range(1, len(p["lines"]) + 1)]
    assert p["text"].startswith("Cancer group: Breast cancer. Setting: ") and "Age band 50 to 59. Sex F." in p["text"]
    assert "ER: Positive (Allred 8/8)" in p["text"] and "Board decisions: decision recorded, intent curative" in p["text"]
    assert "Asha" not in json.dumps(p) and "SYN-7" not in json.dumps(p)


def test_unverified_fact_absent_and_confirmed_value_kept_without_a_line():
    cid = mk("TB-SIM-002")
    add(cid, make_doc("DSIM00201", "ihc", date="2026-09-04", title="IHC REPORT",
                      facts={"her2": fact("Positive", verification="unverified", quote="HER2: Positive"),
                             "pr": {"value": "Negative", "quote": "", "location": None, "verification": "confirmed", "state": "present",
                                    "confirmed_by": "dr.rao", "polarity": "affirmed"},
                             "ki67": fact("20%", state="pending", quote="Ki-67: 20%")}))
    record(cid)
    p = similar.build_profile(cid)
    facts = {e["fact"]: e for e in p["biomarkers"]}
    assert "her2" not in facts and "ki67" not in facts
    assert facts["pr"]["confirmed"] is True and facts["pr"]["quote"] == "" and facts["pr"]["value"] == "Negative" and facts["pr"]["confirmed_by"]
    assert not any(l.get("fact") in ("pr", "her2") for l in p["lines"])


def test_no_stage_and_unparseable_agesex():
    cid = mk("TB-SIM-003", agesex="not stated")
    add(cid, make_doc("DSIM00301", "histopathology", title="HISTOPATHOLOGY REPORT",
                      facts={"histologic_type": fact("Invasive lobular carcinoma", quote="Diagnosis: Invasive lobular carcinoma")}))
    record(cid, stage_as_agreed="")
    p = similar.build_profile(cid)
    assert p["stage"] == [] and p["age_band"] == "" and p["sex"] == ""
    assert similar.age_band("95 Y / M") == ("90 or older", "M") and similar.age_band("") == ("", "")


def test_identifiers_are_scrubbed_from_every_text():
    name, uhid, long_no = "Lakshmi Narayanan Iyer", "VXH/2026/004512", "98765432101"
    cid = mk("TB-SIM-004", name=f"SYNTHETIC, {name}", uhid=uhid)
    c = store.get_case(cid); c["his"] = {"uhid": uhid}; store.save_case(c)
    add(cid, make_doc("DSIM00401", "histopathology", title="HISTOPATHOLOGY REPORT",
                      facts={"histologic_type": fact("Invasive ductal carcinoma", quote=f"Patient lakshmi IYER ({uhid}) Diagnosis: Invasive ductal carcinoma"),
                             "grade": fact("Grade 3", quote=f"Lab no {long_no} Grade 3 seen on 12/09/2026")}))
    long_text = (f"Discussed for Lakshmi Narayanan, UHID {uhid}, ref {long_no}. " + "Neoadjuvant chemotherapy then surgery. " * 40)
    for k in range(6):
        record(cid, text=long_text, rationale=f"NARAYANAN has node positive disease, {uhid}", board_date=f"2026-09-1{k}")
    p = similar.build_profile(cid)
    assert p["text_decisions"], "the decisions go to a second chunk when the first is full"
    blobs = [p["text"], p["text_decisions"]] + [l["text"] for l in p["lines"]]
    for b in blobs:
        low = b.lower()
        for bad in ("lakshmi", "narayanan", "iyer", "004512", long_no, "12/09/2026"):
            assert bad not in low, (bad, b)
    assert "[id]" in p["text"] and "[id]" in p["text_decisions"] and "[date]" in " ".join(blobs)
    assert "lakshmi" not in json.dumps(p).lower() and uhid.lower() not in json.dumps(p).lower()
    assert similar.scrub("Seen by Dr Mehta for Lakshmi", store.get_case(cid)) == "Seen by Dr Mehta for [id]"


# ---- 2. the real case --------------------------------------------------------------------------------------------------------------

def test_a_protected_case_is_never_opened_profiled_indexed_or_listed(monkeypatch):
    monkeypatch.setattr(config, "PROTECTED_CASES", {"TB-REAL-1"})
    decided("TB-SIM-010")
    decided("TB-SIM-011")
    d = config.CASES_DIR / "TB-REAL-1"
    d.mkdir(parents=True)
    (d / "case.json").write_text(json.dumps({"case_id": "TB-REAL-1", "protocol": "breast", "patient": {"name": "X", "agesex": "50 Y / F"},
                                             "listing": {"status": "listed"}}))
    (d / "state.json").write_text("{ not json")  # a read would raise
    opened = []
    real_read = store._read_json
    monkeypatch.setattr(store, "_read_json", lambda p, default=None: opened.append(str(p)) or real_read(p, default))
    for fn in (similar.build_profile, similar.query_profile):
        with pytest.raises(ValueError, match="protected"):
            fn("TB-REAL-1")
    with pytest.raises(ValueError, match="protected"):
        similar.candidates("TB-REAL-1")
    out = similar.ensure()
    assert out["failed"] == 0 and out["built"] == 2
    assert not any("TB-REAL-1" in p for p in opened)
    assert "TB-REAL-1" not in index_ids() and not any(k.startswith("TB-REAL-1") for k in index_keys())
    assert not (similar._profiles_dir() / "TB-REAL-1.json").exists()
    res = similar.candidates("TB-SIM-010")
    assert [c["case_id"] for c in res["candidates"]] == ["TB-SIM-011"]
    assert not any("TB-REAL-1" in p for p in opened)


# ---- 3. eligibility and the index -------------------------------------------------------------------------------------------------

def test_only_listed_decided_unarchived_files_are_profiled_and_archive_removes():
    decided("TB-SIM-020")
    mk("TB-SIM-021"); breast_docs("TB-SIM-021")                                   # undecided
    mk("TB-SIM-022"); breast_docs("TB-SIM-022"); record("TB-SIM-022", outcome="deferred")  # deferred only
    mk("TB-SIM-023", listed=False); breast_docs("TB-SIM-023"); record("TB-SIM-023")  # not listed
    mk("TB-SIM-024", protocol="generic"); record("TB-SIM-024")                    # no cancer name: no group
    decided("TB-SIM-025")
    out = similar.ensure()
    assert out["built"] == 2 and out["scanned"] == 6
    assert index_ids() == {"TB-SIM-020", "TB-SIM-025"}
    c = store.get_case("TB-SIM-025"); c["archived"] = {"by": "test", "at": "2026-10-27T10:00:00", "reason": "test"}; store.save_case(c)
    out = similar.ensure()
    assert out["removed"] == 1 and index_ids() == {"TB-SIM-020"} and not (similar._profiles_dir() / "TB-SIM-025.json").exists()
    store.delete_case("TB-SIM-020")
    assert similar.ensure()["removed"] == 1 and index_ids() == set()


def test_a_file_decided_through_record_decision_is_profiled(unit_case, monkeypatch):
    from tumour_board import llm

    async def chat(role, msgs, **kw):
        return {"claims": []}
    monkeypatch.setattr(llm, "chat", chat)
    add(unit_case, make_doc("DUNIT0001", "histopathology", title="HISTOPATHOLOGY REPORT",
                            facts={"histologic_type": fact("Adenocarcinoma", quote="Diagnosis: Adenocarcinoma")}))
    asyncio.run(postboard.record_decision(unit_case, {"outcome": "decision", "decision_text": "Upfront surgery, then adjuvant chemotherapy.",
                                                      "intent": "curative", "board_date": "2026-09-10", "stage_as_agreed": "cT2 N1 M0",
                                                      "stage_source": "board"}, "anil"))
    assert similar.ensure()["built"] == 1
    p = json.loads((similar._profiles_dir() / "TB-UNIT.json").read_text())
    assert p["group"] == "unit" and p["group_label"] == "Unit test protocol" and p["age_band"] == "60 to 69" and p["sex"] == "M"
    assert p["decisions"][0]["outcome_label"] == "Decision recorded" and p["decisions"][0]["when"] == "Sep 2026"


def test_forget_removes_at_once_without_embedding(fake_embed):
    decided("TB-SIM-030"); decided("TB-SIM-031")
    similar.ensure()
    n = len(embedded(fake_embed))
    similar.forget("TB-SIM-031")
    assert len(embedded(fake_embed)) == n
    assert index_ids() == {"TB-SIM-030"} and index_keys() == ["TB-SIM-030|main"]
    assert not (similar._profiles_dir() / "TB-SIM-031.json").exists()
    meta, m = similar.load_index()
    assert m.shape[0] == len(meta["chunks"]) == 1 and abs(float(np.linalg.norm(m[0])) - 1.0) < 1e-5
    similar.forget("TB-NONE")  # a missing profile is fine


def test_the_index_write_is_atomic():
    decided("TB-SIM-040")
    similar.DIR().mkdir(parents=True)
    (similar.DIR() / "index.npz.tmp").write_bytes(b"stale half write")
    similar.ensure()
    assert not list(similar.DIR().rglob("*.tmp"))
    meta, m = similar.load_index()
    assert [c["case_id"] for c in meta["chunks"]] == ["TB-SIM-040"] and m.shape == (1, DIM)
    assert meta["version"] == similar.VERSION and meta["embed_model"] == search.EMBED_MODEL and len(meta["signature"]) == 16


def test_a_changed_decision_rebuilds_only_that_profile_and_the_cache_is_reused(fake_embed):
    decided("TB-SIM-050", agesex="44 Y / F"); decided("TB-SIM-051", agesex="54 Y / F"); decided("TB-SIM-052", agesex="64 Y / F")
    first = similar.ensure()
    assert first["built"] == 3 and first["embedded"] == 3 and len(embedded(fake_embed)) == 3
    again = similar.ensure()
    assert again == {**again, "built": 0, "unchanged": 3, "embedded": 0, "removed": 0} and len(embedded(fake_embed)) == 3
    st = store.get_case("TB-SIM-051") and store.get_state("TB-SIM-051")
    before = similar.signature(store.get_case("TB-SIM-051"), st)
    st["board_records"][0].update(decision_text="Neoadjuvant chemotherapy, then surgery.", version=2)
    store.save_state("TB-SIM-051", st)
    assert similar.signature(store.get_case("TB-SIM-051"), store.get_state("TB-SIM-051")) != before
    old = {c: json.loads((similar._profiles_dir() / f"{c}.json").read_text())["built_at"] for c in ("TB-SIM-050", "TB-SIM-052")}
    out = similar.ensure()
    assert out["built"] == 1 and out["unchanged"] == 2 and out["embedded"] == 1
    new_texts = embedded(fake_embed)[3:]
    assert len(new_texts) == 1 and "Neoadjuvant chemotherapy" in new_texts[0]
    assert {c: json.loads((similar._profiles_dir() / f"{c}.json").read_text())["built_at"] for c in old} == old
    cache = config.DATA_ROOT / "embed_cache" / "chunks"
    assert len(list(cache.glob("*.npy"))) == 4
    # a fresh index from the same profiles embeds nothing: every chunk comes from the content cache
    assert similar.ensure(force=True)["embedded"] == 0


def test_a_summary_edit_or_stage_confirmation_changes_the_signature():
    cid = decided("TB-SIM-060")
    s0 = similar.signature(store.get_case(cid), store.get_state(cid))
    case_summary(cid, [{"id": "ssince-1", "text": "Surgery done.", "citations": []}])
    s1 = similar.signature(store.get_case(cid), store.get_state(cid))
    st = store.get_state(cid)
    st["staging"] = {"status": "staged", "stage": "IIA", "components": {"T": {"cat": "T2"}, "N": {"cat": "N0"}, "M": {"cat": "M0"}},
                     "confirmed": {"by": "dr.rao", "by_name": "Dr Rao", "at": "2026-10-01T10:00:00"}}
    store.save_state(cid, st)
    s2 = similar.signature(store.get_case(cid), store.get_state(cid))
    assert len({s0, s1, s2}) == 3
    p = similar.build_profile(cid)
    draft = next(s for s in p["stage"] if s["kind"] == "confirmed_draft")
    assert draft["text"] == "T2 N0 M0, stage IIA" and draft["label"] == "Vaidyx draft stage, confirmed by Dr Rao" and draft["month"] == "Oct 2026"


# ---- 4. the candidates -----------------------------------------------------------------------------------------------------------

def test_group_filter_colon_and_rectum_share_generic_by_name():
    for cid, prot, name in (("TB-SIM-070", "breast", None), ("TB-SIM-071", "breast", None), ("TB-SIM-072", "colorectal_colon", None),
                            ("TB-SIM-073", "colorectal_rectum", None), ("TB-SIM-074", "generic", "Neuroendocrine Tumour."),
                            ("TB-SIM-075", "generic", "neuroendocrine   tumour"), ("TB-SIM-076", "generic", "Thymoma"),
                            ("TB-SIM-077", "generic_haem", "Neuroendocrine tumour, (typed)")):
        mk(cid, protocol=prot, cancer_name=name)
        record(cid)
    assert similar.group(store.get_case("TB-SIM-074")) == "name:neuroendocrine tumour"
    assert similar.group_label(store.get_case("TB-SIM-072")) == "Colorectal cancer"
    assert similar.group_label(store.get_case("TB-SIM-074")) == "Neuroendocrine Tumour."
    got = {c: [x["case_id"] for x in similar.candidates(c)["candidates"]] for c in ("TB-SIM-070", "TB-SIM-072", "TB-SIM-074", "TB-SIM-076")}
    assert got == {"TB-SIM-070": ["TB-SIM-071"], "TB-SIM-072": ["TB-SIM-073"], "TB-SIM-074": ["TB-SIM-075"], "TB-SIM-076": []}
    r = similar.candidates("TB-SIM-070")
    assert r["group"] == "breast" and r["group_label"] == "Breast cancer" and r["n_in_group"] == 1
    assert r["note"] == "Only 1 past Case File of this cancer group has a recorded decision."
    assert similar.candidates("TB-SIM-076")["note"] == "No past Case File of this cancer group has a recorded decision."
    mk("TB-SIM-078", protocol="generic")
    assert similar.candidates("TB-SIM-078") == {"group": None, "group_label": "", "candidates": [], "n_in_group": 0, "note": "No cancer group on this file."}


def test_the_source_the_same_patient_and_linked_files_are_excluded():
    mk("TB-SIM-080", uhid="VXH/2026/000801", linked=["TB-SIM-083"])
    record("TB-SIM-080")
    decided("TB-SIM-081")
    decided("TB-SIM-082", uhid="VXH/2026/000801", name="SYNTHETIC, Other Name")     # the same patient (UHID in common)
    decided("TB-SIM-083")                                                            # linked from the source
    decided("TB-SIM-084", linked=["TB-SIM-080"])                                     # links back to the source
    decided("TB-SIM-085")
    r = similar.candidates("TB-SIM-080")
    assert sorted(c["case_id"] for c in r["candidates"]) == ["TB-SIM-081", "TB-SIM-085"]
    assert r["note"] == "Only 2 past Case Files of this cancer group have a recorded decision."
    assert [c["rrf_rank"] for c in r["candidates"]] == [1, 2]


def test_an_undecided_source_gets_a_transient_profile_and_is_never_stored():
    mk("TB-SIM-090"); breast_docs("TB-SIM-090")
    for c in ("TB-SIM-091", "TB-SIM-092", "TB-SIM-093"):
        decided(c)
    r = similar.candidates("TB-SIM-090")
    assert len(r["candidates"]) == 3 and r["note"] == "" and r["n_in_group"] == 3
    assert not (similar._profiles_dir() / "TB-SIM-090.json").exists()
    assert similar.query_profile("TB-SIM-090")["outcome_so_far"]["later_records"] == "No board decision recorded yet"


def test_the_doctors_words_raise_a_profile_quoting_them():
    mk("TB-SIM-100"); breast_docs("TB-SIM-100")
    mk("TB-SIM-101"); breast_docs("TB-SIM-101", her2="positive", distant="brain metastases"); record("TB-SIM-101")
    mk("TB-SIM-102"); breast_docs("TB-SIM-102", her2="negative"); record("TB-SIM-102")
    mk("TB-SIM-103"); breast_docs("TB-SIM-103", her2="negative"); record("TB-SIM-103")
    r = similar.candidates("TB-SIM-100", words="HER2 positive with brain metastases")
    ids = [c["case_id"] for c in r["candidates"]]
    assert ids[0] == "TB-SIM-101" and set(ids) == {"TB-SIM-101", "TB-SIM-102", "TB-SIM-103"}


def test_words_with_the_patients_name_or_uhid_are_refused():
    mk("TB-SIM-110", name="SYNTHETIC, Radhika Menon", uhid="VXH/2026/001101"); record("TB-SIM-110")
    for w in ("radhika with brain metastases", "VXH/2026/001101 HER2", "lab number 1234567"):
        with pytest.raises(published.PublishedError):
            similar.candidates("TB-SIM-110", words=w)


# ---- 5. the scheduler and the import guard -----------------------------------------------------------------------------------------

def test_the_scheduler_job(monkeypatch, tmp_path):
    names = [j[0] for j in scheduler.JOBS]
    assert "similar" in names and "similar" not in scheduler.QUICK
    job = next(j for j in scheduler.JOBS if j[0] == "similar")
    assert job[2] == 1800 and job[1] is scheduler.similar_job
    monkeypatch.setattr(config, "CASES_DIR", tmp_path / "missing")
    out = scheduler.similar_job(None)
    assert "error" not in out and out["scanned"] == 0

    def boom(force=False):
        raise RuntimeError("disk full")
    monkeypatch.setattr(similar, "ensure", boom)
    assert scheduler.similar_job(None) == {"error": "RuntimeError: disk full"}


def test_no_agent_or_summary_module_imports_similar():
    root = Path(similar.__file__).resolve().parent
    rx = re.compile(r"^\s*(from\s+[.\w]*\s+import\s+[^#\n]*\bsimilar\b|import\s+[.\w]*similar\b|from\s+[.\w]*similar\s+import)", re.M)
    for f in ("agents.py", "helpers.py", "summary.py", "case_summary.py", "postboard.py", "guardrails.py"):
        p = root / f
        if p.exists():
            assert not rx.search(p.read_text()), f


def test_no_em_dash_or_advice_word_in_the_module_strings():
    src = Path(similar.__file__).read_text()
    assert chr(0x2014) not in src and chr(0x2013) not in src
    for s in (similar.LABEL, similar.NO_GROUP, similar.NO_RECORDS_AFTER, similar.NO_DECISION_YET):
        assert not re.search(r"\b(consider|suggest|recommend|do the same|treat as|follow|best match)\b", s, re.I)
