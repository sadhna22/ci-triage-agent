"""A controlled flaky test, for the build-history demo.

It flips pass/fail across CI builds (by build parity) with NO code change — the
hallmark of a flaky test. The triage agent should see the flip-flop in
get_test_history and classify it FLAKY (quarantine), not a regression.

Locally (no BUILD_NUMBER) it passes, so it never disrupts local runs; only in
Jenkins, where BUILD_NUMBER is set, does it alternate.
"""
from __future__ import annotations

import os


def test_intermittent_async_timing():
    build = int(os.environ.get("BUILD_NUMBER", "0") or "0")
    # Simulates an async/timing race that surfaces only on some runs.
    assert build % 2 == 0, (
        f"intermittent timing failure on build {build} "
        f"(flips across builds, no code change)"
    )
