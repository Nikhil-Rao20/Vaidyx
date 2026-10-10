"""serve_models.sh: the reasoner's speculative decoding is on by default, not only when TB_SPEC is set by hand (V1 item 1.7)."""
import json, re, subprocess
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "serve_models.sh"


def _spec_default():
    m = re.search(r"SPEC=\$\{TB_SPEC-'(\{.*?\})'\}", SCRIPT.read_text())
    assert m, "the reasoner branch must default SPEC from TB_SPEC"
    return json.loads(m.group(1))


def test_default_speculative_config_is_ngram():
    d = _spec_default()
    assert d["method"] == "ngram" and d["num_speculative_tokens"] >= 1 and d["prompt_lookup_min"] <= d["prompt_lookup_max"]


def test_reasoner_command_uses_the_default_and_empty_tb_spec_turns_it_off():
    s = SCRIPT.read_text()
    assert '${SPEC:+--speculative-config "$SPEC"}' in s and '${TB_SPEC:+' not in s
    # the shell expansion itself: unset -> default JSON; empty -> no flag
    probe = 'SPEC=${TB_SPEC-\'{"method":"ngram"}\'}; echo "x${SPEC:+--speculative-config}"'
    assert subprocess.run(["bash", "-c", probe], capture_output=True, text=True, env={}).stdout.strip() == "x--speculative-config"
    assert subprocess.run(["bash", "-c", probe], capture_output=True, text=True, env={"TB_SPEC": ""}).stdout.strip() == "x"


def test_script_parses():
    assert subprocess.run(["bash", "-n", str(SCRIPT)]).returncode == 0
