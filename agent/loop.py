"""The agent loop — provider-pluggable, ~transparent, no framework.

Three interchangeable backends, same tools, same trace callback:

  * replay   — a deterministic rule-based driver over the REAL tools. No API key.
               Runs today and is the demo-day insurance policy (if wifi/API dies,
               you still get a flawless run). It encodes the same policy prose the
               LLM is given, so the traces match.
  * openai   — real LLM tool-calling loop on your OpenAI key (default when set).
  * anthropic— same loop shape on an Anthropic key (drop-in; design is vendor
               agnostic — a good interview point).

Selection: $TRIAGE_MODE forces one; otherwise prefer OpenAI (if OPENAI_API_KEY),
then Anthropic (if ANTHROPIC_API_KEY), else replay so it ALWAYS runs.

`trace(name, args, output)` is invoked per tool call so the CLI can render the
tool-call trace (the trace IS the demo).
"""
from __future__ import annotations

import json
import os
from typing import Any, Callable

from agent.prompts import SYSTEM_PROMPT
from agent.tools import TERMINAL_TOOL, TOOL_IMPLS, TOOL_SCHEMAS
from rag.normalize import signature_from_failure

OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")   # bump to gpt-4o for max reasoning
ANTHROPIC_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-6")
MAX_STEPS = 12

Trace = Callable[[str, dict, Any], None]


def select_mode() -> str:
    mode = os.environ.get("TRIAGE_MODE")
    if mode:
        return mode
    if os.environ.get("OPENAI_API_KEY"):
        return "openai"
    if os.environ.get("ANTHROPIC_API_KEY"):
        return "anthropic"
    return "replay"


def triage(test_id: str, *, trace: Trace | None = None) -> dict[str, Any]:
    """Triage one failing test; returns the submit_triage verdict dict."""
    mode = select_mode()
    if mode == "replay":
        return _replay_triage(test_id, trace)
    if mode == "openai":
        return _openai_triage(test_id, trace)
    if mode == "anthropic":
        return _anthropic_triage(test_id, trace)
    raise ValueError(f"Unknown TRIAGE_MODE={mode!r}")


# --------------------------------------------------------------------------
# Shared helpers
# --------------------------------------------------------------------------
def _run_tool(name: str, args: dict, trace: Trace | None) -> Any:
    out = TOOL_IMPLS[name](**args)
    if trace:
        trace(name, args, out)
    return out


_ACTION = {
    "FLAKY": "quarantine test; do not block the build",
    "REAL_REGRESSION": "block the build; assign owner; file a bug",
    "ENVIRONMENT": "route to infra; do not block on application code",
}


# --------------------------------------------------------------------------
# Backend 1: deterministic rule-based driver (no API key)
# --------------------------------------------------------------------------
def _replay_triage(test_id: str, trace: Trace | None) -> dict[str, Any]:
    details = _run_tool("get_failure_details", {"test_id": test_id}, trace)
    err = (details.get("error_type") or "").lower()
    msg = (details.get("message") or "").lower()
    query = signature_from_failure(
        details.get("error_type", ""), details.get("message", ""),
        details.get("endpoint"), details.get("stack"),
    )

    # --- 1. ENVIRONMENT: connection/network failure (cheap, hard signal) ---
    if "connection" in err or "refused" in msg or "timed out" in msg:
        target = os.environ.get("API_BASE_URL") or details.get("endpoint", "")
        health = _run_tool("check_service_health", {"target": target}, trace)
        if not health.get("reachable", True):
            return _verdict(
                test_id, "ENVIRONMENT", 0.9, "team-platform",
                [f"{details.get('error_type')}: dependency unreachable",
                 f"service health: {health.get('detail','')}"], trace)

    # --- 2. BUILD-HISTORY path: temporal, suite-specific evidence (primary) -
    history = _run_tool("get_test_history", {"test_id": test_id}, trace)
    if history.get("currently_failing"):
        summary = _run_tool("get_build_summary", {}, trace)

        # 2a. Large blast radius -> ENVIRONMENT prior (bias, NOT veto:
        #     a concrete contract violation still escalates to regression).
        if summary.get("blast_radius") == "widespread":
            contract = _run_tool("check_contract", {"test_id": test_id}, trace)
            if contract.get("violations"):
                return _regression(test_id, details, contract, history, trace)
            return _verdict(
                test_id, "ENVIRONMENT", 0.85, "team-platform",
                [summary.get("blast_radius_hint", ""),
                 f"{summary.get('newly_failing')} of {summary.get('total_tests')} "
                 f"tests newly failing this build"], trace)

        # 2b. Flip-flop across builds -> FLAKY (strongest flaky evidence)
        if history.get("flip_count", 0) >= 2:
            return _verdict(
                test_id, "FLAKY", 0.9, _guess_owner(details),
                [history.get("history_hint", ""),
                 f"flipped {history['flip_count']}x across recent builds (no code link)"],
                trace)

        # 2c. Isolated failure -> regression; contract confirms, blame names culprit
        contract = _run_tool("check_contract", {"test_id": test_id}, trace)
        return _regression(test_id, details, contract, history, trace)

    # --- 3. COLD START (no CI history): rerun + RAG prior -------------------
    rerun = _run_tool("rerun_test", {"test_id": test_id, "times": 5}, trace)
    passed, failed = rerun.get("passed", 0), rerun.get("failed", 0)

    if passed > 0 and failed > 0:
        matches = _run_tool("search_past_failures", {"query": query, "k": 3}, trace)["matches"]
        if _has_strong(matches, "FLAKY"):
            return _verdict(
                test_id, "FLAKY", 0.85, _top_owner(matches, "FLAKY") or _guess_owner(details),
                [f"re-run mixed: {passed} pass / {failed} fail (non-deterministic)",
                 _precedent_note(matches, "FLAKY")], trace)

    if failed > 0 and passed == 0:
        contract = _run_tool("check_contract", {"test_id": test_id}, trace)
        if contract.get("violations"):
            return _verdict(
                test_id, "REAL_REGRESSION", 0.92, _guess_owner(details),
                [f"re-run deterministic: {failed} fail / 0 pass",
                 "contract violation: " + "; ".join(contract["violations"])], trace)
        matches = _run_tool("search_past_failures", {"query": query, "k": 3}, trace)["matches"]
        verdict = _majority(matches) or "REAL_REGRESSION"
        return _verdict(test_id, verdict, 0.7, _top_owner(matches, verdict) or _guess_owner(details),
                        [f"re-run deterministic: {failed} fail (no CI history)",
                         _precedent_note(matches, verdict)], trace)

    matches = _run_tool("search_past_failures", {"query": query, "k": 3}, trace)["matches"]
    verdict = _majority(matches) or "FLAKY"
    return _verdict(test_id, verdict, 0.6, _top_owner(matches, verdict) or "unknown",
                    ["inconclusive local signal", _precedent_note(matches, verdict)], trace)


def _regression(test_id, details, contract, history, trace) -> dict[str, Any]:
    """Build a REAL_REGRESSION verdict, enriched with history + blame."""
    evidence = []
    if contract.get("violations"):
        evidence.append("contract violation: " + "; ".join(contract["violations"]))
    if history.get("history_hint"):
        evidence.append("history: " + history["history_hint"])
    blame = _run_tool("get_blame", {"test_id": test_id}, trace)
    commits = blame.get("suspect_commits") or []
    if commits:
        c = commits[0]
        evidence.append(
            f"first failed in build #{blame.get('failed_since_build')}; "
            f"suspect {c['sha']} by {c['author']} — {c['message'][:50]}"
        )
    conf = 0.92 if contract.get("violations") else 0.8
    return _verdict(test_id, "REAL_REGRESSION", conf, _guess_owner(details), evidence, trace)


def _verdict(test_id, verdict, confidence, owner, evidence, trace) -> dict[str, Any]:
    out = {
        "verdict": verdict,
        "confidence": confidence,
        "evidence": [e for e in evidence if e],
        "owner": owner,
        "suggested_action": _ACTION[verdict],
    }
    return _run_tool("submit_triage", out, trace)


def _has_strong(matches, verdict) -> bool:
    return any(m["strong_precedent"] and m["verdict"] == verdict for m in matches)


def _top_owner(matches, verdict) -> str | None:
    for m in matches:
        if m["verdict"] == verdict and m.get("owner"):
            return m["owner"]
    return None


def _precedent_note(matches, verdict) -> str:
    hits = [m for m in matches if m["verdict"] == verdict and m["strong_precedent"]]
    if not hits:
        return "no strong precedent found"
    top = hits[0]
    return (f"precedent: {len(hits)} similar past {verdict} "
            f"(e.g. {top['id']} sim={top['similarity']}, {top['root_cause'][:50]})")


def _majority(matches):
    from collections import Counter
    strong = [m["verdict"] for m in matches if m["strong_precedent"]]
    return Counter(strong).most_common(1)[0][0] if strong else None


def _guess_owner(details) -> str:
    ep = (details.get("endpoint") or "").lower()
    if "product" in ep or "categor" in ep:
        return "team-catalog"
    if "cart" in ep or "checkout" in ep or "payment" in ep:
        return "team-checkout"
    if "user" in ep or "login" in ep:
        return "team-accounts"
    if "invoice" in ep:
        return "team-billing"
    return "unassigned"


# --------------------------------------------------------------------------
# Backend 2: OpenAI tool-calling loop
# --------------------------------------------------------------------------
def _openai_tools() -> list[dict]:
    return [
        {"type": "function", "function": {
            "name": t["name"], "description": t["description"],
            "parameters": t["input_schema"]}}
        for t in TOOL_SCHEMAS
    ]


def _openai_triage(test_id: str, trace: Trace | None) -> dict[str, Any]:
    from openai import OpenAI

    client = OpenAI()
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"Triage the failing test: {test_id}"},
    ]
    tools = _openai_tools()

    for _ in range(MAX_STEPS):
        resp = client.chat.completions.create(
            model=OPENAI_MODEL, messages=messages, tools=tools, tool_choice="auto",
        )
        msg = resp.choices[0].message
        messages.append(msg.model_dump(exclude_none=True))

        if not msg.tool_calls:
            messages.append({"role": "user", "content": "Call submit_triage with your verdict."})
            continue

        for tc in msg.tool_calls:
            args = json.loads(tc.function.arguments or "{}")
            output = _run_tool(tc.function.name, args, trace)
            if tc.function.name == TERMINAL_TOOL:
                return output
            messages.append({
                "role": "tool", "tool_call_id": tc.id,
                "content": json.dumps(output, default=str),
            })
    raise RuntimeError(f"No verdict after {MAX_STEPS} steps for {test_id}")


# --------------------------------------------------------------------------
# Backend 3: Anthropic tool-calling loop (drop-in; vendor-agnostic design)
# --------------------------------------------------------------------------
def _anthropic_triage(test_id: str, trace: Trace | None) -> dict[str, Any]:
    import anthropic

    client = anthropic.Anthropic()
    messages = [{"role": "user", "content": f"Triage the failing test: {test_id}"}]

    for _ in range(MAX_STEPS):
        resp = client.messages.create(
            model=ANTHROPIC_MODEL, max_tokens=1024, system=SYSTEM_PROMPT,
            tools=[{"name": t["name"], "description": t["description"],
                    "input_schema": t["input_schema"]} for t in TOOL_SCHEMAS],
            messages=messages,
        )
        messages.append({"role": "assistant", "content": resp.content})
        tool_uses = [b for b in resp.content if b.type == "tool_use"]
        if not tool_uses:
            messages.append({"role": "user", "content": "Call submit_triage with your verdict."})
            continue
        results = []
        for tu in tool_uses:
            output = _run_tool(tu.name, tu.input, trace)
            if tu.name == TERMINAL_TOOL:
                return output
            results.append({"type": "tool_result", "tool_use_id": tu.id,
                            "content": json.dumps(output, default=str)})
        messages.append({"role": "user", "content": results})
    raise RuntimeError(f"No verdict after {MAX_STEPS} steps for {test_id}")
