#!/bin/bash
mkdir -p /tmp/vaidyx-tmux 2>/dev/null || true
exec 3>&1 4>&2
exec > >(tee -a /tmp/vaidyx-tmux/serve-c3224225.log) 2>&1
VAIDYX_USER_SHELL="${SHELL:-}"
if [ -n "$VAIDYX_USER_SHELL" ] && [ -x "$VAIDYX_USER_SHELL" ]; then
  VAIDYX_USER_PATH="$("$VAIDYX_USER_SHELL" -ic 'printf "__VAIDYX_PATH__%s\n" "$PATH"' 2>/dev/null | sed -n 's/^__VAIDYX_PATH__//p' | tail -n 1 || true)"
  if [ -n "$VAIDYX_USER_PATH" ]; then export PATH="$VAIDYX_USER_PATH:$PATH"; fi
fi
_odys_py3="$(command -v python3 2>/dev/null || true)"
case "$_odys_py3" in ""|*[Ww]indows[Aa]pps*) python3() { python "$@"; } ;; esac
command -v python >/dev/null 2>&1 || python() { python3 "$@"; }
VAIDYX_PREFLIGHT_EXIT=""
export PATH="/usr/bin:$PATH"
export FLASHINFER_DISABLE_VERSION_CHECK=1
export CUDA_VISIBLE_DEVICES='0'
deactivate 2>/dev/null; hash -r
_ODY_VENV_FOR_LIBS="${VIRTUAL_ENV:-}"
if [ -n "$_ODY_VENV_FOR_LIBS" ] && [ -d "$_ODY_VENV_FOR_LIBS" ]; then
  for _ody_nvlib in "$_ODY_VENV_FOR_LIBS"/lib/python*/site-packages/nvidia/cu13/lib "$_ODY_VENV_FOR_LIBS"/lib/python*/site-packages/nvidia/cu12/lib "$_ODY_VENV_FOR_LIBS"/lib/python*/site-packages/nvidia/cuda_nvrtc/lib "$_ODY_VENV_FOR_LIBS"/lib/python*/site-packages/nvidia/cuda_runtime/lib "$_ODY_VENV_FOR_LIBS"/lib/python*/site-packages/nvidia/cublas/lib "$_ODY_VENV_FOR_LIBS"/lib/python*/site-packages/nvidia/cudnn/lib; do
    [ -d "$_ody_nvlib" ] && export LD_LIBRARY_PATH="$_ody_nvlib:${LD_LIBRARY_PATH:-}"
  done
fi
VAIDYX_SERVE_PORT='8000'
VAIDYX_EXPECTED_MODEL='google/medgemma-27b-text-it'
if [ -n "$VAIDYX_SERVE_PORT" ]; then
  python3 - "$VAIDYX_SERVE_PORT" "$VAIDYX_EXPECTED_MODEL" <<'PY'
import json, sys, urllib.request
port = sys.argv[1]
expected = (sys.argv[2] or '').strip()
url = f'http://127.0.0.1:{port}/v1/models'
try:
    with urllib.request.urlopen(url, timeout=1.5) as r:
        data = json.loads(r.read().decode('utf-8', 'replace') or '{}')
except Exception:
    raise SystemExit(0)
models = [str(x.get('id') or '') for x in data.get('data', []) if isinstance(x, dict)]
def base(s): return s.lower().split('/')[-1]
match = bool(expected) and any((m.lower() == expected.lower() or base(m) == base(expected) or base(expected) in m.lower() or base(m) in expected.lower()) for m in models)
print(f'ERROR: Port {port} is already serving {models or ["unknown"]}.')
if expected and not match:
    print(f'ERROR: Cookbook was about to launch {expected}, but this port is occupied by a different model. Stop the old server or choose another port.')
else:
    print('ERROR: Stop the existing server or choose another port before launching a duplicate serve.')
raise SystemExit(98)
PY
  _ody_port_ec=$?
  if [ "$_ody_port_ec" -ne 0 ]; then VAIDYX_PREFLIGHT_EXIT="$_ody_port_ec"; fi
fi
if [ -n "$HF_TOKEN" ]; then echo "[vaidyx] HF token: applied"; else echo "[vaidyx] HF token: NOT SET — gated/private models will be denied. Add one in Vaidyx Cookbook -> Settings -> HuggingFace Token."; fi
if [ "$(uname -s)" = "Darwin" ]; then
  echo "ERROR: vLLM does not run on macOS. Use Ollama or llama.cpp (Metal) instead."
  VAIDYX_PREFLIGHT_EXIT=1
fi
export PATH="$HOME/.local/bin:$PATH"
if ! command -v vllm &>/dev/null; then
  echo "ERROR: vLLM is not installed."
  VAIDYX_PREFLIGHT_EXIT=127
fi
VAIDYX_SERVE_CMD='CUDA_VISIBLE_DEVICES=0 vllm serve google/medgemma-27b-text-it --host 0.0.0.0 --port 8000 --tensor-parallel-size 1 --max-model-len 20000 --gpu-memory-utilization 0.90 --dtype auto --max-num-seqs 4'
if [ -z "$VAIDYX_PREFLIGHT_EXIT" ]; then
  VAIDYX_VLLM_HELP_CMD="$(python3 - "$VAIDYX_SERVE_CMD" <<'PY'
import shlex, sys
parts = shlex.split(sys.argv[1])
try:
    serve_i = parts.index("serve")
except ValueError:
    print("vllm serve --help")
else:
    print(shlex.join(parts[:serve_i + 1] + ["--help"]))
PY
)"
  VAIDYX_VLLM_SUPPORTS_SWAP=0
  if eval "$VAIDYX_VLLM_HELP_CMD" 2>&1 | grep -q -- "--swap-space"; then VAIDYX_VLLM_SUPPORTS_SWAP=1; fi
fi
if [ -z "$VAIDYX_PREFLIGHT_EXIT" ] && [ "${VAIDYX_VLLM_SUPPORTS_SWAP:-0}" = "1" ] && ! printf "%s" "$VAIDYX_SERVE_CMD" | grep -q -- "--swap-space"; then
  echo "[vaidyx] Setting vLLM --swap-space 0 so the runtime does not reserve CPU swap per GPU."
  VAIDYX_SERVE_CMD="${VAIDYX_SERVE_CMD} --swap-space 0"
fi
if [ -z "$VAIDYX_PREFLIGHT_EXIT" ] && [ "${VAIDYX_VLLM_SUPPORTS_SWAP:-0}" != "1" ]; then
  if printf "%s" "$VAIDYX_SERVE_CMD" | grep -q -- "--swap-space"; then
    echo "[vaidyx] vLLM serve does not expose --swap-space; removing the flag and patching the runtime default to 0."
    VAIDYX_SERVE_CMD="$(python3 - "$VAIDYX_SERVE_CMD" <<'PY'
import shlex, sys
parts = shlex.split(sys.argv[1])
out = []
skip = False
for part in parts:
    if skip:
        skip = False
        continue
    if part == "--swap-space":
        skip = True
        continue
    if part.startswith("--swap-space="):
        continue
    out.append(part)
print(shlex.join(out))
PY
)"
  fi
  VAIDYX_SERVE_CMD="$(python3 - "$VAIDYX_SERVE_CMD" <<'PY'
import shlex, sys
parts = shlex.split(sys.argv[1])
patch = r"""import inspect, sys
from vllm.engine.arg_utils import EngineArgs, AsyncEngineArgs
def _vaidyx_swap0(cls):
    params = list(inspect.signature(cls).parameters)
    if "swap_space" not in params:
        return
    idx = params.index("swap_space")
    defaults = list(cls.__init__.__defaults__ or ())
    if idx < len(defaults):
        defaults[idx] = 0
        cls.__init__.__defaults__ = tuple(defaults)
    fields = getattr(cls, "__dataclass_fields__", {})
    if "swap_space" in fields:
        fields["swap_space"].default = 0
_vaidyx_swap0(EngineArgs)
_vaidyx_swap0(AsyncEngineArgs)
try:
    from vllm.config import CacheConfig
    CacheConfig.swap_space = 0
except Exception:
    pass
_orig_create_engine_config = EngineArgs.create_engine_config
def _vaidyx_create_engine_config(self, *args, **kwargs):
    self.swap_space = 0
    return _orig_create_engine_config(self, *args, **kwargs)
EngineArgs.create_engine_config = _vaidyx_create_engine_config
AsyncEngineArgs.create_engine_config = _vaidyx_create_engine_config
from vllm.entrypoints.cli.main import main
sys.exit(main())"""
try:
    serve_i = parts.index("serve")
except ValueError:
    print(shlex.join(parts))
else:
    exe_i = serve_i - 1
    exe = parts[exe_i] if exe_i >= 0 else "vllm"
    py = "python3"
    if exe.endswith("/bin/vllm"):
        py = exe[:-len("/bin/vllm")] + "/bin/python"
    parts[exe_i:serve_i] = [py, "-c", patch]
    print(shlex.join(parts))
PY
)"
  echo "[vaidyx] Patched vLLM internal swap_space default to 0 for this runtime."
fi
if [ -n "$VAIDYX_PREFLIGHT_EXIT" ]; then
  echo ""; echo "=== Process exited with code $VAIDYX_PREFLIGHT_EXIT ==="
  exec 1>&3 2>&4 3>&- 4>&- 2>/dev/null || true
  sleep 0.2  # let tee child flush + exit
  exec "${SHELL:-/bin/bash}"
fi
eval "$VAIDYX_SERVE_CMD"
VAIDYX_CMD_EXIT=$?
echo ""; echo "=== Process exited with code $VAIDYX_CMD_EXIT ==="
exec 1>&3 2>&4 3>&- 4>&- 2>/dev/null || true
sleep 0.2  # let tee child flush + exit
exec "${SHELL:-/bin/bash}"
