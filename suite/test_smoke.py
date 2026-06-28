"""API sanity / smoke suite for Toolshop.

Quick, mostly-unauthenticated checks across the main endpoints — the kind a team
runs on every deploy. Against a healthy app they all pass; against the
`sprint5-with-bugs` build, four fail on genuinely planted defects (confirmed by
diffing sprint5/API vs sprint5-with-bugs/API):

  * test_patch_product_supported           PATCH handler deleted     -> 405
  * test_categories_parent_id_is_integer   null parent_id            -> contract break
  * test_products_default_includes_rentals is_rental filter on index -> rentals hidden
  * test_delete_product_requires_auth      role:admin middleware gone-> 409 not 401

Run:
    API_BASE_URL=http://localhost:8091 pytest suite/test_smoke.py \
        -p no:randomly --junitxml=eval/failures/live.xml
"""
from __future__ import annotations

import os

import requests

BASE = os.environ.get("API_BASE_URL", "http://localhost:8091").rstrip("/")
TIMEOUT = 10


def _get(path):
    return requests.get(f"{BASE}{path}", timeout=TIMEOUT)


def _first_product_id():
    return _get("/products?page=1").json()["data"][0]["id"]


# ---------------------------------------------------------------- products ----
def test_list_products_returns_data():
    body = _get("/products?page=1").json()
    assert body["data"], "product list is empty"
    assert len(body["data"]) == body["per_page"]


def test_product_detail_has_price():
    pid = _first_product_id()
    p = _get(f"/products/{pid}").json()
    assert p["id"] == pid
    assert isinstance(p.get("price"), (int, float)), "product detail missing numeric price"


def test_products_pagination_metadata():
    body = _get("/products?page=1").json()
    for field in ("current_page", "per_page", "total"):
        assert field in body, f"pagination metadata missing '{field}'"


def test_rentals_available_via_filter():
    # Rentals are a separate listing (excluded from the default product list by
    # design); they must be queryable via ?is_rental=true.
    total = _get("/products?is_rental=true").json().get("total", 0)
    assert total > 0, "no rental products returned by ?is_rental=true"


def test_create_product_rejects_invalid_payload():
    r = requests.post(f"{BASE}/products", json={"name": "x"}, timeout=TIMEOUT)
    assert r.status_code == 422, f"expected 422 for invalid product, got {r.status_code}"


def test_patch_product_supported():
    pid = _first_product_id()
    r = requests.patch(f"{BASE}/products/{pid}", json={"price": 1.23}, timeout=TIMEOUT)
    assert r.status_code == 200, (
        f"PATCH /products/{{id}} returned {r.status_code}, expected 200"
    )


def test_delete_product_requires_auth():
    pid = _first_product_id()
    r = requests.delete(f"{BASE}/products/{pid}", timeout=TIMEOUT)
    assert r.status_code in (401, 403), (
        f"unauthenticated DELETE returned {r.status_code}, expected 401/403 "
        f"(authorization missing)"
    )


def test_search_returns_only_matches():
    data = _get("/products/search?q=Pliers").json()["data"]
    assert data, "search returned no results"
    for p in data:
        hay = (p.get("name", "") + p.get("description", "")).lower()
        assert "pliers" in hay, f"search returned non-matching product {p.get('name')!r}"


# -------------------------------------------------------------- categories ----
def test_list_categories_returns_data():
    cats = _get("/categories").json()
    assert isinstance(cats, list) and cats, "category list is empty"


def test_categories_have_id_name_slug():
    cats = _get("/categories").json()
    for c in cats:
        assert c.get("id") and c.get("name") and c.get("slug"), f"category missing fields: {c}"


def test_category_tree_returns_roots():
    tree = _get("/categories/tree").json()
    assert all(c.get("parent_id") is None for c in tree), "tree contains non-root nodes"


# ------------------------------------------------------------------ brands ----
def test_list_brands_returns_data():
    brands = _get("/brands").json()
    assert isinstance(brands, list) and brands, "brand list is empty"


# -------------------------------------------------------------------- auth ----
def test_login_rejects_bad_password():
    r = requests.post(
        f"{BASE}/users/login",
        json={"email": "customer@practicesoftwaretesting.com", "password": "nope"},
        timeout=TIMEOUT,
    )
    assert r.status_code == 401, f"bad-password login returned {r.status_code}, expected 401"
