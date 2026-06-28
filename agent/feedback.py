"""Confirmed-only feedback loop.

Promote OUTCOME-confirmed verdicts into the RAG corpus with provenance, so the
agent learns from reality — never from its own unverified guesses (which would
amplify its own errors).

The cleanest automatic ground truth is **flakiness confirmed by observed
flip-flop**: a test that has flipped pass<->fail across CI builds, with no code
link, IS flaky by definition. We mint a `provenance: confirmed-outcome` record
for it. Over time these grounded, suite-specific records out-vote the generic
synthetic/IDoFT priors (retrieval boosts confirmed provenance).

Run: `python -m agent.feedback`  (in production, post-build, gated on confirmation)

Regression/environment outcome-confirmation (a fix commit followed, or the whole
cohort recovered) is a documented extension — it needs longer outcome tracking.
"""
from __future__ import annotations

import hashlib
import json
import os

from agent import jenkins_history as jh
from rag.normalize import signature_from_failure


def _hid(prefix: str, sig: str) -> str:
    return f"{prefix}-{hashlib.md5(sig.encode()).hexdigest()[:8]}"

CONFIRMED_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "rag", "corpus", "confirmed_records.json"
)


def confirmed_flaky(last_n: int = 10) -> list[dict]:
    """Tests that flip-flopped across recent builds -> outcome-confirmed flaky."""
    builds = jh.list_builds()[-last_n:]
    names: set[str] = set()
    for b in builds:
        names |= set(jh._build(b).keys())

    records = []
    for name in sorted(names):
        h = jh.test_history(name, last_n)
        if h["flip_count"] < 2:
            continue
        err = jh.test_error(name) or {}
        sig = signature_from_failure(
            "AssertionError", err.get("details", ""), None, err.get("stack", "")
        )
        records.append({
            "id": f"CONFIRMED-FLAKY-{name}",
            "signature": sig or f"{name} intermittent failure",
            "verdict": "FLAKY",
            "root_cause": (
                f"NOD: flipped pass<->fail {h['flip_count']}x across CI builds "
                f"with no code link — outcome-confirmed flaky"
            ),
            "owner": "",
            "fix_ref": f"confirmed by CI history (builds {builds[0]}..{builds[-1]})",
            "provenance": "confirmed-outcome",
        })
    return records


def confirmed_environment(last_n: int = 10) -> list[dict]:
    """Cohort recovery: many tests went red together then green together -> a real
    fix can't un-break unrelated tests at once, so it was an environment outage.
    Deduped by signature (a 20-test cohort collapses to a few error shapes)."""
    builds = jh.list_builds()[-last_n:]
    by_sig: dict[str, dict] = {}
    for n_prev, n_cur in zip(builds, builds[1:]):
        if jh.build_summary(n_prev).get("blast_radius") != "widespread":
            continue
        prev, cur = jh._build(n_prev), jh._build(n_cur)
        recovered = [t for t in prev
                     if prev[t]["status"] == "fail" and cur.get(t, {}).get("status") == "pass"]
        for t in recovered:
            err = jh.test_error(t) or {}
            sig = signature_from_failure("Error", err.get("details", ""), None,
                                         err.get("stack", "")) or f"{t} outage failure"
            by_sig[sig] = {
                "id": _hid("CONFIRMED-ENV", sig),
                "signature": sig,
                "verdict": "ENVIRONMENT",
                "root_cause": f"Recovered as a cohort (build {n_prev}->{n_cur}, no targeted "
                              f"change) — outcome-confirmed environment",
                "owner": "", "fix_ref": f"cohort recovery builds {n_prev}->{n_cur}",
                "provenance": "confirmed-outcome",
            }
    return list(by_sig.values())


def confirmed_regression(last_n: int = 10) -> list[dict]:
    """Isolated red->green where a commit landed in the recovery build -> a fix was
    needed, so it was a real regression. NOTE: exact in a monorepo; with a split
    app/test repo the commit signal is an assumption (track the app SHA to be precise)."""
    builds = jh.list_builds()[-last_n:]
    by_sig: dict[str, dict] = {}
    for n_prev, n_cur in zip(builds, builds[1:]):
        if jh.build_summary(n_prev).get("blast_radius") == "widespread":
            continue  # widespread recovery is environment, not a targeted fix
        if not jh._parse_changelog(n_cur):
            continue  # recovered with no code change -> flaky/env, not a confirmed fix
        prev, cur = jh._build(n_prev), jh._build(n_cur)
        recovered = [t for t in prev
                     if prev[t]["status"] == "fail" and cur.get(t, {}).get("status") == "pass"]
        for t in recovered:
            err = jh.test_error(t) or {}
            sig = signature_from_failure("AssertionError", err.get("details", ""), None,
                                         err.get("stack", "")) or f"{t} regression"
            by_sig[sig] = {
                "id": _hid("CONFIRMED-REG", sig),
                "signature": sig,
                "verdict": "REAL_REGRESSION",
                "root_cause": f"Isolated red->green; a commit landed in build {n_cur} "
                              f"(monorepo assumption) — outcome-confirmed regression",
                "owner": "", "fix_ref": f"fixed in build {n_cur}",
                "provenance": "confirmed-outcome",
            }
    return list(by_sig.values())


def ingest(last_n: int = 10) -> list[dict]:
    """Merge ALL confirmed records into rag/corpus/confirmed_records.json (dedup by id)."""
    merged: dict[str, dict] = {}
    if os.path.exists(CONFIRMED_PATH):
        for r in json.load(open(CONFIRMED_PATH)):
            merged[r["id"]] = r
    for fn in (confirmed_flaky, confirmed_environment, confirmed_regression):
        for r in fn(last_n):
            merged[r["id"]] = r
    records = list(merged.values())
    with open(CONFIRMED_PATH, "w") as f:
        json.dump(records, f, indent=2)
    return records


if __name__ == "__main__":
    recs = ingest()
    print(f"{len(recs)} confirmed-outcome record(s) in {os.path.basename(CONFIRMED_PATH)}:")
    for r in recs:
        print(f"  {r['id']}  [{r['provenance']}]  {r['root_cause'][:60]}")
    print("\nRebuild the index to use them:  python -m rag.index")
