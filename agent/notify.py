"""Send one digest email per recipient via SMTP (captured by MailCatcher).

Failures are grouped by who-should-act (bucket-aware routing), so each team gets
a single digest — e.g. "infra: 4 SERVICE_5XX failures" rather than four emails.
SMTP defaults to MailCatcher (localhost:1025); nothing leaves the machine.
Also stamps each result with notified_team/notified_email for the HTML report.
"""
from __future__ import annotations

import os
import smtplib
from collections import defaultdict
from email.mime.text import MIMEText

from agent import routing

SMTP_HOST = os.environ.get("TRIAGE_SMTP_HOST", "localhost")
SMTP_PORT = int(os.environ.get("TRIAGE_SMTP_PORT", "1025"))
FROM_ADDR = "ci-triage@toolshop.local"


def _digest_body(team: str, items: list[dict], build: str | None) -> str:
    lines = [f"CI triage digest for {team} — {len(items)} item(s)"]
    if build:
        lines.append(f"build: {build}")
    lines.append("")
    for r in items:
        cat = f" [{r['env_category']}]" if r.get("env_category") else ""
        lines.append(f"• {r['test_id']} — {r['verdict']}{cat} (confidence {r.get('confidence','?')})")
        lines.append(f"    action: {r.get('suggested_action','')}")
        for e in r.get("evidence", []):
            lines.append(f"    - {e}")
        lines.append("")
    return "\n".join(lines)


def send_digests(results: list[dict], *, build: str | None = None) -> list[dict]:
    """Route + group failures, send one digest per recipient. Returns send summary.
    Mutates each result with notified_team / notified_email for the report."""
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for r in results:
        team, email = routing.route(r)
        r["notified_team"], r["notified_email"] = team, email
        groups[(team, email)].append(r)

    summary = []
    try:
        server = smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=10)
    except Exception as e:
        for (team, email), items in groups.items():
            summary.append({"team": team, "email": email, "count": len(items),
                            "sent": False, "error": f"{type(e).__name__}: {e}"})
        return summary

    with server:
        for (team, email), items in groups.items():
            msg = MIMEText(_digest_body(team, items, build))
            verdicts = ",".join(sorted({i["verdict"] for i in items}))
            msg["Subject"] = f"[CI Triage] {len(items)} {verdicts} issue(s) for {team}"
            msg["From"] = FROM_ADDR
            msg["To"] = email
            try:
                server.sendmail(FROM_ADDR, [email], msg.as_string())
                summary.append({"team": team, "email": email, "count": len(items), "sent": True})
            except Exception as e:
                summary.append({"team": team, "email": email, "count": len(items),
                                "sent": False, "error": str(e)})
    return summary
