"""Read build history straight from Jenkins' on-disk job storage.

No API token needed: Jenkins writes every build's results and SCM changelog under
$JENKINS_HOME/jobs/<job>/builds/<n>/. We read:
  * junitResult.xml  -> per-test status + `failedSince` (first failing build)
  * changelog*.xml   -> git commits in that build (for blame)
  * build.xml        -> overall build result

This powers the temporal, suite-specific signals (the primary evidence for
flaky vs. regression vs. environment): a test's pass/fail timeline, how long it's
been failing, build-level blast radius, and the commits in the first failing build.
"""
from __future__ import annotations

import os
import re
import xml.etree.ElementTree as ET

JENKINS_HOME = os.environ.get("JENKINS_HOME", os.path.expanduser("~/.jenkins"))
JOB = os.environ.get("JENKINS_JOB", "ci-triage-agent")


def _builds_dir() -> str:
    return os.path.join(JENKINS_HOME, "jobs", JOB, "builds")


def list_builds() -> list[int]:
    """Build numbers that have JUnit results, oldest→newest."""
    d = _builds_dir()
    if not os.path.isdir(d):
        return []
    nums = []
    for name in os.listdir(d):
        if name.isdigit() and os.path.exists(os.path.join(d, name, "junitResult.xml")):
            nums.append(int(name))
    return sorted(nums)


def latest_build() -> int | None:
    builds = list_builds()
    return builds[-1] if builds else None


def _parse_build(n: int) -> dict[str, dict]:
    """test_id -> {status: pass|fail|skip, failed_since: int, classname: str}."""
    path = os.path.join(_builds_dir(), str(n), "junitResult.xml")
    out = {}
    for case in ET.parse(path).getroot().findall(".//case"):
        name = case.findtext("testName")
        if not name:
            continue
        failed = case.find("errorStackTrace") is not None or case.find("errorDetails") is not None
        skipped = (case.findtext("skipped") or "false") == "true"
        out[name] = {
            "status": "skip" if skipped else ("fail" if failed else "pass"),
            "failed_since": int(case.findtext("failedSince") or 0),
            "classname": case.findtext("className") or "",
        }
    return out


# Cache parsed builds within a process (builds are immutable once written).
_cache: dict[int, dict] = {}


def _build(n: int) -> dict:
    if n not in _cache:
        _cache[n] = _parse_build(n)
    return _cache[n]


def test_history(test_id: str, last_n: int = 10) -> dict:
    """Per-test timeline + derived signals across the most recent builds."""
    builds = list_builds()[-last_n:]
    timeline = []
    for b in builds:
        case = _build(b).get(test_id)
        timeline.append({"build": b, "status": case["status"] if case else "absent"})

    ran = [t for t in timeline if t["status"] in ("pass", "fail")]
    flips = sum(
        1 for a, b in zip(ran, ran[1:]) if a["status"] != b["status"]
    )
    latest = builds[-1] if builds else None
    latest_case = _build(latest).get(test_id) if latest else None
    currently_failing = bool(latest_case and latest_case["status"] == "fail")
    failed_since = latest_case["failed_since"] if latest_case else 0
    last_green = max(
        (t["build"] for t in timeline if t["status"] == "pass"), default=None
    )
    age = (latest - failed_since + 1) if (currently_failing and failed_since) else 0

    return {
        "test_id": test_id,
        "timeline": timeline,
        "currently_failing": currently_failing,
        "failed_since_build": failed_since or None,
        "age_builds": age,            # consecutive failing builds
        "flip_count": flips,          # pass<->fail transitions (flakiness)
        "last_green_build": last_green,
        "history_hint": _hint(flips, age, last_green, currently_failing),
    }


def _hint(flips, age, last_green, failing) -> str:
    if not failing:
        return "not currently failing"
    if flips >= 2:
        return "FLIP-FLOP across builds -> flaky-shaped"
    if age == 1:
        return "freshly failing (green->red this build) -> regression-shaped"
    return f"failing for {age} consecutive builds -> chronic"


def test_error(test_id: str) -> dict | None:
    """Most recent failure's error text for a test (for building a signature)."""
    for b in reversed(list_builds()):
        path = os.path.join(_builds_dir(), str(b), "junitResult.xml")
        for case in ET.parse(path).getroot().findall(".//case"):
            if case.findtext("testName") == test_id and case.find("errorStackTrace") is not None:
                return {
                    "build": b,
                    "details": case.findtext("errorDetails") or "",
                    "stack": case.findtext("errorStackTrace") or "",
                    "classname": case.findtext("className") or "",
                }
    return None


def build_summary(n: int | None = None) -> dict:
    """Build-level blast radius: how much of the suite newly broke this build."""
    n = n or latest_build()
    if n is None:
        return {"error": "no builds with results"}
    cur = _build(n)
    failed = [t for t, c in cur.items() if c["status"] == "fail"]
    newly = [t for t in failed if cur[t]["failed_since"] == n]
    total = len(cur)
    # Widespread = many unrelated tests newly red at once -> environment-shaped.
    widespread = len(newly) >= max(5, int(0.25 * total))
    return {
        "build": n,
        "total_tests": total,
        "failed": len(failed),
        "newly_failing": len(newly),
        "newly_failing_tests": newly,
        "chronic_failing": len(failed) - len(newly),
        "blast_radius": "widespread" if widespread else "isolated",
        "blast_radius_hint": (
            "many unrelated tests newly failed -> ENVIRONMENT-shaped"
            if widespread else
            "few/isolated new failures -> per-test analysis (regression-shaped)"
        ),
    }


def blame(test_id: str) -> dict:
    """Commits in the build where this test started failing (suspects, not proof)."""
    hist = test_history(test_id)
    since = hist["failed_since_build"]
    if not since:
        return {"failed_since_build": None, "suspect_commits": [],
                "note": "test not currently failing"}
    commits = _parse_changelog(since)
    return {
        "failed_since_build": since,
        "suspect_commits": commits,
        "note": "commits in the first failing build — suspects for a human to confirm, not proof",
    }


def _parse_changelog(n: int) -> list[dict]:
    d = os.path.join(_builds_dir(), str(n))
    files = [f for f in os.listdir(d) if f.startswith("changelog")] if os.path.isdir(d) else []
    if not files:
        return []
    text = open(os.path.join(d, files[0])).read()
    commits, cur = [], None
    for line in text.splitlines():
        if line.startswith("commit "):
            cur = {"sha": line.split()[1][:10], "author": "", "message": "", "files": []}
            commits.append(cur)
        elif cur is None:
            continue
        elif line.startswith("author "):
            m = re.match(r"author (.+?) <(.+?)>", line)
            if m:
                cur["author"] = m.group(1)
        elif line.startswith("    ") and not cur["message"]:
            cur["message"] = line.strip()
        elif line.startswith(":"):
            parts = line.split("\t")
            if len(parts) > 1:
                cur["files"].append(parts[-1])
    return commits
