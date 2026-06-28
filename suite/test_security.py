"""Security / access-control regression checks.

These assert universal security invariants (a correct app passes them regardless
of version); the sprint5-with-bugs build violates them. Found by diffing
sprint5/API vs sprint5-with-bugs/API.
"""
from __future__ import annotations

import requests

TIMEOUT = 10


def test_reports_require_auth(base):
    # Sales/customer reports are admin-only; they must not be public.
    r = requests.get(f"{base}/reports/total-sales-per-country", timeout=TIMEOUT)
    assert r.status_code in (401, 403), (
        f"GET /reports/* returned {r.status_code} unauthenticated, expected 401/403 "
        f"(reports must not be public)"
    )


def test_internal_logs_not_public(base):
    # The raw application log must not be exposed via the API.
    r = requests.get(f"{base}/logs/laravel.log", timeout=TIMEOUT)
    assert r.status_code != 200, (
        "GET /logs/laravel.log returned 200 — internal logs are publicly exposed"
    )


def test_login_rejects_sql_injection(base):
    # A classic auth-bypass payload must not yield a token.
    r = requests.post(
        f"{base}/users/login",
        json={"email": "x' OR '1'='1' -- ", "password": "x"},
        timeout=TIMEOUT,
    )
    assert "access_token" not in r.text and r.status_code != 200, (
        "login accepted a SQL-injection payload (auth bypass)"
    )
