"""The agent's tool set: JSON schemas (sent to Claude) + Python implementations.

6 shipped tools + git_blame (stretch). Each TOOL_SCHEMAS entry has a matching
`tool_<name>` implementation. The loop (loop.py) dispatches tool_use blocks here.

Most bodies are scaffolds — see `# TODO(build)`. Wire them to the real test
suite / Toolshop API / Chroma index during the Day-1 "Agent loop" slot.
"""
from __future__ import annotations

from typing import Any

# --------------------------------------------------------------------------
# Tool schemas advertised to Claude. The `description` fields are load-bearing:
# they are how the model decides *when* to call each tool (esp. retrieval).
# --------------------------------------------------------------------------
TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "name": "get_failure_details",
        "description": (
            "Read the full failure record for a test: error type, stack trace, "
            "assertion message, target endpoint, HTTP status, and raw logs. "
            "Call this first to gather your starting evidence."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"test_id": {"type": "string"}},
            "required": ["test_id"],
        },
    },
    {
        "name": "rerun_test",
        "description": (
            "Re-run a single test N times and return the pass/fail tally. Use to "
            "distinguish flaky (mixed results) from deterministic (all fail)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "test_id": {"type": "string"},
                "times": {"type": "integer", "default": 5},
            },
            "required": ["test_id"],
        },
    },
    {
        "name": "search_past_failures",
        "description": (
            "Semantic search over previously-triaged failures by error signature. "
            "Returns similar past failures with their verdict, root cause, and "
            "owner. Use when you need PRECEDENT to judge an ambiguous failure "
            "('have we seen this signature before, and was it flaky?'). You may "
            "call it again with a refined query if the first matches are weak. "
            "Returns matches with similarity scores — low scores mean no strong "
            "precedent exists."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "k": {"type": "integer", "default": 5},
            },
            "required": ["query"],
        },
    },
    {
        "name": "check_contract",
        "description": (
            "Compare the failing test's actual API response against the endpoint's "
            "OpenAPI schema. Returns contract violations (missing/mis-typed/invalid "
            "fields, wrong status code). A clear violation is strong evidence of a "
            "REAL_REGRESSION."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"test_id": {"type": "string"}},
            "required": ["test_id"],
        },
    },
    {
        "name": "check_service_health",
        "description": (
            "Probe a dependency / base URL. Returns whether it is reachable and any "
            "connection-refused / 5xx / auth failure. Use to confirm an ENVIRONMENT "
            "problem rather than a code defect."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"target": {"type": "string"}},
            "required": ["target"],
        },
    },
    {
        "name": "get_test_history",
        "description": (
            "Get this test's pass/fail timeline across recent CI builds, plus how "
            "long it's been failing (age), whether it flip-flops (flaky signal), "
            "when it last passed, and the build it started failing in. THE primary "
            "signal for flaky (flip-flop across builds) vs. regression (freshly "
            "green->red). Suite-specific evidence — prefer it over generic precedent."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"test_id": {"type": "string"}},
            "required": ["test_id"],
        },
    },
    {
        "name": "get_build_summary",
        "description": (
            "Get this build's blast radius: how many tests failed and how many are "
            "NEWLY failing vs the previous build. Many unrelated tests newly failing "
            "=> ENVIRONMENT/infra problem, not a code regression. Call this to tell a "
            "systemic environment failure apart from an isolated regression."
        ),
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_blame",
        "description": (
            "For a freshly-failing test, get the commits in the build where it "
            "started failing (failedSince) — the suspect change set + author. Use "
            "only after concluding REAL_REGRESSION on an isolated failure."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"test_id": {"type": "string"}},
            "required": ["test_id"],
        },
    },
    {
        "name": "submit_triage",
        "description": (
            "Submit the final triage verdict. Call exactly once, last. This ends "
            "the investigation."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "verdict": {
                    "type": "string",
                    "enum": ["FLAKY", "REAL_REGRESSION", "ENVIRONMENT"],
                },
                "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                "evidence": {"type": "array", "items": {"type": "string"}},
                "owner": {"type": "string"},
                "suggested_action": {"type": "string"},
            },
            "required": ["verdict", "confidence", "evidence", "suggested_action"],
        },
    },
    # ---- stretch ---------------------------------------------------------
    # {
    #     "name": "git_blame",
    #     "description": "Author/commit of a line in the TEST repo — use to check "
    #                    "whether the test itself was recently changed (test fault).",
    #     "input_schema": {
    #         "type": "object",
    #         "properties": {"path": {"type": "string"}, "line": {"type": "integer"}},
    #         "required": ["path", "line"],
    #     },
    # },
]


# --------------------------------------------------------------------------
# Implementations. Each returns a JSON-serialisable dict fed back as tool_result.
#
# These read from fixtures/recorded.json (offline demo) so the whole pipeline
# runs with no live app. When you stand up Toolshop and set API_BASE_URL, swap
# the marked bodies to call the real API (see `# LIVE:` notes) — the schemas and
# the loop don't change.
# --------------------------------------------------------------------------
import json
import os

_ROOT = os.path.dirname(os.path.dirname(__file__))
_FIXTURES_PATH = os.path.join(_ROOT, "fixtures", "recorded.json")
_fixtures: dict[str, Any] | None = None

# Live-wired tests: map a test_id to its pytest node, JUnit report, and endpoint.
# When API_BASE_URL is set, get_failure_details parses the real report and
# rerun_test actually re-runs pytest against the live API.
# Optional endpoint labels for nicer traces. The pytest node is derived from the
# report's classname, so tests don't need to be registered here to be triaged.
_LIVE_TEST = {
    "test_categories_parent_id_is_integer": {"endpoint": "GET /categories"},
    "test_patch_product_supported": {"endpoint": "PATCH /products/{id}"},
    "test_products_default_includes_rentals": {"endpoint": "GET /products"},
    "test_delete_product_requires_auth": {"endpoint": "DELETE /products/{id}"},
    "test_invoices_require_auth": {"endpoint": "GET /invoices"},
}


def _report_path() -> str:
    return os.environ.get("TRIAGE_REPORT") or os.path.join(_ROOT, "eval/failures/live.xml")


def _live_test(test_id: str) -> dict | None:
    if os.environ.get("API_BASE_URL") and test_id in _LIVE_TEST:
        return _LIVE_TEST[test_id]
    return None


def _fx(test_id: str) -> dict[str, Any]:
    global _fixtures
    if _fixtures is None:
        with open(_FIXTURES_PATH) as f:
            _fixtures = json.load(f)
    if test_id not in _fixtures:
        raise KeyError(f"No fixture for test_id {test_id!r}; add it to {_FIXTURES_PATH}")
    return _fixtures[test_id]


def _live() -> bool:
    return bool(os.environ.get("API_BASE_URL"))


def tool_get_failure_details(test_id: str) -> dict[str, Any]:
    # LIVE: parse the real JUnit report produced by pytest against the live API.
    # Works for ANY failing test in the report (smoke suite), not just registered
    # ones; a registered endpoint label is added when known.
    if os.environ.get("API_BASE_URL"):
        from eval.report import failure_record

        report = _report_path()
        if os.path.exists(report):
            rec = failure_record(report, test_id)
            if rec:
                rec.update(
                    endpoint=_LIVE_TEST.get(test_id, {}).get("endpoint"),
                    status=None,
                    logs=f"parsed from {os.path.basename(report)} "
                         f"(live run vs {os.environ['API_BASE_URL']})",
                )
                return rec
    return _fx(test_id)["details"]


def tool_rerun_test(test_id: str, times: int = 5) -> dict[str, Any]:
    # LIVE: actually re-run the pytest node `times` times against the live API and
    # tally pass/fail. Node id comes from the registry or the report's classname.
    if os.environ.get("API_BASE_URL"):
        node = _LIVE_TEST.get(test_id, {}).get("node") or _node_from_report(test_id)
        if node:
            return _rerun_live(node, times)
    return _fx(test_id)["rerun"]


def _node_from_report(test_id: str) -> str | None:
    from eval.report import failure_record, node_id

    report = _report_path()
    if not os.path.exists(report):
        return None
    rec = failure_record(report, test_id)
    if rec and rec.get("classname"):
        return node_id(rec["classname"], test_id)
    return None


def _rerun_live(node: str, times: int) -> dict[str, Any]:
    import subprocess
    import sys

    passed = failed = 0
    errors: list[str] = []
    for _ in range(max(1, min(times, 5))):  # cap to keep the demo snappy
        p = subprocess.run(
            [sys.executable, "-m", "pytest", node, "-q", "-p", "no:randomly", "--no-header"],
            cwd=_ROOT, capture_output=True, text=True, env=os.environ.copy(),
        )
        if p.returncode == 0:
            passed += 1
        else:
            failed += 1
            line = next((l.strip() for l in p.stdout.splitlines() if l.startswith("E ")), "")
            if line:
                errors.append(line)
    return {"passed": passed, "failed": failed, "errors": errors[:3]}


def tool_search_past_failures(query: str, k: int = 5) -> dict[str, Any]:
    from rag.retrieve import search  # local import keeps agent import light

    return {"matches": search(query, k=k)}


# Maps a test_id to a live endpoint + the OpenAPI component schema to validate
# its response items against. Used only when API_BASE_URL is set.
_LIVE_CONTRACT = {
    # "schema": validate the response items against an OpenAPI component schema.
    "test_categories_parent_id_is_integer": {
        "type": "schema", "method": "get", "path": "/categories",
        "schema": "CategoryResponse", "array": True,
    },
    # "status": issue the request and check the status code against the contract.
    "test_patch_product_supported": {
        "type": "status", "method": "patch",
        "path": "/products/{first_product_id}", "expected": [200],
        "body": {"price": 1.23},
    },
    "test_delete_product_requires_auth": {
        "type": "status", "method": "delete",
        "path": "/products/{first_product_id}", "expected": [401, 403],
    },
    "test_invoices_require_auth": {
        "type": "status", "method": "get",
        "path": "/invoices", "expected": [401, 403],
    },
}
_spec_cache: dict[str, Any] = {}


def tool_check_contract(test_id: str) -> dict[str, Any]:
    # LIVE: when API_BASE_URL is set and this test maps to an endpoint, hit the
    # real API and validate the response against the live OpenAPI contract.
    base = os.environ.get("API_BASE_URL")
    mapping = _LIVE_CONTRACT.get(test_id)
    if base and mapping:
        return _check_contract_live(base.rstrip("/"), mapping)
    # Offline / fixture mode: replay the recorded violations if we have them.
    if _fixtures is None or test_id in (_load_fixtures()):
        try:
            return _fx(test_id)["contract"]
        except KeyError:
            pass
    return {"endpoint": "n/a", "violations": [],
            "note": "no contract configured for this test; rely on other signals"}


def _load_fixtures() -> dict[str, Any]:
    global _fixtures
    if _fixtures is None:
        with open(_FIXTURES_PATH) as f:
            _fixtures = json.load(f)
    return _fixtures


def _get_spec(base: str) -> dict[str, Any]:
    if base not in _spec_cache:
        import requests

        _spec_cache[base] = requests.get(base + "/docs", timeout=15).json()
    return _spec_cache[base]


def _check_contract_live(base: str, m: dict) -> dict[str, Any]:
    # Robust to a failing/unreachable API (e.g. DB down -> 500/non-JSON): never
    # crash the triage; report that the contract couldn't be checked instead.
    try:
        if m.get("type") == "status":
            return _check_contract_status(base, m)
        return _check_contract_schema(base, m)
    except Exception as e:
        return {
            "endpoint": m.get("path"),
            "source": f"LIVE API ({base})",
            "violations": [],
            "note": f"could not check contract ({type(e).__name__}) — "
                    f"API erroring or unreachable (service may be down)",
        }


def _check_contract_schema(base: str, m: dict) -> dict[str, Any]:
    import requests
    from jsonschema import Draft7Validator, RefResolver

    spec = _get_spec(base)
    schema = spec["components"]["schemas"][m["schema"]]
    validator = Draft7Validator(schema, resolver=RefResolver.from_schema(spec))

    r = requests.get(base + m["path"], timeout=15)
    body = r.json()
    items = body.get("data") if isinstance(body, dict) and "data" in body else body
    items = items if (m.get("array") and isinstance(items, list)) else [items]

    violations = []
    for it in items:
        for e in validator.iter_errors(it):
            violations.append(
                f"id={it.get('id')}: field {list(e.path)} -> {e.message[:80]}"
            )
    return {
        "endpoint": f"{m['method'].upper()} {m['path']}",
        "source": f"LIVE API ({base})",
        "status": r.status_code,
        "checked": len(items),
        "violation_count": len(violations),
        "violations": violations[:5],
    }


def _check_contract_status(base: str, m: dict) -> dict[str, Any]:
    import requests

    path = m["path"]
    if "{first_product_id}" in path:
        pid = requests.get(base + "/products?page=1", timeout=15).json()["data"][0]["id"]
        path = path.replace("{first_product_id}", str(pid))
    r = requests.request(m["method"], base + path, json=m.get("body"), timeout=15)
    if r.status_code >= 500:
        # A server error is an outage signal, not a contract breach — don't let it
        # masquerade as a regression during a widespread environment failure.
        return {
            "endpoint": f"{m['method'].upper()} {m['path']}",
            "source": f"LIVE API ({base})",
            "status": r.status_code,
            "checked": 1,
            "violation_count": 0,
            "violations": [],
            "note": f"{r.status_code} server error — likely environment, not a contract breach",
        }
    ok = r.status_code in m["expected"]
    violations = [] if ok else [
        f"{m['method'].upper()} {path} returned {r.status_code}; "
        f"contract expects {m['expected']}"
    ]
    return {
        "endpoint": f"{m['method'].upper()} {m['path']}",
        "source": f"LIVE API ({base})",
        "status": r.status_code,
        "checked": 1,
        "violation_count": len(violations),
        "violations": violations,
    }


def tool_check_service_health(target: str) -> dict[str, Any]:
    # If `target` names a host (a URL or host:port), actually probe it with a TCP
    # connect — truthful and robust regardless of how the caller phrases it. This
    # is what makes the env scenario deterministic: a dead port genuinely refuses.
    host, port = _parse_host_port(target)
    if host:
        import socket

        try:
            with socket.create_connection((host, port), timeout=1.5):
                return {"target": target, "reachable": True,
                        "detail": f"TCP connect to {host}:{port} succeeded"}
        except OSError as e:
            return {"target": target, "reachable": False,
                    "detail": f"{type(e).__name__}: {e} — dependency unreachable"}

    # Otherwise treat `target` as an endpoint label and match a recorded health.
    with open(_FIXTURES_PATH) as f:
        data = json.load(f)
    for rec in data.values():
        if isinstance(rec, dict) and rec.get("service_health", {}).get("target") == target:
            return rec["service_health"]
    return {"target": target, "reachable": None,
            "detail": "unknown target — could not probe and no recorded health"}


def _parse_host_port(target: str) -> tuple[str | None, int]:
    """Extract (host, port) from a URL or host:port string; else (None, 0)."""
    import re
    from urllib.parse import urlparse

    if "://" in target:
        u = urlparse(target)
        if u.hostname:
            return u.hostname, (u.port or (443 if u.scheme == "https" else 80))
    m = re.fullmatch(r"([\w.-]+):(\d{1,5})", target.strip())
    if m:
        return m.group(1), int(m.group(2))
    return None, 0


def tool_get_test_history(test_id: str) -> dict[str, Any]:
    from agent import jenkins_history

    return jenkins_history.test_history(test_id)


def tool_get_build_summary() -> dict[str, Any]:
    from agent import jenkins_history

    return jenkins_history.build_summary()


def tool_get_blame(test_id: str) -> dict[str, Any]:
    from agent import jenkins_history

    return jenkins_history.blame(test_id)


def tool_submit_triage(**verdict: Any) -> dict[str, Any]:
    # Terminal tool: the loop detects this name and stops, returning `verdict`.
    return verdict


# Dispatch table used by loop.py
TOOL_IMPLS = {
    "get_failure_details": tool_get_failure_details,
    "rerun_test": tool_rerun_test,
    "search_past_failures": tool_search_past_failures,
    "check_contract": tool_check_contract,
    "check_service_health": tool_check_service_health,
    "get_test_history": tool_get_test_history,
    "get_build_summary": tool_get_build_summary,
    "get_blame": tool_get_blame,
    "submit_triage": tool_submit_triage,
}

TERMINAL_TOOL = "submit_triage"
