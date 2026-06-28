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
