"""Categories API checks (universally valid — pass on any correct Toolshop)."""
from __future__ import annotations

import requests

TIMEOUT = 10


def test_categories_all_have_name(base):
    for c in requests.get(f"{base}/categories", timeout=TIMEOUT).json():
        assert c.get("name"), f"category missing name: {c}"


def test_categories_have_unique_ids(base):
    cats = requests.get(f"{base}/categories", timeout=TIMEOUT).json()
    ids = [c["id"] for c in cats]
    assert len(ids) == len(set(ids)), "duplicate category ids"


def test_category_tree_is_nested(base):
    # The tree endpoint returns roots with a sub_categories array.
    tree = requests.get(f"{base}/categories/tree", timeout=TIMEOUT).json()
    assert isinstance(tree, list) and tree, "category tree is empty"
    assert all("sub_categories" in c for c in tree), "tree nodes missing sub_categories"
