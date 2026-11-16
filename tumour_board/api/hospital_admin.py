"""The Hospital console's API (admin consoles, 16 Nov 2026, docs/admin-console/DESIGN.md 5.3, API_FIELDS.md): GET /hospital/overview and
GET /hospital/departments for the current hospital.

Who: the hospital admin of this hospital, or a Vaidyx admin (in the hospital it acts in): org.can(r, "manage_org"). Counts and names of
people only (no patient name, UHID or report text); the recent events are the hospital's people, set-up, account and hospital-system
events, never a clinical one. The changes stay on the existing routes (/accounts, /setup/*, /departments/{d}/people, /his/*)."""
from fastapi import Request

from tumour_board import org, platform_admin as svc
from tumour_board.api.common import fail, make_router, roles

router = make_router()
NOT_YOURS = "Only the hospital admin opens the Hospital console."


def _admin(request: Request) -> dict:
    r = roles(request)
    if not org.can(r, "manage_org"):
        fail(403, NOT_YOURS, "forbidden")
    return r


@router.get("/hospital/overview")
async def overview(request: Request):
    _admin(request)
    return svc.hospital_overview(getattr(request.app.state, "auth_manager", None))


@router.get("/hospital/departments")
async def departments(request: Request):
    _admin(request)
    return svc.departments_view()
