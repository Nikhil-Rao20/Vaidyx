"""Video (B3): the LiveKit keys file, access tokens (PyJWT and the small HMAC encoder give the same verifiable JWT), the status and
token routes (members only, off without keys)."""
import json

import jwt
import pytest

from tumour_board import config, video
from tumour_board.tests.test_nik_meetings import As, app, tc, started, join_and_admit  # noqa: F401

SECRET2 = "a-second-synthetic-secret-32-bytes-long"
KEYS = {"api_key": "APItestkey000001", "api_secret": "s3cr3t-synthetic-secret-for-tests-only", "url": "ws://127.0.0.1:7880"}


@pytest.fixture
def keys(data_root):
    (data_root / "livekit.json").write_text(json.dumps(KEYS))
    return KEYS


def test_keys_and_status(data_root):
    assert video.keys() is None and video.enabled() is False and video.status() == {"enabled": False, "url": None} and video.url() == "ws://127.0.0.1:7880"
    (data_root / "livekit.json").write_text("{bad json")
    assert video.keys() is None
    (data_root / "livekit.json").write_text(json.dumps({"api_key": "k"}))
    assert video.keys() is None
    (data_root / "livekit.json").write_text(json.dumps(KEYS))
    assert video.status() == {"enabled": True, "url": "ws://127.0.0.1:7880"} and video.room_name("S20261105-ab12") == "tb-S20261105-ab12"


def test_token_decodes_with_the_secret(keys):
    tok = video.token("priya", "Dr Priya Nair", "tb-S1", now=1_700_000_000)
    claims = jwt.decode(tok, KEYS["api_secret"], algorithms=["HS256"], options={"verify_exp": False})
    assert claims["iss"] == KEYS["api_key"] and claims["sub"] == "priya" and claims["name"] == "Dr Priya Nair"
    assert claims["nbf"] == 1_700_000_000 and claims["exp"] == 1_700_000_000 + 7200
    assert claims["video"] == {"roomJoin": True, "room": "tb-S1", "canPublish": True, "canSubscribe": True}
    with pytest.raises(jwt.PyJWTError):
        jwt.decode(tok, "another-synthetic-secret-for-tests-only-0000", algorithms=["HS256"], options={"verify_exp": False})
    assert video.decode(tok, KEYS["api_secret"])["sub"] == "priya"
    with pytest.raises(ValueError):
        video.decode(tok, "another-synthetic-secret-for-tests-only-0000")


def test_hmac_encoder_matches_pyjwt(keys):
    payload = {"iss": "k", "sub": "u", "nbf": 1, "exp": 2, "name": "n", "video": {"roomJoin": True, "room": "tb-S1", "canPublish": True, "canSubscribe": True}}
    tok = video.hmac_jwt(payload, SECRET2)
    assert tok.count(".") == 2 and "=" not in tok
    assert jwt.decode(tok, SECRET2, algorithms=["HS256"], options={"verify_exp": False}) == payload
    header, body, sig = tok.split(".")
    with pytest.raises(ValueError):
        video.decode(f"{header}.{body}.{sig[:-2]}xx", SECRET2)
    with pytest.raises(ValueError):
        video.decode("nope", SECRET2)
    # without PyJWT the encoder is used: the same claims
    import builtins
    real = builtins.__import__

    def no_jwt(name, *a, **k):
        if name == "jwt":
            raise ImportError("no jwt")
        return real(name, *a, **k)
    builtins.__import__ = no_jwt
    try:
        tok2 = video.token("priya", "Dr Priya Nair", "tb-S1", now=1_700_000_000)
    finally:
        builtins.__import__ = real
    assert jwt.decode(tok2, KEYS["api_secret"], algorithms=["HS256"], options={"verify_exp": False})["video"]["room"] == "tb-S1"


def test_video_routes(tc, data_root):
    mid = started(tc)
    join_and_admit(tc, mid, "priya")
    assert As(tc, "priya").get("/video/status").json() == {"enabled": False, "url": None}
    r = As(tc, "priya").post(f"/meetings/{mid}/video-token")
    assert r.status_code == 503 and r.json()["detail"]["code"] == "video_off"
    (data_root / "livekit.json").write_text(json.dumps(KEYS))
    assert As(tc, "priya").get("/video/status").json() == {"enabled": True, "url": "ws://127.0.0.1:7880"}
    r = As(tc, "ravi").post(f"/meetings/{mid}/video-token")
    assert r.status_code == 403 and r.json()["detail"]["code"] == "not_member"
    r = As(tc, "priya").post(f"/meetings/{mid}/video-token")
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["url"] == "ws://127.0.0.1:7880" and out["room"] == f"tb-{mid}" and out["identity"] == "priya" and out["name"] == "Dr Priya Nair" and out["expires_in"] == 7200
    claims = jwt.decode(out["token"], KEYS["api_secret"], algorithms=["HS256"])
    assert claims["sub"] == "priya" and claims["video"]["room"] == f"tb-{mid}" and claims["iss"] == KEYS["api_key"]
    assert KEYS["api_secret"] not in r.text
    assert As(tc, "anil").post(f"/meetings/{mid}/video-token").status_code == 200  # the coordinator is always a member
    As(tc, "anil").post(f"/meetings/{mid}/end")
    assert As(tc, "priya").post(f"/meetings/{mid}/video-token").status_code == 409
    assert As(tc, "priya").post("/meetings/S20991231-zzzz/video-token").status_code == 404
    from tumour_board import board
    assert "video_token" in [e["kind"] for e in board.read_audit() if e["session"] == mid]


def test_token_grants_sources_and_data(keys):
    from tumour_board import video as v
    claims = jwt.decode(v.token("priya", "Dr Priya Nair", "tb-S1", now=1_700_000_000, can_publish_sources=v.MEMBER_SOURCES, can_publish_data=True), KEYS["api_secret"], algorithms=["HS256"], options={"verify_exp": False})
    assert claims["video"]["canPublishSources"] == ["camera", "microphone", "screen_share", "screen_share_audio"] and claims["video"]["canPublishData"] is True
    claims = jwt.decode(v.token("anil#room", "Room screen", "tb-S1", now=1_700_000_000, can_publish_sources=v.ROOM_SOURCES), KEYS["api_secret"], algorithms=["HS256"], options={"verify_exp": False})
    assert claims["video"]["canPublishSources"] == ["camera", "microphone"] and "canPublishData" not in claims["video"]
    assert v.decode(v.hmac_jwt({"video": {"canPublishSources": ["camera"]}}, KEYS["api_secret"]), KEYS["api_secret"])["video"]["canPublishSources"] == ["camera"]


def test_video_token_route_grants_a_member_the_screen_share_and_the_room_screen_not(tc, data_root):
    mid = started(tc)
    join_and_admit(tc, mid, "priya")
    (data_root / "livekit.json").write_text(json.dumps(KEYS))
    claims = jwt.decode(As(tc, "priya").post(f"/meetings/{mid}/video-token").json()["token"], KEYS["api_secret"], algorithms=["HS256"])
    assert claims["video"]["canPublishSources"] == ["camera", "microphone", "screen_share", "screen_share_audio"] and "canPublishData" not in claims["video"]  # no data grant (review)
    claims = jwt.decode(As(tc, "anil").post(f"/meetings/{mid}/video-token", json={"screen": "room"}).json()["token"], KEYS["api_secret"], algorithms=["HS256"])
    assert claims["sub"] == "anil#room" and claims["video"]["canPublishSources"] == ["camera", "microphone"] and "canPublishData" not in claims["video"]
