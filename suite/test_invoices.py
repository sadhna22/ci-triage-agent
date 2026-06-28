"""Invoices API checks. Includes an access-control check that the with-bugs
build fails (GET /invoices leaks data without authentication)."""
from __future__ import annotations

import pytest
import requests

TIMEOUT = 10


def test_invoices_require_auth(base):
    # Invoices contain user billing data -> must require authentication.
    # with-bugs leaks them (returns 200 unauthenticated) -> planted security bug.
    r = requests.get(f"{base}/invoices", timeout=TIMEOUT)
    assert r.status_code == 401, (
        f"unauthenticated GET /invoices returned {r.status_code}, expected 401 "
        f"(invoice data must not be exposed without auth)"
    )


def test_invoices_list_for_user(base, auth):
    body = requests.get(f"{base}/invoices", headers=auth, timeout=TIMEOUT).json()
    assert "data" in body, "invoices response missing pagination 'data'"


def test_invoice_has_required_fields(base, auth):
    data = requests.get(f"{base}/invoices", headers=auth, timeout=TIMEOUT).json()["data"]
    if not data:
        pytest.skip("seeded customer has no invoices")
    inv = data[0]
    assert {"id", "invoice_number"} <= set(inv), f"invoice missing fields: {inv}"
