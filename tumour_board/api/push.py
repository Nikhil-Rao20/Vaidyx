"""Push and notification preference routes (B3): GET /push/key, POST / DELETE /push/subscribe, GET / PUT /me/notifications."""
from fastapi import Request

from . import common
from .. import push

router = common.make_router(["tumour-board-push"])
SUBSCRIBE_LIMIT = common.RateLimit(20, 60 * 60)


def _tb_user(request: Request) -> str:
    """A Tumour Board user (placed, coordinator, admin, root admin, auditor or outside expert): push and its preferences are for them."""
    u = common.user(request)
    rl = common.roles(request)
    if rl.get("disabled") or not any(rl.get(k) for k in ("known", "outside_expert", "root_admin", "auditor")):
        common.fail(403, "Notifications are for Tumour Board accounts. Ask a Tumour Board admin to place your account.", "not_placed")
    return u


@router.get("/push/key")
async def push_key(request: Request):
    """The VAPID public key the page subscribes with (the keys are generated on first use); enabled is false without pywebpush."""
    common.user(request)
    k = push.keys(create=True)
    return {"public_key": (k or {}).get("public_key"), "enabled": push.enabled()}


@router.post("/push/subscribe")
async def push_subscribe(request: Request):
    u = _tb_user(request); b = await common.body(request)
    SUBSCRIBE_LIMIT.check(u, "Too many subscriptions from this account. Try again in an hour.")
    sub = b.get("subscription") if isinstance(b.get("subscription"), dict) else b
    try:
        return push.subscribe(u, sub, request.headers.get("user-agent", ""))
    except ValueError as e:
        common.fail(400, str(e), "bad_subscription")


@router.delete("/push/subscribe")
async def push_unsubscribe(request: Request):
    u = common.user(request)
    b = {}
    try:
        b = await common.body(request)
    except Exception:
        pass
    endpoint = str(b.get("endpoint") or request.query_params.get("endpoint") or "")
    if not endpoint:
        common.fail(400, "Say which subscription (endpoint) to remove.", "bad_subscription")
    return push.unsubscribe(u, endpoint)


@router.get("/me/notifications")
async def notification_prefs(request: Request):
    u = common.user(request)
    from .. import notify
    return {**push.prefs(u), "kinds_available": list(notify.KINDS), "push_enabled": push.enabled(), "subscriptions": len(push.subscriptions(u))}


@router.put("/me/notifications")
async def set_notification_prefs(request: Request):
    u = _tb_user(request); b = await common.body(request)
    try:
        return push.set_prefs(u, b)
    except ValueError as e:
        common.fail(400, str(e), "bad_prefs")
