"""Contact / messages API checks."""
from __future__ import annotations

import requests

TIMEOUT = 10


def test_contact_rejects_empty_payload(base):
    r = requests.post(f"{base}/messages", json={}, timeout=TIMEOUT)
    assert r.status_code == 422, f"empty contact message returned {r.status_code}, expected 422"


def test_contact_validates_email(base):
    r = requests.post(
        f"{base}/messages",
        json={"name": "X", "email": "not-an-email", "subject": "Customer service",
              "message": "hello there, this is a long enough message"},
        timeout=TIMEOUT,
    )
    assert r.status_code == 422, (
        f"POST /messages accepted an invalid email ({r.status_code}), expected 422"
    )
