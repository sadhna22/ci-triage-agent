"""Users / auth API checks."""
from __future__ import annotations

import requests

TIMEOUT = 10


def test_login_success_returns_token(base):
    r = requests.post(
        f"{base}/users/login",
        json={"email": "customer@practicesoftwaretesting.com", "password": "welcome01"},
        timeout=TIMEOUT,
    )
    assert r.status_code == 200 and r.json().get("access_token")


def test_me_requires_auth(base):
    r = requests.get(f"{base}/users/me", timeout=TIMEOUT)
    assert r.status_code == 401, f"GET /users/me unauth returned {r.status_code}, expected 401"


def test_me_returns_profile(base, auth):
    me = requests.get(f"{base}/users/me", headers=auth, timeout=TIMEOUT).json()
    assert "id" in me and me.get("first_name")


def test_register_rejects_empty_payload(base):
    r = requests.post(f"{base}/users/register", json={}, timeout=TIMEOUT)
    assert r.status_code == 422, f"empty register returned {r.status_code}, expected 422"
