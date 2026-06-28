# Triage Agent

An **agentic CI test-failure triage tool**. Given a failing test, it decides
**flaky vs. real regression vs. environment**, explains its reasoning from real
evidence (re-runs, API-contract checks, dependency health), names a likely owner,
and recommends an action. It consults a corpus of past triaged failures via
**RAG — but only when it judges it needs precedent** (retrieval is a tool the
agent chooses, not a forced pre-step).

> Full design & rationale: **[DESIGN.md](./DESIGN.md)**

## Quickstart (runs offline, no key)
```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m rag.index                      # build the Chroma index (downloads MiniLM once)

# Replay mode — deterministic, no API key. The whole demo, offline:
TRIAGE_MODE=replay python cli.py eval/failures/failures.xml
TRIAGE_MODE=replay python -m eval.run_eval    # per-class accuracy
```

## Run it as a real LLM agent (your OpenAI key)
Set the key **once** in a local `.env` (auto-loaded; gitignored):
```bash
cp .env.example .env
# edit .env -> OPENAI_API_KEY=sk-...
python cli.py eval/failures/failures.xml     # auto-selects the openai backend
python -m eval.run_eval                       # real per-class accuracy
```
Prefer not to use a file? Either works too:
```bash
export OPENAI_API_KEY=sk-...        # whole shell session
OPENAI_API_KEY=sk-... python -m eval.run_eval   # one command only
```
Have an Anthropic key instead? Put `ANTHROPIC_API_KEY=...` in `.env` (and
`pip install anthropic`) — the loop is vendor-agnostic and switches automatically.

## Three run modes (auto-selected; override with `TRIAGE_MODE`)
| Mode | When | What it is |
|------|------|-----------|
| `replay` | no key (default fallback) | deterministic **rule-based driver over the real tools** — demo-day insurance; needs nothing |
| `openai` | `OPENAI_API_KEY` set | real LLM tool-calling loop (GPT-4o) |
| `anthropic` | `ANTHROPIC_API_KEY` set | same loop on Claude — drop-in |

## How it works (30s)
```
failure report ─▶ agent loop ─▶ [ get_failure_details · rerun_test ·
                                   search_past_failures(RAG) · check_contract ·
                                   check_service_health ] ─▶ submit_triage
```
- **Retrieval-as-a-tool:** the agent calls `search_past_failures` only when it
  lacks decisive local signal.
- **Normalized signatures:** we embed a noise-stripped failure *signature*, not
  raw logs, so identical failures cluster (`rag/normalize.py`).
- **Threshold-gated retrieval:** low similarity ⇒ "no precedent" ⇒ fall back to
  contract/health checks.

## Fixtures vs. live
The 5 tools read from `fixtures/recorded.json` so the pipeline runs with **no live
app**. Set `API_BASE_URL` to switch marked tool bodies to real API calls —
schemas and loop are unchanged.

### Live demo against a LOCAL with-bugs Toolshop (docker)
For the live tests, **three tools are real** (gated on `API_BASE_URL`):
- `get_failure_details` parses the actual JUnit report from the live pytest run,
- `rerun_test` re-runs the pytest node ×N against the live API and tallies,
- `check_contract` validates the live response against the API's own OpenAPI spec
  (schema check) or asserts the status code (status check).

**Set up the local with-bugs instance** (in your `practice-software-testing` clone):
```bash
echo "SPRINT=sprint5-with-bugs" > .env
docker compose up -d
docker compose exec laravel-api composer install
docker compose exec laravel-api php artisan migrate:fresh --seed
docker compose exec laravel-api php artisan l5-swagger:generate
# API now at http://localhost:8091
```
Point the agent at it (already in this repo's `.env`): `API_BASE_URL=http://localhost:8091`.

```bash
# 1) run the API smoke suite against the local buggy app -> one JUnit report
pytest suite/ -p no:randomly --junitxml=eval/failures/live.xml
#    31 checks across 7 resources: 28 pass, 3 fail on planted bugs
#    (the SAME suite is 31/31 GREEN against the clean sprint5 baseline)

# 2) the agent triages every failure, hitting localhost:8091 live
python cli.py eval/failures/live.xml
```
The suite (`suite/`) is a realistic API sanity/regression suite across **products,
categories, brands, users, invoices, favorites, contact**. It is **green on the
clean `sprint5` baseline** and red only on genuine defects — against
`sprint5-with-bugs`, **three checks fail on genuinely planted defects** (confirmed
by diffing `sprint5/API` vs `sprint5-with-bugs/API`, *and* by the clean baseline):

| Failing check | Planted bug | Caught by |
|---|---|---|
| `test_patch_product_supported` | `PATCH /products/{id}` → 405 (handler deleted) | `check_contract` (status) |
| `test_delete_product_requires_auth` | unauth `DELETE` → 409 not 401 (`role:admin` middleware removed) | `check_contract` (status) |
| `test_invoices_require_auth` | unauth `GET /invoices` → 200 (leaks billing data) | `check_contract` (status) |

The agent triages all three as `REAL_REGRESSION`, live. New failures need no
wiring — `get_failure_details`/`rerun_test` derive everything from the report.

> Validating the suite against the clean baseline caught **false-positive tests**
> (e.g. a "rentals hidden" check that flagged intended behavior) — those were
> fixed so a *correct* app is fully green. A test that fails on a correct app is a
> broken test.

To run against the **hosted** with-bugs instead of docker, set
`API_BASE_URL=https://api-with-bugs.practicesoftwaretesting.com`.

## Embeddings: local, with a fallback
Primary is `sentence-transformers` MiniLM (offline). If torch isn't installed,
retrieval transparently falls back to a pure-Python hashing embedder so the
pipeline still runs (`rag/embedder.py`).

## Status — working end to end
`replay` mode: 3 scenario traces + 9/9 per-class eval, fully offline. `openai`
mode: add your key. The only build-out left is pointing the tools at a live
Toolshop (`# LIVE:` markers in `agent/tools.py`) — fixtures stand in until then.
