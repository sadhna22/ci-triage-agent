"""Favorites API checks (authenticated)."""
from __future__ import annotations

import pytest
import requests

TIMEOUT = 10


def test_favorites_require_auth(base):
    r = requests.get(f"{base}/favorites", timeout=TIMEOUT)
    assert r.status_code == 401, f"GET /favorites unauth returned {r.status_code}, expected 401"


def test_favorites_list_for_user(base, auth):
    favs = requests.get(f"{base}/favorites", headers=auth, timeout=TIMEOUT).json()
    assert isinstance(favs, list), "favorites should be a list"


def test_favorite_entry_has_product(base, auth):
    favs = requests.get(f"{base}/favorites", headers=auth, timeout=TIMEOUT).json()
    if not favs:
        pytest.skip("seeded customer has no favorites")
    assert "product" in favs[0], "favorite entry missing nested product"
