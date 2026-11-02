"""The hospital logo (19 Oct 2026) and the end of the .pptx deck (meetings-v2 item 4.2, owner decision D10): the deck of a meeting and of
one Case File are gone (the meeting PDF and the board record PDF replace them, test_meeting_pdf.py); the logo upload and the logo route
stay. Hermetic: the meeting fixtures of test_nik_meetings, synthetic Case Files, no model."""
import base64
import io

from tumour_board import config, meeting_pdf, org
from tumour_board.tests.test_nik_meetings import As, app, tc, join_and_admit, owned, started  # noqa: F401


def _png_1x1() -> bytes:
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGBA", (8, 8), (11, 78, 116, 255)).save(buf, format="PNG")
    return buf.getvalue()


def test_the_deck_routes_are_gone(tc):
    """GET /meetings/{mid}/deck and GET /cases/{id}/deck answer 404 for everyone (the coordinator, an admitted member, the owner);
    the PDF routes answer instead."""
    mid = started(tc)
    owned("TB-002")
    assert As(tc, "anil").get(f"/meetings/{mid}/deck").status_code == 404
    assert As(tc, "priya").get("/cases/TB-002/deck").status_code == 404
    join_and_admit(tc, mid, "ravi")
    assert As(tc, "ravi").get(f"/meetings/{mid}/deck").status_code == 404
    from tumour_board.api import deck as api_deck
    paths = {getattr(r, "path", "") for r in api_deck.router.routes}
    assert paths == {"/hospital/logo", "/setup/hospital/logo"}, paths  # the logo routes only
    # the PDF routes answer instead: the board record of a Case File with none yet is a plain 404 no_board_record
    r = As(tc, "priya").get("/cases/TB-002/board-pdf")
    assert r.status_code == 404 and r.json()["detail"]["code"] == "no_board_record", r.text


def test_the_deck_module_is_gone():
    """tumour_board/deck (python-pptx) was only used by the deck routes; the meeting PDF keeps its own copies of the images."""
    import importlib.util
    assert importlib.util.find_spec("tumour_board.deck") is None
    assert (meeting_pdf.TEMPLATE_DIR / "demo-hospital.png").exists()


def test_hospital_logo_upload_and_use(tc, data_root):
    assert As(tc, "priya").get("/hospital/logo").status_code == 404
    png = _png_1x1()
    data = "data:image/png;base64," + base64.b64encode(png).decode()
    assert As(tc, "priya").post("/setup/hospital/logo", json={"data": data}).status_code == 403
    r = As(tc, "tbroot").post("/setup/hospital/logo", json={"data": data})
    assert r.status_code == 200 and r.json()["logo"]["file"] == "hospital_logo.png", r.text
    assert (config.DATA_ROOT / "hospital_logo.png").read_bytes() == png
    assert org.hospital()["logo"]["type"] == "image/png" and meeting_pdf.logo_path() == config.DATA_ROOT / "hospital_logo.png"
    r = As(tc, "priya").get("/hospital/logo")
    assert r.status_code == 200 and r.headers["content-type"].startswith("image/png") and r.content == png
    # a JPEG claimed that is not one, and something too big, are refused
    assert As(tc, "tbroot").post("/setup/hospital/logo", json={"data": "data:image/jpeg;base64," + base64.b64encode(png).decode()}).status_code == 400
    assert As(tc, "tbroot").post("/setup/hospital/logo", json={"data": "data:image/png;base64," + base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"0" * 1_100_000).decode()}).status_code in (400, 413)  # the body limit may answer first
    assert As(tc, "tbroot").post("/setup/hospital/logo", json={"data": "data:image/svg+xml;base64,PHN2Zz4="}).status_code == 400
    # the meeting PDF's cover carries the uploaded logo (as a data URL in its HTML)
    assert meeting_pdf._data_uri(meeting_pdf.logo_path()) == "data:image/png;base64," + base64.b64encode(png).decode()
    assert As(tc, "tbroot").delete("/setup/hospital/logo").status_code == 200
    assert As(tc, "priya").get("/hospital/logo").status_code == 404 and not (config.DATA_ROOT / "hospital_logo.png").exists()
