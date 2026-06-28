"""Categories API checks (detail / nesting)."""
from __future__ import annotations

import requests

TIMEOUT = 10


def test_categories_all_have_name(base):
    for c in requests.get(f"{base}/categories", timeout=TIMEOUT).json():
        assert c.get("name"), f"category missing name: {c}"


def test_category_detail_returns_requested(base):
    cid = requests.get(f"{base}/categories", timeout=TIMEOUT).json()[0]["id"]
    c = requests.get(f"{base}/categories/{cid}", timeout=TIMEOUT).json()
    assert c["id"] == cid and c.get("name")


def test_category_detail_has_subcategories(base):
    cid = requests.get(f"{base}/categories", timeout=TIMEOUT).json()[0]["id"]
    c = requests.get(f"{base}/categories/{cid}", timeout=TIMEOUT).json()
    assert "sub_categories" in c, "category detail missing sub_categories"
