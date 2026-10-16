"""Local server for the Vaidyx-TB workflow atlas (docs/ui/workflow).

Serves the page on 127.0.0.1 only and keeps the reader's marks and comments in notes.json next to this file
(kept out of git), so they can be read back later. Fonts come from static/tb/fonts (no copies).

Usage: python docs/ui/workflow/server.py [--port 7150]
"""
import argparse, json, os, threading, time
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
FONTS = (HERE / "../../../static/tb/fonts").resolve()
NOTES = HERE / "notes.json"
LOCK = threading.Lock()
MAX_BODY = 256 * 1024
MAX_FILE = 4 * 1024 * 1024


def load_notes():
    try:
        return json.loads(NOTES.read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        return {"items": {}, "general": {}}


def save_notes(data):
    tmp = NOTES.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, NOTES)


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=str(HERE), **kw)

    def log_message(self, fmt, *args):  # quiet
        pass

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def _json(self, code, obj):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path == "/api/notes":
            with LOCK:
                return self._json(200, load_notes())
        if path.startswith("/fonts/"):
            target = (FONTS / path[len("/fonts/"):]).resolve()
            if target.parent != FONTS or not target.is_file() or target.suffix != ".woff2":
                return self.send_error(404)
            data = target.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "font/woff2")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            return self.wfile.write(data)
        if path.endswith((".py", ".json", ".tmp")):
            return self.send_error(404)
        return super().do_GET()

    def do_POST(self):
        if self.path.split("?", 1)[0] != "/api/notes":
            return self.send_error(404)
        n = int(self.headers.get("Content-Length") or 0)
        if n <= 0 or n > MAX_BODY:
            return self._json(413, {"error": "Note too large"})
        try:
            msg = json.loads(self.rfile.read(n).decode("utf-8"))
        except ValueError:
            return self._json(400, {"error": "Not JSON"})
        stamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
        with LOCK:
            data = load_notes()
            if "general" in msg:  # {"general": {"section": "...", "text": "..."}}
                g = msg["general"]
                key = str(g.get("section", "page"))[:80]
                text = str(g.get("text", ""))[:20000]
                if text.strip():
                    data["general"][key] = {"text": text, "updated": stamp}
                else:
                    data["general"].pop(key, None)
            else:  # {"id", "title", "section", "mark", "comment"}
                iid = str(msg.get("id", ""))[:80]
                if not iid:
                    return self._json(400, {"error": "Missing id"})
                mark = msg.get("mark") if msg.get("mark") in ("keep", "change", "discuss") else None
                comment = str(msg.get("comment") or "")[:20000]
                if not mark and not comment.strip():
                    data["items"].pop(iid, None)
                else:
                    data["items"][iid] = {"title": str(msg.get("title", ""))[:300], "section": str(msg.get("section", ""))[:80],
                                          "mark": mark, "comment": comment, "updated": stamp}
            if len(json.dumps(data)) > MAX_FILE:
                return self._json(413, {"error": "Notes file is full"})
            save_notes(data)
        return self._json(200, {"ok": True, "saved": stamp})


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=7150)
    port = ap.parse_args().port
    print(f"Workflow atlas on http://127.0.0.1:{port}/  (notes: {NOTES})", flush=True)
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
