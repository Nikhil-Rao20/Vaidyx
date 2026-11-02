"""The voice check's scoring (night-v3 item 4.5, tumour_board/eval/audio_eval.py): word error rate, the normalised equality rules,
the exact-token score, the WAV builders and the summary line. No network, no service, no GPU. Synthetic text only."""
import io
import json
import wave

import pytest

from tumour_board.eval import audio_eval as ae


# ----------------------------------------------------------------------------------------------------- word error rate

def test_edit_distance_and_wer_known_pairs():
    assert ae.edit_distance(["a", "b", "c"], ["a", "b", "c"]) == 0
    assert ae.edit_distance(["a", "b", "c"], ["a", "x", "c"]) == 1  # one substitution
    assert ae.edit_distance(["a", "b", "c"], ["a", "c"]) == 1  # one deletion
    assert ae.edit_distance(["a", "b"], ["a", "b", "c", "d"]) == 2  # two insertions
    assert ae.edit_distance([], ["a"]) == 1
    assert ae.wer(["one", "two", "three", "four"], ["one", "too", "three", "four"]) == pytest.approx(0.25)
    assert ae.wer([], []) == 0.0
    assert ae.wer([], ["noise"]) == 1.0
    assert ae.wer(["a"], []) == 1.0


def test_strict_words_lower_case_and_punctuation_removed():
    assert ae.strict_words("HPE dated 14/09/2026 shows, grade 2.") == ["hpe", "dated", "14/09/2026", "shows", "grade", "2"]
    assert ae.strict_words("Haemoglobin 11.8 g/dL, platelets 245,000.") == ["haemoglobin", "11.8", "g/dl", "platelets", "245,000"]
    assert ae.strict_words("Ki-67 30%") == ["ki", "67", "30%"]
    # strict keeps conventions apart: a date written another way is an error here
    s = ae.strict_words("The board meets on 28/10/2026.")
    h = ae.strict_words("The board meets on 28th of October, 2026.")
    assert ae.wer(s, h) > 0


# ---------------------------------------------------------------------------------------------- the normalised rules

@pytest.mark.parametrize("said,heard", [
    ("Haemoglobin 11.8 g/dL, platelets 245,000 per microlitre.", "hemoglobin 11.8 grams per deciliter, platelets 245 thousand per microliter"),
    ("Haemoglobin 9.6 g/dL", "Haemoglobin 9.6 g per deciliter"),
    ("platelets 1,80,000.", "platelets 1 lakh 80,000"),
    ("platelets 1,80,000.", "platelets 180000"),
    ("MRI pelvis gives the stage as mrT3b N1.", "MRI pelvis gives the stage as MRT3BN1"),
    ("cT3 N2 M0", "c T3 N2 M0"),
    ("ypT2 N0", "ypT2-N0"),
    ("The board meets on 28/10/2026.", "The board meets on 28th of October, 2026."),
    ("due by 04/11/2026", "due by 4-11-2026"),
    ("on 04/11/2026", "on fourth of november twenty twenty-six"),
    ("on 16/10/2026", "on October 16, 2026"),
    ("PM-JAY, Ki-67 30%", "PM JAY, Ki67 30 percent"),
    ("ER positive, PR positive", "ER-positive, PR-positive"),
    ("ECOG 1 versus ECOG 2", "ECOG1 vs ECOG 2"),
    ("Dr Kavita", "Doctor Kavita"),
    ("size 3.2 by 2.1 cm", "size 3.2 x 2.1 centimetres"),
    ("for four cycles", "for 4 cycles"),
    ("Pre-Authorization under PM-JAY", "Preauthorization under PM-JAY"),
])
def test_normalised_equal(said, heard):
    assert ae.normalised_words(said) == ae.normalised_words(heard)


def test_normalised_still_counts_real_errors():
    assert ae.normalised_words("Referral from Guwahati") != ae.normalised_words("Referral from Gao Hadi")
    assert ae.normalised_words("platelets 1,80,000") != ae.normalised_words("platelets 1-lock 80,000")
    assert ae.normalised_words("cT4 N3 M1a") != ae.normalised_words("cT4 N3, M1")
    assert ae.normalised_words("Ki-67") != ae.normalised_words("CHI67")  # "PMJ" is reshaped to PM-JAY by the service clean-up since the check
    assert ae.normalised_words("on 01/08/2026") != ae.normalised_words("on 108, 2026")


def test_sentence_accept_pairs():
    assert ae.normalised_words("SUVmax 8.4") != ae.normalised_words("SUV max 8.4")
    assert ae.normalised_words("SUVmax 8.4", [["SUVmax", "SUV max"]]) == ae.normalised_words("SUV max 8.4", [["SUVmax", "SUV max"]])
    assert ae.normalised_words("HER2 3+", [["3+", "3 plus"]]) == ae.normalised_words("HER2 3 plus", [["3+", "3 plus"]])


# ------------------------------------------------------------------------------------------------------ exact tokens

def test_exact_tokens_case_hyphens_and_spaces_ignored():
    heard = "SUVmax 8.4, 11.8 g/dL, mrT3bN1, 30 %, PDL1, er-POSITIVE"
    found, total, missing = ae.exact_tokens(["11.8 g/dL", "mrT3b N1", "30%", "PD-L1", "ER positive"], heard)
    assert (found, total, missing) == (5, 5, [])


def test_exact_tokens_are_whole():
    assert ae.exact_tokens(["8"], "SUVmax 8.4 and 18 nodes")[2] == ["8"]  # not inside 8.4 or 18
    assert ae.exact_tokens(["8"], "Allred score 8 out of 8.")[0] == 1  # at a sentence end it counts
    assert ae.exact_tokens(["11.8"], "value 211.8")[0] == 0
    assert ae.exact_tokens(["1.8"], "value 11.8")[0] == 0
    assert ae.exact_tokens(["245,000"], "platelets 245000")[0] == 0  # exact: the digit grouping is part of the token
    assert ae.exact_tokens(["14/09/2026"], "on 14th of September, 2026")[0] == 0
    assert ae.exact_tokens([], "anything") == (0, 0, [])


def test_exact_tokens_any_form_tells_a_format_from_a_wrong_value():
    assert ae.exact_tokens(["14/09/2026"], "on 14th of September, 2026", any_form=True)[0] == 1
    assert ae.exact_tokens(["11.8 g/dL"], "11.8 g per deciliter", any_form=True)[0] == 1
    assert ae.exact_tokens(["245,000"], "245 thousand", any_form=True)[0] == 1
    assert ae.exact_tokens(["01/08/2026"], "on 108, 2026", any_form=True)[0] == 0  # an ambiguous glued date is never reshaped
    assert ae.exact_tokens(["1,80,000"], "1-lock 80,000", any_form=True)[0] == 0


def test_score_row_and_aggregate():
    r = ae.score_row("HPE dated 14/09/2026 shows grade 2.", "HPE dated 14th of September, 2026 shows grade 2.", ["14/09/2026", "grade 2"])
    assert r["normalised_wer"] == 0.0 and r["strict_wer"] > 0
    assert (r["tokens_found"], r["tokens_total"], r["missing"], r["tokens_found_any_form"]) == (1, 2, ["14/09/2026"], 2)
    rows = [dict(r, heard="x", stt_ms=100), dict(ae.score_row("a b c d", "a b c d", ["a"]), heard="a b c d", stt_ms=300)]
    agg = ae.aggregate(rows)
    assert agg["n"] == 2
    assert agg["tokens_found"] == 2 and agg["tokens_total"] == 3
    assert agg["exact_tokens"] == pytest.approx(2 / 3, abs=1e-4)
    assert agg["strict_wer"] == pytest.approx(r["strict_edits"] / (r["strict_ref_words"] + 4), abs=1e-4)
    assert agg["stt_ms_p50"] == 200
    assert ae.aggregate([])["strict_wer"] is None


def test_percentile():
    assert ae.percentile([], 50) is None
    assert ae.percentile([5], 95) == 5
    assert ae.percentile([1, 2, 3, 4], 50) == 2.5
    assert ae.percentile(list(range(1, 101)), 95) == pytest.approx(95.05)
    assert ae.percentile([3, None, 1], 50) == 2


# ------------------------------------------------------------------------------------------------------------- audio

def _info(data):
    with wave.open(io.BytesIO(data), "rb") as w:
        return w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getnframes(), w.readframes(w.getnframes())


def test_silence_wav_length_and_format():
    data = ae.silence_wav(10.0)
    ch, width, rate, frames, pcm = _info(data)
    assert (ch, width, rate, frames) == (1, 2, 16000, 160000)
    assert set(pcm) == {0}
    assert ae.wav_seconds(data) == pytest.approx(10.0)
    assert len(data) == 44 + 320000


def test_noise_and_tone_wavs():
    n = ae.noise_wav(2.0, amplitude=3000, seed=1)
    assert ae.wav_seconds(n) == pytest.approx(2.0)
    assert ae.noise_wav(2.0, amplitude=3000, seed=1) == n  # seeded: the same clip each run
    assert len(set(_info(n)[4])) > 10
    t = ae.tone_wav(62.0)
    assert ae.wav_seconds(t) == pytest.approx(62.0)
    assert len(t) < 4 * 1024 * 1024  # under the body cap, so the refusal is the duration (413 too_long), not the size


# ------------------------------------------------------------------------------------------------- summary and checks

def test_summary_line_and_checks():
    agg = {"n": 46, "strict_wer": 0.0712, "normalised_wer": 0.032, "exact_tokens": 0.9512, "stt_ms_p50": 122.0}
    line = ae.summary_line(agg, True, 62.4)
    assert line == "AUDIO: strict WER 0.071, normalised 0.032, exact tokens 0.95, silence ok, 46 sentences, p50 stt 122 ms, p50 tts 62 ms"
    assert "silence FAILED" in ae.summary_line(agg, False, None)
    assert "p50 tts n/a ms" in ae.summary_line(agg, True, None)
    assert ae.summary_line({}, True, None).startswith("AUDIO: strict WER n/a, normalised n/a, exact tokens n/a")
    assert ae.checks(agg, True, True) == {"strict_wer": True, "exact_tokens": True, "silence_and_noise": True, "over_60_s_refused": True}
    bad = ae.checks({"strict_wer": 0.2, "exact_tokens": 0.5}, False, False)
    assert not any(bad.values())
    assert "\u2014" not in line


def test_sentence_file_is_synthetic_and_complete():
    data = json.loads(ae.SENTENCES.read_text(encoding="utf-8"))
    rows = data["sentences"]
    assert 38 <= len(rows) <= 50
    assert len({r["id"] for r in rows}) == len(rows)
    cats = {r["category"] for r in rows}
    assert {"histology", "lab", "staging", "dates", "receptors", "pre-authorization", "points-for-review", "questions",
            "agent-answer", "drugs", "places-names"} <= cats
    text = " ".join(r["text"] for r in rows)
    for word in ("capecitabine", "oxaliplatin", "trastuzumab", "pembrolizumab", "osimertinib", "letrozole", "tamoxifen", "paclitaxel",
                 "docetaxel", "carboplatin", "bevacizumab", "temozolomide", "imatinib", "Tata Memorial", "Kidwai Memorial", "Adyar",
                 "AIIMS", "PGIMER", "Thiruvananthapuram", "Visakhapatnam", "Bengaluru", "Guwahati", "Bhubaneswar", "Coimbatore",
                 "Kathua", "Rajouri", "Poonch", "Kavita", "Venkatesh", "Priya", "mrT3b N1", "cT3 N2 M0", "ypT2 N0", "PD-L1 TPS",
                 "PM-JAY", "Pre-Authorization", "Points for review", "which department should clear the fitness"):
        assert word.lower() in text.lower(), word
    assert "bharath" not in text.lower()
    assert "\u2014" not in json.dumps(data, ensure_ascii=False)
    for r in rows:  # every must_keep token is written in the sentence itself
        for tok in r["must_keep"]:
            assert ae.token_pattern(tok).search(r["text"]), (r["id"], tok)
        # the reference sentence scores perfectly against itself
        s = ae.score_row(r["text"], r["text"], r["must_keep"], r.get("accept"))
        assert s["strict_wer"] == 0 and s["normalised_wer"] == 0 and s["tokens_found"] == s["tokens_total"]


def test_token_is_read_from_the_config_file(tmp_path, monkeypatch):
    f = tmp_path / "audio_token.json"
    f.write_text(json.dumps({"token": "  t0k3n  "}))
    monkeypatch.setattr(ae.config, "AUDIO_TOKEN_FILE", str(f))
    assert ae.read_token() == "t0k3n"
    monkeypatch.setattr(ae.config, "AUDIO_TOKEN_FILE", str(tmp_path / "missing.json"))
    assert ae.read_token() == ""


def test_gate_summary_reads_the_voice_line(tmp_path, monkeypatch):
    from tumour_board.eval import gate_summary as gs
    run = tmp_path / "r1"
    run.mkdir()
    (run / "run_timings.txt").write_text("=== audio_eval finished rc=0 in 60 s\n")
    line = "AUDIO: strict WER 0.071, normalised 0.032, exact tokens 0.95, silence ok, 46 sentences, p50 stt 122 ms, p50 tts 62 ms"
    (run / "audio_eval_v2-r1.json").write_text(json.dumps({"summary": line, "checks": {"strict_wer": True, "exact_tokens": False}}))
    n = gs.numbers(run)
    assert n["audio_summary"] == line and n["audio_checks"] == {"strict_wer": True, "exact_tokens": False}
    monkeypatch.setattr(gs, "v9_in_corpus", lambda: [])
    gs.main("r1", "baseline", tmp_path)
    md = (run / "gate_summary.md").read_text()
    assert "Voice check (synthetic sentences, not an accuracy claim; not in the verdict): " + line in md
    assert "thresholds not met: exact_tokens" in md
    # a failed run without its JSON says so; no audio step at all leaves no line
    run2 = tmp_path / "r2"
    run2.mkdir()
    (run2 / "run_timings.txt").write_text("=== audio_eval finished rc=2 in 1 s\n")
    assert gs.numbers(run2)["audio_summary"].startswith("did not run (exit 2")
    run3 = tmp_path / "r3"
    run3.mkdir()
    assert "audio_summary" not in gs.numbers(run3)
