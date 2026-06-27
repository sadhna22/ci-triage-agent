"""triage-agent CLI — the demo surface. The tool-call trace IS the demo.

Usage:
    python cli.py <report.xml>          # triage every failure in a JUnit report
    python cli.py --test <test_id>      # triage a single failure

Streams each tool call + result, then a verdict card per failure.
"""
from __future__ import annotations

import argparse

# Load a local .env (OPENAI_API_KEY, etc.) before anything reads the environment.
try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:
    pass

from rich.console import Console
from rich.panel import Panel

from agent.loop import triage

console = Console()

_ICON = {
    "get_failure_details": "🔧",
    "rerun_test": "🔁",
    "search_past_failures": "📚",
    "check_contract": "📋",
    "check_service_health": "🩺",
    "submit_triage": "✅",
}
_VERDICT_STYLE = {
    "FLAKY": "yellow",
    "REAL_REGRESSION": "red",
    "ENVIRONMENT": "cyan",
}


def _trace(name: str, args: dict, output) -> None:
    if name == "submit_triage":
        return  # rendered as the verdict card instead
    icon = _ICON.get(name, "🔧")
    console.print(f"  {icon} [bold]{name}[/bold]({_fmt_args(args)}) → {_summary(output)}")


def _fmt_args(args: dict) -> str:
    return ", ".join(f"{k}={v!r}" for k, v in args.items())


def _summary(output) -> str:
    # Keep tool results to a single readable line in the trace.
    text = str(output)
    return text if len(text) <= 100 else text[:97] + "..."


def _render_verdict(test_id: str, v: dict) -> None:
    style = _VERDICT_STYLE.get(v["verdict"], "white")
    body = [f"[bold {style}]{v['verdict']}[/]  (confidence {v.get('confidence', '?')})"]
    if v.get("owner"):
        body.append(f"owner → {v['owner']}")
    body.append(f"action: {v.get('suggested_action', '')}")
    if v.get("evidence"):
        body.append("")
        body.extend(f"• {e}" for e in v["evidence"])
    console.print(Panel("\n".join(body), title=test_id, border_style=style))


def triage_one(test_id: str) -> dict:
    console.rule(f"Failure: {test_id}")
    verdict = triage(test_id, trace=_trace)
    _render_verdict(test_id, verdict)
    console.print()
    return {"test_id": test_id, **verdict}


def main() -> None:
    ap = argparse.ArgumentParser(description="CI test-failure triage agent")
    ap.add_argument("report", nargs="?", help="JUnit XML report of failures")
    ap.add_argument("--test", help="triage a single test_id instead of a report")
    ap.add_argument("--out", help="write a JSON triage summary to this path (for CI)")
    args = ap.parse_args()

    results = []
    if args.test:
        results.append(triage_one(args.test))
    elif args.report:
        from eval.report import failing_test_ids

        failures = failing_test_ids(args.report)
        console.print(f"[dim]{len(failures)} failing test(s) in {args.report}[/dim]\n")
        results = [triage_one(t) for t in failures]
    else:
        ap.error("provide a JUnit report path or --test <test_id>")

    if args.out:
        import json
        from collections import Counter

        summary = {
            "total": len(results),
            "by_verdict": dict(Counter(r["verdict"] for r in results)),
            "results": results,
        }
        with open(args.out, "w") as f:
            json.dump(summary, f, indent=2)
        console.print(f"[dim]triage summary written to {args.out}[/dim]")


if __name__ == "__main__":
    main()
