"""Sample Toolshop API tests — the three seeded scenarios live here.

Scaffold: assertions are sketched so the structure is clear. Fill in real request
calls during the Day-1 suite slot, against the with-bugs Toolshop API.
"""
from __future__ import annotations

import requests


def test_list_products_returns_200(base_url):
    """Happy path — should pass against a healthy host."""
    resp = requests.get(f"{base_url}/products", timeout=5)
    assert resp.status_code == 200


def test_create_product_returns_201(base_url, auth_token):
    """S2 REAL_REGRESSION — a documented with-bugs defect makes this fail
    deterministically and violate the response contract (e.g. missing `id`)."""
    # TODO(build): POST a product; with-bugs returns a contract-violating response.
    resp = requests.post(f"{base_url}/products", json={"name": "hammer"}, timeout=5)
    assert resp.status_code == 201
    assert "id" in resp.json()  # with-bugs: field missing -> contract violation


def test_related_products_eventually_populated(base_url):
    """S1 FLAKY — order-dependent / async: passes or fails depending on whether a
    prior test seeded state and whether the related-products index has caught up.
    Run with pytest-randomly; force the failing order for the demo."""
    # TODO(build): rely on shared state seeded by another test (order dependence),
    # poll /products/<id>/related with a tight timeout so it's genuinely flaky.
    resp = requests.get(f"{base_url}/products/1/related", timeout=5)
    assert resp.status_code == 200
    assert len(resp.json()) > 0


# S3 ENVIRONMENT is reproduced by running any test with TRIAGE_ENV_BREAK=1
# (see conftest.py) — no dedicated test needed.
