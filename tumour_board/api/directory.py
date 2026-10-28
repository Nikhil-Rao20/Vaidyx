"""The people and departments directory routes (night-v3 item 8.3, contract docs/night-v3/research/06_messages.md section 9.6):
GET /directory?q=&department= and GET /directory/{user}/photo. Both are for people who may use Messages (placed hospital staff and the
MDT Coordinator); everyone else gets 403 not_placed. Reading only: nothing is written and nothing is audited."""
from fastapi import Request
from fastapi.responses import Response

from . import common
from .. import directory, messages

router = common.make_router(["tumour-board-directory"])
DIRECTORY_LIMIT = common.RateLimit(60, 60)
PHOTO_LIMIT = common.RateLimit(120, 60)
NOT_PLACED = "Messages are for placed hospital staff."
LIMIT_MESSAGE = "Too many searches. Please wait a moment."


def _placed(request: Request) -> str:
    """The login asking, when it may use Messages; else 403 not_placed."""
    r = common.roles(request)
    if not messages.may_use(r):
        common.fail(403, NOT_PLACED, "not_placed")
    return r["user"]


@router.get("/directory")
async def directory_search(request: Request, q: str = "", department: str = ""):
    login = _placed(request)
    DIRECTORY_LIMIT.check(common.client_key(request), LIMIT_MESSAGE)
    q = str(q or "")[:100]
    return {"people": directory.people(q, department or None), "departments": directory.departments(q),
            "coordinators": directory.coordinators(), "me": login}


@router.get("/directory/{user}/photo")
async def directory_photo(user: str, request: Request):
    _placed(request)
    PHOTO_LIMIT.check(common.client_key(request), LIMIT_MESSAGE)
    found = directory.photo(user)
    if not found:
        common.fail(404, "No photo.", "no_photo")
    content, media_type = found
    return Response(content, media_type=media_type,
                    headers={"Cache-Control": "private, max-age=300", "X-Content-Type-Options": "nosniff"})
