"""ENV sub-bucket classification + notification routing.

Two jobs:
  * classify_env_category(): refine an ENVIRONMENT verdict into a bucket from the
    observable error signature (DB unreachable vs app 5xx vs dependency down ...).
  * route(): map a triaged failure to the team + address that should act on it —
    bucket-aware for environment (DB->infra, 5xx->platform, ...), owner-team for
    regressions, QA for flaky.

Recipients point at .local addresses; emails are captured by MailCatcher
(SMTP localhost:1025, web UI localhost:1080), so nothing leaves the machine.
"""
from __future__ import annotations

# --- ENV sub-buckets -------------------------------------------------------
def classify_env_category(error_type: str, message: str) -> str:
    t = f"{error_type} {message}".lower()
    if any(k in t for k in ("operationalerror", "too many connections", "mariadb",
                            "mysql", "sqlstate", "database", ":3306")):
        return "DB_UNREACHABLE"
    if any(k in t for k in ("redis", "queue", "cache", "rabbit", "kafka")) and \
            ("refus" in t or "unavailable" in t or "connection" in t):
        return "DEPENDENCY_DOWN"
    if "connection refused" in t or "connectionrefused" in t or "max retries" in t:
        return "DEPENDENCY_DOWN"
    if any(k in t for k in ("503", "502", "500", "server error", "bad gateway",
                            "internal server")):
        return "SERVICE_5XX"
    if "401" in t or "unauthor" in t or "expired token" in t or "missing token" in t:
        return "AUTH_MISCONFIG"
    if any(k in t for k in ("name or service not known", "dns", "ssl", "certificate",
                            "timed out", "timeout")):
        return "NETWORK_DNS"
    return "UNKNOWN_ENV"


# --- Notification routing ---------------------------------------------------
# verdict / env bucket -> (team label, recipient address)
REGRESSION_DEFAULT = ("dev", "dev-team@toolshop.local")
FLAKY_RECIPIENT = ("qa", "qa-team@toolshop.local")
ENV_ROUTES = {
    "DB_UNREACHABLE": ("dba/infra", "infra-db@toolshop.local"),
    "SERVICE_5XX":    ("platform/sre", "platform-sre@toolshop.local"),
    "DEPENDENCY_DOWN": ("platform", "platform-sre@toolshop.local"),
    "AUTH_MISCONFIG": ("secrets/platform", "platform-sre@toolshop.local"),
    "NETWORK_DNS":    ("network/infra", "infra-net@toolshop.local"),
    "UNKNOWN_ENV":    ("infra", "infra@toolshop.local"),
}

# Map an owner team (from the verdict) to a dev address; fall back to default.
OWNER_EMAILS = {
    "team-catalog": "catalog-dev@toolshop.local",
    "team-billing": "billing-dev@toolshop.local",
    "team-accounts": "accounts-dev@toolshop.local",
    "team-checkout": "checkout-dev@toolshop.local",
}


def route(result: dict) -> tuple[str, str]:
    """Return (team_label, recipient_address) for a triaged failure."""
    verdict = result.get("verdict")
    if verdict == "FLAKY":
        return FLAKY_RECIPIENT
    if verdict == "ENVIRONMENT":
        return ENV_ROUTES.get(result.get("env_category", "UNKNOWN_ENV"),
                              ENV_ROUTES["UNKNOWN_ENV"])
    # REAL_REGRESSION -> the owning dev team
    owner = result.get("owner", "")
    if owner in OWNER_EMAILS:
        return (owner, OWNER_EMAILS[owner])
    return REGRESSION_DEFAULT
