"""The meeting PDF downloads (meetings-v2 item 4.1, owner decision D10): they replace the .pptx deck, removed in item 4.2.

    GET /meetings/{mid}/pdf          the PDF of a meeting: the MDT Coordinator and the admitted members (the deck's rule); never an
                                     outside expert. A member gets the decision records of the Case Files it may read in full; the others
                                     print their outcome only (meeting_pdf, as the meeting page and the minutes rule)
    GET /cases/{case_id}/board-pdf   the board records of one Case File, latest first: whoever may open the whole Case File, never in a
                                     read-only window (a doctor's opened with a reason, the meeting window, the Vaidyx admin's break-glass);
                                     404 no_board_record when it has none; a protected Case File is never printed

Every download is audited on the meeting (sessions/audit.jsonl, meeting_pdf_downloaded) or on the Case File (board_pdf_downloaded),
as the deck downloads are. The PDF is made by WeasyPrint in a separate process (meeting_pdf.render_pdf); 503 when it cannot be made."""
import asyncio

from fastapi import Request
from fastapi.responses import Response

from tumour_board import access, board, config, meeting_pdf, meetings, store
from tumour_board.api.common import case, fail, make_router, need_known, roles, scope, user

router = make_router(["tumour-board-meeting-pdf"])


def _pdf(data: bytes, name: str) -> Response:
    return Response(data, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{name}"', "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})


@router.get("/meetings/{mid}/pdf")
async def meeting_pdf_download(mid: str, request: Request):
    u = user(request); rl = roles(request); need_known(rl)
    s = meetings.get(mid)
    if not s:
        fail(404, "Meeting not found.", "not_found")
    if rl.get("outside_expert") and not meetings.manage(rl):
        fail(403, "An outside expert follows the shared screen; the meeting PDF is for the hospital's members.", "outside_expert")
    if not (meetings.manage(rl) or meetings.is_member(rl, s)):
        fail(403, "Only the MDT Coordinator and the admitted members download the meeting PDF.", "not_member")
    try:
        data, info = await asyncio.to_thread(meeting_pdf.build_meeting, s["id"], rl)
    except KeyError:
        fail(404, "Meeting not found.", "not_found")
    except meeting_pdf.PdfError as e:
        fail(503, str(e), e.code)
    board.audit_event(s["id"], "meeting_pdf_downloaded", u, bytes=len(data), cases=info["cases"], restricted=info["restricted"])
    return _pdf(data, meeting_pdf.filename("meeting", s["id"], info.get("date") or ""))


@router.get("/cases/{case_id}/board-pdf")
async def case_board_pdf(case_id: str, request: Request):
    u = user(request); rl = roles(request); need_known(rl)
    c = case(case_id)
    cid = c.get("case_id") or case_id
    try:  # a window reads on screen only: no download (as the deck, whole-run review 9, I1)
        access.no_export_in_window(rl, c, scope(request))
    except access.AccessError as e:
        fail(e.status, str(e), e.code)
    if str(access.scope(rl, c) or "").upper() != "FULL":
        fail(403, "Only the people who may open the whole Case File download its board record.", "forbidden")
    if cid in config.PROTECTED_CASES or access.is_protected(c):
        fail(403, "A protected Case File is never printed.", "protected")
    st = store.get_state(cid) or {}
    if not [x for x in st.get("board_records") or [] if isinstance(x, dict)]:
        fail(404, "No board decision is recorded for this Case File yet.", "no_board_record")
    try:
        data, n = await asyncio.to_thread(meeting_pdf.build_case, cid, rl)
    except KeyError:
        fail(404, "Case not found", "not_found")
    except meeting_pdf.PdfError as e:
        fail(503, str(e), e.code)
    store.audit(cid, {"kind": "board_pdf_downloaded", "by": u, "bytes": len(data), "records": n})
    return _pdf(data, meeting_pdf.filename("record", cid))
