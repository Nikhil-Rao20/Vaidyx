"""A first or reset password (must_change_password) opens only "who am I" and the password change on the Tumour Board API (18 Oct 2026)."""
from tumour_board.tests.test_nik_me import RAO, api, auth, people  # noqa: F401  (shared fixtures)


def test_first_password_opens_only_me_and_the_password_change(api, auth):
    auth.reset_password(RAO, "first-password-xyz", must_change=True)
    me = api.as_(RAO).get("/me")
    assert me.status_code == 200 and me.json()["must_change_password"] is True
    r = api.as_(RAO).get("/case-list")
    assert r.status_code == 409 and r.json()["detail"]["code"] == "password_change_required"
    r = api.as_(RAO).post("/me/password", {"current_password": "first-password-xyz", "new_password": "my-own-password-2026"})
    assert r.status_code == 200, r.text
    assert api.as_(RAO).get("/case-list").status_code == 200
