"""Shared pytest fixtures for the live Toolshop API suite.

`base` is the API base URL (honors TRIAGE_ENV_BREAK to point at a dead port for
the environment scenario). `auth` logs in as the seeded customer and returns a
Bearer header for authenticated endpoints.
"""
from __future__ import annotations

import os

import pytest
import requests

LIVE_BASE = os.environ.get("API_BASE_URL", "http://localhost:8091").rstrip("/")
DEAD_BASE = "http://localhost:1"  # nothing listens here -> ConnectionRefused
CUSTOMER = ("customer@practicesoftwaretesting.com", "welcome01")


@pytest.fixture(scope="session")
def base() -> str:
    # Env-break toggle: point the suite at a dead port to reproduce ConnectionRefused.
    if os.environ.get("TRIAGE_ENV_BREAK") == "1":
        return DEAD_BASE
    return LIVE_BASE


@pytest.fixture(scope="session")
def auth() -> dict:
    r = requests.post(
        f"{LIVE_BASE}/users/login",
        json={"email": CUSTOMER[0], "password": CUSTOMER[1]},
        timeout=10,
    )
    return {"Authorization": f"Bearer {r.json().get('access_token', '')}"}
