"""Parse a JUnit XML report into the list of failing test_ids.

This is the only thing tying us to "CI" — a JUnit report is exactly what any CI
(GitHub Actions, Jenkins, GitLab) emits, and what `pytest --junitxml` produces.
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET


def failing_test_ids(xml_path: str) -> list[str]:
    """Return test names that have a <failure> or <error> child."""
    root = ET.parse(xml_path).getroot()
    ids = []
    for case in root.iter("testcase"):
        if case.find("failure") is not None or case.find("error") is not None:
            ids.append(case.get("name"))
    return ids


def failure_record(xml_path: str, test_id: str) -> dict | None:
    """Extract a structured failure record for one test from a JUnit report."""
    root = ET.parse(xml_path).getroot()
    for case in root.iter("testcase"):
        if case.get("name") != test_id:
            continue
        node = case.find("failure")
        if node is None:
            node = case.find("error")
        if node is None:
            return None  # test passed
        message = node.get("message", "") or ""
        stack = (node.text or "").strip()
        return {
            "name": test_id,
            "classname": case.get("classname", ""),
            "error_type": _error_type(stack or message, node.tag),
            "message": message.splitlines()[0] if message else "",
            "stack": stack,
        }
    return None


def node_id(classname: str, name: str) -> str:
    """Reconstruct a pytest node id from a JUnit classname + test name.

    'suite.test_smoke' + 'test_x' -> 'suite/test_smoke.py::test_x'
    """
    return classname.replace(".", "/") + ".py::" + name


_ERR_RE = re.compile(r"\b([A-Z]\w*(?:Error|Exception|Failure))\b")


def _error_type(text: str, tag: str) -> str:
    m = _ERR_RE.search(text or "")
    if m:
        return m.group(1)
    return "AssertionError" if tag == "failure" else "Error"
