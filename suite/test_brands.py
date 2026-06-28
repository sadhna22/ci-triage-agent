"""Brands API checks."""
from __future__ import annotations

import requests

TIMEOUT = 10


def test_list_brands_nonempty(base):
    brands = requests.get(f"{base}/brands", timeout=TIMEOUT).json()
    assert isinstance(brands, list) and brands, "brand list is empty"


def test_brands_have_required_fields(base):
    for b in requests.get(f"{base}/brands", timeout=TIMEOUT).json():
        assert {"id", "name", "slug"} <= set(b), f"brand missing fields: {b}"


def test_brand_detail_returns_requested(base):
    bid = requests.get(f"{base}/brands", timeout=TIMEOUT).json()[0]["id"]
    b = requests.get(f"{base}/brands/{bid}", timeout=TIMEOUT).json()
    assert b["id"] == bid and b.get("name")


def test_delete_brand_requires_auth(base):
    bid = requests.get(f"{base}/brands", timeout=TIMEOUT).json()[0]["id"]
    r = requests.delete(f"{base}/brands/{bid}", timeout=TIMEOUT)
    assert r.status_code in (401, 403), (
        f"unauthenticated DELETE /brands/{{id}} returned {r.status_code}, expected 401/403"
    )
