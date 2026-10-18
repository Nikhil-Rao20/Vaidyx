"""Browser push (B3): keys generated once (mode 600), subscribe and unsubscribe, a notification pushes a generic text (never a UHID or
a name) to the people addressed, a 410 removes the subscription, preferences (digest time, kinds), off without keys. pywebpush mocked."""
import json, os, stat

import pytest

from tumour_board import notify, org, push
from tumour_board.tests.test_nik_meetings import As, app, tc, hospital_org  # noqa: F401

SUB = {"endpoint": "https://push.example/sub/ravi-1", "keys": {"p256dh": "BPdh-synthetic", "auth": "auth-synthetic"}, "expirationTime": None}


@pytest.fixture
def sent(monkeypatch):
    """pywebpush.webpush replaced: records the calls; an endpoint ending in /gone answers 410."""
    import pywebpush
    calls = []

    class Resp:
        def __init__(self, status):
            self.status_code = status
            self.text = ""

    def fake_webpush(subscription_info, data=None, vapid_private_key=None, vapid_claims=None, **kw):
        calls.append({"endpoint": subscription_info["endpoint"], "data": json.loads(data), "claims": vapid_claims, "key": vapid_private_key, "ttl": kw.get("ttl")})
        if subscription_info["endpoint"].endswith("/gone"):
            raise pywebpush.WebPushException("gone", response=Resp(410))
        if subscription_info["endpoint"].endswith("/down"):
            raise pywebpush.WebPushException("down", response=Resp(500))
        return Resp(201)
    monkeypatch.setattr(pywebpush, "webpush", fake_webpush)
    monkeypatch.setattr(push, "ASYNC", False)
    return calls


def test_keys_are_generated_once_with_mode_600(data_root):
    assert push.keys() is None and push.public_key() is None and push.enabled() is False
    k = push.keys(create=True)
    assert k and k["public_key"] and k["private_key"] and "=" not in k["public_key"] and len(k["private_key"]) == 43
    p = data_root / "push_keys.json"
    assert stat.S_IMODE(os.stat(p).st_mode) == 0o600
    assert push.keys(create=True) == k and push.public_key() == k["public_key"] and push.enabled() is True
    from py_vapid import Vapid01
    v = Vapid01.from_raw(k["private_key"].encode())  # the stored private key is what the push library reads
    assert v.public_key is not None


def test_subscribe_unsubscribe_and_prefs_routes(tc, data_root):
    r = As(tc, "ravi").get("/push/key")
    assert r.status_code == 200 and r.json()["public_key"] and r.json()["enabled"] is True
    assert As(tc, "ravi").post("/push/subscribe", json={"subscription": {"endpoint": "http://plain", "keys": {}}}).status_code == 400
    r = As(tc, "ravi").post("/push/subscribe", json={"subscription": SUB})
    assert r.status_code == 200 and r.json() == {"subscribed": True, "count": 1}
    assert As(tc, "ravi").post("/push/subscribe", json=SUB).json()["count"] == 1  # the same endpoint again replaces it
    assert As(tc, "ravi").post("/push/subscribe", json={**SUB, "endpoint": "https://push.example/sub/ravi-2"}).json()["count"] == 2
    assert stat.S_IMODE(os.stat(data_root / "push_subs.json").st_mode) == 0o600
    assert As(tc, "ravi").get("/me/notifications").json()["subscriptions"] == 2
    r = As(tc, "ravi").delete("/push/subscribe?endpoint=https://push.example/sub/ravi-2")
    assert r.json() == {"removed": 1} and len(push.subscriptions("ravi")) == 1
    assert As(tc, "ravi").delete("/push/subscribe").status_code == 400
    p = As(tc, "ravi").get("/me/notifications").json()
    assert p["digest_time"] == "08:00" and p["kinds"] == {} and p["push"] is True and "reminder_automatic" in p["kinds_available"] and p["push_enabled"] is True
    r = As(tc, "ravi").put("/me/notifications", json={"digest_time": "07:30", "kinds": {"agenda": False, "digest": True}})
    assert r.status_code == 200 and r.json()["digest_time"] == "07:30" and r.json()["kinds"] == {"agenda": False, "digest": True}
    assert As(tc, "ravi").put("/me/notifications", json={"digest_time": "7:30"}).status_code == 400
    assert As(tc, "ravi").put("/me/notifications", json={"kinds": {"nope": True}}).status_code == 400
    assert As(tc, "ravi").get("/me/notifications").json()["digest_time"] == "07:30"
    assert push.prefs("anil")["digest_time"] == "08:00"  # another person keeps the default
    assert As(tc, "ravi").put("/me/notifications", json={"push": False}).json()["push"] is False and push.wants("ravi", "request") is False
    o = org.load(); o["users"]["ravi"]["disabled"] = True; org.save(o, by="test")
    assert As(tc, "ravi").post("/push/subscribe", json={"subscription": SUB}).status_code == 403  # a disabled account
    assert As(tc, "tbroot").post("/push/subscribe", json={"subscription": {**SUB, "endpoint": "https://push.example/sub/root"}}).status_code == 200


def test_a_notification_pushes_a_generic_text_to_the_people_addressed(data_root, sent):
    org.save(hospital_org(), by="test")
    push.keys(create=True)
    push.subscribe("ravi", SUB)
    push.subscribe("suresh", {**SUB, "endpoint": "https://push.example/sub/suresh-1"})
    push.subscribe("priya", {**SUB, "endpoint": "https://push.example/sub/priya-1"})
    rec = notify.notify({"department": "radiology"}, "request", "TB-001", "CT thorax needed for SYNTHETIC, Test Patient (TB-001)", "UHID SYN-900001", uhid="SYN-900001")
    assert sorted(c["endpoint"] for c in sent) == ["https://push.example/sub/ravi-1", "https://push.example/sub/suresh-1"]  # the department's people, not priya
    for c in sent:
        assert c["data"]["body"] == "Vaidyx-TB: a request needs your attention" and c["data"]["title"] == "Vaidyx-TB" and c["data"]["kind"] == "request"
        assert "SYN-900001" not in json.dumps(c["data"]) and "Test Patient" not in json.dumps(c["data"]) and "TB-001" not in json.dumps(c["data"])
        assert c["claims"] == {"sub": push.CONTACT} and c["key"] == push.keys()["private_key"] and c["ttl"] == 3600
    assert rec["kind"] == "request"  # the in-app notification is unchanged
    sent.clear()
    notify.notify({"role": "coordinator"}, "board_ready", "TB-001", "Ready", "")
    assert sent == []  # anil has no subscription
    push.subscribe("anil", {**SUB, "endpoint": "https://push.example/sub/anil-1"})
    notify.notify({"role": "coordinator"}, "board_ready", "TB-001", "Ready", "")
    assert [c["endpoint"] for c in sent] == ["https://push.example/sub/anil-1"] and sent[0]["data"]["body"] == push.TEXTS["board_ready"]
    sent.clear()
    notify.notify({"user": "priya"}, "outcome", "TB-002", "Board outcome", "")
    assert [c["endpoint"] for c in sent] == ["https://push.example/sub/priya-1"]
    sent.clear()
    push.set_prefs("priya", {"kinds": {"outcome": False}})
    notify.notify({"user": "priya"}, "outcome", "TB-002", "Board outcome", "")
    assert sent == []  # a kind switched off
    notify.notify({"user": "priya"}, "sign_off", "TB-002", "Sign off", "")
    assert sent[0]["data"]["body"] == "Vaidyx-TB: a resident asks you to sign off"
    assert push.text_for("unknown_kind") == push.GENERIC


def test_gone_subscriptions_are_removed_and_failures_never_raise(data_root, sent):
    org.save(hospital_org(), by="test")
    push.keys(create=True)
    push.subscribe("ravi", {**SUB, "endpoint": "https://push.example/sub/gone"})
    push.subscribe("ravi", {**SUB, "endpoint": "https://push.example/sub/down"})
    push.subscribe("ravi", {**SUB, "endpoint": "https://push.example/sub/ok"})
    out = push.send_to_users(["ravi", "ravi", "nobody"], "request")
    assert out == {"sent": 1, "removed": 1, "skipped": 0, "failed": 1}
    assert [s["endpoint"] for s in push.subscriptions("ravi")] == ["https://push.example/sub/down", "https://push.example/sub/ok"]
    assert push.users_for({"department": "Radiology"}) == ["ravi", "suresh"] and push.users_for({"role": "coordinator"}) == ["anil"]
    assert push.users_for({"user": "x"}) == ["x"] and push.users_for({"department": "MDT Coordinator"}) == ["anil"] and push.users_for({}) == []


def test_push_is_off_without_keys(data_root, sent):
    org.save(hospital_org(), by="test")
    push.subscribe("ravi", SUB)
    assert push.enabled() is False
    assert push.send_to_users(["ravi"], "request") == {"sent": 0, "removed": 0, "skipped": 1, "failed": 0}
    notify.notify({"department": "radiology"}, "request", "TB-001", "t", "")
    assert sent == [] and push.on_notification({"to": {"user": "ravi"}, "kind": "request"}) is None


def test_digest_due_follows_the_preference():
    from datetime import datetime
    assert push.digest_due("ravi", datetime(2026, 10, 18, 8, 0), None) is True
    assert push.digest_due("ravi", datetime(2026, 10, 18, 7, 59), None) is False
    assert push.digest_due("ravi", datetime(2026, 10, 18, 9, 0), "2026-10-18") is False
    assert push.digest_due("ravi", datetime(2026, 10, 19, 9, 0), "2026-10-18") is True
