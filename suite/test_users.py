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


def test_me_hides_sensitive_fields(base, auth):
    me = requests.get(f"{base}/users/me", headers=auth, timeout=TIMEOUT).json()
    leaked = [f for f in ("password", "totp_secret", "failed_login_attempts") if f in me]
    assert not leaked, f"/users/me exposes sensitive fields: {leaked}"


def _valid_registration(email: str) -> dict:
    return {
        "first_name": "Test", "last_name": "User", "address": "1 St",
        "city": "Town", "state": "ST", "country": "NL", "postcode": "1000",
        "phone": "0612345678", "dob": "1990-01-01", "email": email,
    }


def test_register_rejects_weak_password(base):
    import uuid
    payload = _valid_registration(f"weakpw_{uuid.uuid4().hex[:8]}@example.com")
    payload["password"] = "aaaaaaaaa"  # no mixed case / number / symbol
    r = requests.post(f"{base}/users/register", json=payload, timeout=TIMEOUT)
    assert r.status_code == 422, (
        f"register accepted a weak password ({r.status_code}), expected 422"
    )


def test_register_does_not_leak_password_hint(base):
    payload = _valid_registration("customer@practicesoftwaretesting.com")  # existing
    payload["password"] = "SuperSecret1!"
    r = requests.post(f"{base}/users/register", json=payload, timeout=TIMEOUT)
    body = r.text.lower()
    assert "hint" not in body and "cat" not in body, (
        "register response leaks a password hint / enumerates the account"
    )
