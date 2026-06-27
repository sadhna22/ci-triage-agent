"""Normalize a raw failure into a stable *signature* for embedding.

THE key RAG detail: we do NOT embed raw stack traces. Line numbers, timestamps,
hex addresses, UUIDs, and ports differ on every run, so semantically-identical
failures would never match. We strip that run-specific noise and keep the stable
shape (error type + frames + endpoint + assertion), so identical failures cluster.

This is implemented enough to be useful out of the box — extend the patterns as
real Toolshop failures reveal new noise.
"""
from __future__ import annotations

import re

# Order matters: most-specific first.
_NOISE_PATTERNS: list[tuple[str, str]] = [
    (r"0x[0-9a-fA-F]+", "<addr>"),                                   # memory addresses
    (r"\b[0-9a-fA-F]{8}-(?:[0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12}\b", "<uuid>"),
    (r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?Z?", "<ts>"),  # ISO timestamps
    (r":\d{2,5}\b", ":<port>"),                                      # :8091 etc.
    (r"\bline \d+\b", "line <n>"),                                   # "line 42"
    (r":\d+\b", ":<n>"),                                             # file:123
    (r"\b\d+\b", "<num>"),                                           # remaining ints
]


def normalize(raw: str) -> str:
    """Collapse run-specific noise so equivalent failures map to one signature."""
    sig = raw.strip()
    for pattern, repl in _NOISE_PATTERNS:
        sig = re.sub(pattern, repl, sig)
    sig = re.sub(r"\s+", " ", sig)  # collapse whitespace
    return sig


def signature_from_failure(
    error_type: str, message: str, endpoint: str | None, stack: str | None = None
) -> str:
    """Build the embedded signature from a structured failure record."""
    parts = [error_type, message]
    if endpoint:
        parts.append(f"@ {endpoint}")
    if stack:
        # keep only the top few frames; they carry the stable shape
        parts.append(" | ".join(stack.splitlines()[:3]))
    return normalize(" ".join(parts))
