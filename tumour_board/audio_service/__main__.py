"""Run the audio service: python -m tumour_board.audio_service [--host 127.0.0.1] [--port 7120] [--warm]
[--device auto|cuda|cpu] [--token-file PATH]. Binds to the loopback address only; never tunnelled."""
import os

os.environ["HF_HUB_OFFLINE"] = "1"        # before any engine import: models come from the local cache only
os.environ["TRANSFORMERS_OFFLINE"] = "1"

import argparse  # noqa: E402
import json  # noqa: E402
import logging  # noqa: E402
import sys  # noqa: E402
from pathlib import Path  # noqa: E402

DEFAULT_TOKEN_FILE = Path(__file__).resolve().parents[2] / "data" / "tumour_board" / "audio_token.json"
LOOPBACK = ("127.0.0.1", "localhost", "::1")


def read_token(path: str) -> str | None:
    """The shared token from {"token": "..."}; None when the file is missing, unreadable or too short."""
    try:
        with open(path, encoding="utf-8") as f:
            tok = json.load(f).get("token")
    except Exception:
        return None
    return tok if isinstance(tok, str) and len(tok) >= 16 else None


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="python -m tumour_board.audio_service", description="Vaidyx-TB audio service")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=7120)
    p.add_argument("--warm", action="store_true", help="load the engines at start")
    p.add_argument("--device", choices=("auto", "cuda", "cpu"), default="auto")
    p.add_argument("--token-file", default=None)
    args = p.parse_args(argv)
    if args.host not in LOOPBACK:
        print("audio service: it binds to 127.0.0.1 only", file=sys.stderr)
        return 2
    if args.device == "cpu":
        os.environ["CUDA_VISIBLE_DEVICES"] = ""  # the CPU run never touches the GPU
    token_file = args.token_file or os.environ.get("TB_AUDIO_TOKEN_FILE") or str(DEFAULT_TOKEN_FILE)
    token = read_token(token_file)
    if not token:
        print(f"audio service: cannot read the token file {token_file}", file=sys.stderr)
        return 2
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", stream=sys.stderr)
    for name in ("faster_whisper", "phonemizer", "onnx_asr", "aiohttp.access", "aiohttp.server", "aiohttp.web"):
        logging.getLogger(name).setLevel(logging.WARNING)
    from aiohttp import web

    from .server import make_app
    app = make_app(token, device=args.device, warm=args.warm)
    logging.getLogger("tb.audio").info("audio service on %s:%d device=%s", args.host, args.port, args.device)
    web.run_app(app, host=args.host, port=args.port, access_log=None, print=None)
    return 0


if __name__ == "__main__":
    sys.exit(main())
