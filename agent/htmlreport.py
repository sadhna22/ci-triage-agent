"""Render a self-contained static HTML triage report.

One file, inline CSS, no server. Shows every failure with its verdict, env
bucket, the justification the agent cited, owner, suggested action, and who was
notified — plus a link to MailCatcher where the actual emails landed.
"""
from __future__ import annotations

import html

_COLOR = {"REAL_REGRESSION": "#c0392b", "FLAKY": "#b8860b", "ENVIRONMENT": "#2471a3"}
MAILCATCHER_URL = "http://localhost:1080"


def _esc(x) -> str:
    return html.escape(str(x))


def render(results: list[dict], path: str, *, build: str | None = None) -> None:
    counts: dict[str, int] = {}
    for r in results:
        counts[r["verdict"]] = counts.get(r["verdict"], 0) + 1
    chips = " ".join(
        f'<span class="chip" style="background:{_COLOR.get(v,"#555")}">{_esc(v)}: {n}</span>'
        for v, n in sorted(counts.items())
    )

    rows = []
    for r in results:
        v = r["verdict"]
        color = _COLOR.get(v, "#555")
        bucket = f' <span class="bucket">{_esc(r["env_category"])}</span>' if r.get("env_category") else ""
        evidence = "".join(f"<li>{_esc(e)}</li>" for e in r.get("evidence", []))
        team, email = r.get("notified_team", ""), r.get("notified_email", "")
        notified = f'✉ {_esc(team)} &lt;{_esc(email)}&gt;' if email else "—"
        rows.append(f"""
        <tr>
          <td class="mono">{_esc(r["test_id"])}</td>
          <td><span class="verdict" style="background:{color}">{_esc(v)}</span>{bucket}</td>
          <td>{_esc(r.get("confidence",""))}</td>
          <td class="just"><ul>{evidence}</ul></td>
          <td>{_esc(r.get("owner",""))}</td>
          <td>{_esc(r.get("suggested_action",""))}</td>
          <td class="mono small">{notified}</td>
        </tr>""")

    head = f"build {_esc(build)}" if build else ""
    doc = f"""<!doctype html><html><head><meta charset="utf-8">
<title>CI Triage Report</title>
<style>
 body{{font:14px/1.5 -apple-system,Segoe UI,Roboto,sans-serif;margin:24px;color:#222}}
 h1{{margin:0 0 4px}} .sub{{color:#666;margin-bottom:14px}}
 .chip,.verdict{{color:#fff;border-radius:4px;padding:2px 8px;font-size:12px;font-weight:600}}
 .chip{{margin-right:6px}}
 .bucket{{background:#ddd;color:#333;border-radius:4px;padding:1px 6px;font-size:11px;margin-left:6px}}
 table{{border-collapse:collapse;width:100%;margin-top:10px}}
 th,td{{border-bottom:1px solid #eee;padding:8px;text-align:left;vertical-align:top}}
 th{{background:#fafafa;font-size:12px;text-transform:uppercase;color:#666}}
 .mono{{font-family:ui-monospace,Menlo,monospace}} .small{{font-size:12px}}
 .just ul{{margin:0;padding-left:16px}} .just li{{margin:1px 0}}
 a{{color:#2471a3}}
</style></head><body>
<h1>CI Test-Failure Triage</h1>
<div class="sub">{head} &middot; {len(results)} failure(s) triaged &middot; {chips}
 &middot; <a href="{MAILCATCHER_URL}" target="_blank">view sent emails (MailCatcher)</a></div>
<table>
 <tr><th>Test</th><th>Verdict</th><th>Conf.</th><th>Justification</th>
     <th>Owner</th><th>Suggested action</th><th>Notified</th></tr>
 {''.join(rows)}
</table>
</body></html>"""
    with open(path, "w") as f:
        f.write(doc)
