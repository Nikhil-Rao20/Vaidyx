"""The access log without search words (night-v3 Phase 8 review): uvicorn writes one line per request with the full path, so whatever
a person types in a search box (a patient's name, a message word) would land in the app log through the query string. This filter
keeps the path of every /api/tb/ request and drops its query string from the access log line. Installed once by the Tumour Board
start-up hook (routes/tumour_board_routes.py); harmless when the access log is off."""
from __future__ import annotations

import logging

PREFIX = "/api/tb/"
DROPPED = "?[query dropped]"


def strip_query(path) -> str:
    """'/api/tb/messages/search?q=Kavitha' -> '/api/tb/messages/search?[query dropped]'; other paths unchanged."""
    p = str(path or "")
    if p.startswith(PREFIX) and "?" in p:
        return p.split("?", 1)[0] + DROPPED
    return p


class QueryStripFilter(logging.Filter):
    """uvicorn's access record carries (client, method, path, http version, status) in record.args; the path is the third."""

    def filter(self, record: logging.LogRecord) -> bool:
        args = record.args
        try:
            if isinstance(args, tuple) and len(args) >= 3 and isinstance(args[2], str):
                record.args = args[:2] + (strip_query(args[2]),) + args[3:]
            elif isinstance(record.msg, str) and PREFIX in record.msg and "?" in record.msg:
                record.msg = " ".join(strip_query(w) if w.startswith(PREFIX) else w for w in record.msg.split(" "))
        except Exception:
            pass
        return True


def install() -> None:
    """Idempotent: one filter on the uvicorn access logger."""
    lg = logging.getLogger("uvicorn.access")
    if not any(isinstance(f, QueryStripFilter) for f in lg.filters):
        lg.addFilter(QueryStripFilter())
