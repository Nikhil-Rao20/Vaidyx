"""The board deck (19 Oct 2026): the deck of a meeting and of one Case File as .pptx (python-pptx, a design of our own), who may
download which, the hospital logo upload. Hermetic: the meeting fixtures of test_nik_meetings, synthetic Case Files, no model."""
import base64
import io

from pptx import Presentation

from tumour_board import config, deck, org, store
from tumour_board.tests.test_nik_meetings import As, app, tc, join_and_admit, owned, started  # noqa: F401

PPTX = "application/vnd.openxmlformats-officedocument.presentationml.presentation"


def _png_1x1() -> bytes:
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGBA", (8, 8), (11, 78, 116, 255)).save(buf, format="PNG")
    return buf.getvalue()


def _texts(data: bytes) -> list[str]:
    prs = Presentation(io.BytesIO(data))
    out = []
    for s in prs.slides:
        out.append(" ".join(sh.text_frame.text for sh in s.shapes if sh.has_text_frame))
    return out


def test_case_deck_is_a_presentation_with_the_chapter(tc):
    owned("TB-002")
    r = As(tc, "priya").get("/cases/TB-002/deck")
    assert r.status_code == 200 and r.headers["content-type"].startswith(PPTX) and r.content[:2] == b"PK"
    assert 'filename="Tumour-Board-case-TB-002.pptx"' in r.headers["content-disposition"]
    texts = _texts(r.content)
    assert len(texts) >= 5  # cover, the case title, the summary, the values, the records, the closing
    name = store.get_case("TB-002")["patient"]["name"].split(",")[0].split()[0]
    assert any(name in t for t in texts[:2])
    assert any("Question for the Tumour Board".upper() in t.upper() for t in texts)
    assert "Vaidyx checks, routes, summarises and flags" in " ".join(texts)
    # the builder itself, straight
    assert deck.build_case("TB-002")[:2] == b"PK"
    # a doctor with no scope on the file is refused; the audit names the download
    assert As(tc, "mohan").get("/cases/TB-002/deck").status_code == 403
    assert "deck_downloaded" in (store.case_dir("TB-002") / "audit.jsonl").read_text()


def test_meeting_deck_for_the_coordinator_and_the_admitted_members(tc):
    mid = started(tc)
    r = As(tc, "anil").get(f"/meetings/{mid}/deck")
    assert r.status_code == 200 and r.content[:2] == b"PK" and "Tumour-Board-meeting-" in r.headers["content-disposition"]
    texts = _texts(r.content)
    assert "Agenda" in texts[1] and len(texts) >= 6
    assert As(tc, "ravi").get(f"/meetings/{mid}/deck").status_code == 403  # not admitted yet
    join_and_admit(tc, mid, "ravi")
    assert As(tc, "ravi").get(f"/meetings/{mid}/deck").status_code == 200
    join_and_admit(tc, mid, "guest")
    assert As(tc, "guest").get(f"/meetings/{mid}/deck").status_code == 403  # an outside expert follows the screen only
    assert As(tc, "anil").get("/meetings/S20991231-zzzz/deck").status_code == 404


def test_closed_meeting_deck_carries_the_outcomes_and_minutes(tc):
    mid = started(tc)
    s = As(tc, "anil").get(f"/meetings/{mid}").json()
    cid = s["agenda"]["discussion"][0]["case_id"]
    As(tc, "anil").post(f"/meetings/{mid}/current", json={"case_id": cid})
    r = As(tc, "anil").post(f"/meetings/{mid}/cases/{cid}/decision", json={"outcome": "decision", "decision_text": "Upfront surgery, then adjuvant therapy as per the final histopathology.", "members_present": ["Anil Kumar"]})
    assert r.status_code == 200, r.text
    assert As(tc, "anil").post(f"/meetings/{mid}/end").status_code == 200
    r = As(tc, "anil").get(f"/meetings/{mid}/deck")
    assert r.status_code == 200
    joined = " ".join(_texts(r.content))
    assert "Upfront surgery, then adjuvant therapy" in joined and "Outcomes of the meeting" in joined and "Closed: outcomes and minutes inside" in joined


def test_hospital_logo_upload_and_use(tc, data_root):
    assert As(tc, "priya").get("/hospital/logo").status_code == 404
    png = _png_1x1()
    data = "data:image/png;base64," + base64.b64encode(png).decode()
    assert As(tc, "priya").post("/setup/hospital/logo", json={"data": data}).status_code == 403
    r = As(tc, "tbroot").post("/setup/hospital/logo", json={"data": data})
    assert r.status_code == 200 and r.json()["logo"]["file"] == "hospital_logo.png", r.text
    assert (config.DATA_ROOT / "hospital_logo.png").read_bytes() == png
    assert org.hospital()["logo"]["type"] == "image/png" and deck.hospital_logo_path() == config.DATA_ROOT / "hospital_logo.png"
    r = As(tc, "priya").get("/hospital/logo")
    assert r.status_code == 200 and r.headers["content-type"].startswith("image/png") and r.content == png
    # a JPEG claimed that is not one, and something too big, are refused
    assert As(tc, "tbroot").post("/setup/hospital/logo", json={"data": "data:image/jpeg;base64," + base64.b64encode(png).decode()}).status_code == 400
    assert As(tc, "tbroot").post("/setup/hospital/logo", json={"data": "data:image/png;base64," + base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"0" * 1_100_000).decode()}).status_code in (400, 413)  # the body limit may answer first
    assert As(tc, "tbroot").post("/setup/hospital/logo", json={"data": "data:image/svg+xml;base64,PHN2Zz4="}).status_code == 400
    # the deck's cover carries the logo (a picture on the first slide)
    owned("TB-002")
    prs = Presentation(io.BytesIO(As(tc, "priya").get("/cases/TB-002/deck").content))
    assert any(sh.shape_type == 13 for sh in prs.slides[0].shapes)  # MSO_SHAPE_TYPE.PICTURE
    assert As(tc, "tbroot").delete("/setup/hospital/logo").status_code == 200
    assert As(tc, "priya").get("/hospital/logo").status_code == 404 and not (config.DATA_ROOT / "hospital_logo.png").exists()
