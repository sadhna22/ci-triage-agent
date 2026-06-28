"""Contact / messages API checks."""
from __future__ import annotations

import requests

TIMEOUT = 10


def test_contact_rejects_empty_payload(base):
    r = requests.post(f"{base}/messages", json={}, timeout=TIMEOUT)
    assert r.status_code == 422, f"empty contact message returned {r.status_code}, expected 422"
