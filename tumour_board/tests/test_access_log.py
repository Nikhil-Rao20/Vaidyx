"""The access log keeps the path and drops the query string of /api/tb/ requests (night-v3 Phase 8 review): a search word never lands
in the app log through the URL."""
import logging

from tumour_board import access_log


def _record(path, msg='%s - "%s %s HTTP/%s" %d'):
    return logging.LogRecord("uvicorn.access", logging.INFO, __file__, 1, msg, ("127.0.0.1:1", "GET", path, "1.1", 200), None)


def test_query_string_of_tb_paths_is_dropped():
    f = access_log.QueryStripFilter()
    r = _record("/api/tb/messages/search?q=Kavitha%20Raghunathan&x=1")
    assert f.filter(r) is True
    assert r.getMessage() == '127.0.0.1:1 - "GET /api/tb/messages/search?[query dropped] HTTP/1.1" 200'
    assert "Kavitha" not in r.getMessage()


def test_other_paths_and_plain_paths_are_unchanged():
    f = access_log.QueryStripFilter()
    r = _record("/api/tb/messages/unread"); f.filter(r)
    assert "/api/tb/messages/unread HTTP" in r.getMessage()
    r = _record("/static/tb-nik/index.html?v=3"); f.filter(r)
    assert "index.html?v=3" in r.getMessage()


def test_install_is_idempotent_and_filters_the_logger(caplog):
    access_log.install(); access_log.install()
    lg = logging.getLogger("uvicorn.access")
    assert sum(isinstance(x, access_log.QueryStripFilter) for x in lg.filters) == 1
    with caplog.at_level(logging.INFO, logger="uvicorn.access"):
        lg.info('%s - "%s %s HTTP/%s" %d', "127.0.0.1:1", "GET", "/api/tb/directory?q=Priya", "1.1", 200)
    assert "Priya" not in caplog.text and "/api/tb/directory?[query dropped]" in caplog.text
