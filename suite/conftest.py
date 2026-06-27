"""pytest fixtures for the Toolshop API suite.

Holds the base_url / auth config — and the S3 ENVIRONMENT toggle. Flip
TRIAGE_ENV_BREAK=1 to point the suite at a dead port and reproduce the
ConnectionRefused scenario on demand.
"""
from __future__ import annotations

import os

import pytest

GOOD_BASE_URL = os.environ.get(
    "API_BASE_URL", "http://localhost:8091/api"  # local with-bugs Toolshop
)
DEAD_BASE_URL = "http://localhost:1/api"  # nothing listens here -> ConnectionRefused


@pytest.fixture
def base_url() -> str:
    # S3 env-break toggle: when set, the suite talks to a dead port.
    if os.environ.get("TRIAGE_ENV_BREAK") == "1":
        return DEAD_BASE_URL
    return GOOD_BASE_URL


@pytest.fixture
def auth_token() -> str | None:
    # Dropping the token reproduces the 401 flavour of the env scenario.
    if os.environ.get("TRIAGE_DROP_AUTH") == "1":
        return None
    return os.environ.get("API_TOKEN")
