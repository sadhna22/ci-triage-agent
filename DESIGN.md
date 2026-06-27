# CI Test-Failure Triage Agent — Design

> An agentic tool that triages failing CI tests: it decides **flaky vs. real
> regression vs. environment**, explains its reasoning from real evidence, names
> a likely owner, and recommends an action. Retrieval over a corpus of past
> triaged failures is **one tool the agent chooses to call** — not a forced
> pre-step.

Built as a 2-day, fully-offline, demoable prototype for a senior SDET interview.

---

## 1. Problem & why it's worth building

Every team drowns in red builds, and a human wastes real time per failure asking
the same three questions:

1. Is this **flaky** (quarantine, don't block) ?
2. Is this a **real regression** (block the build, find the owner) ?
3. Is this an **environment/config** problem (not a code bug at all) ?

This agent automates that first-line triage. It is universally applicable — every
company with CI has this pain.

### Why it's genuinely *agentic* (not a chatbot + vector store)
The agent must **take actions and branch on their results**: re-run a test,
compare a response to its API contract, check a dependency's health, consult
history. The verdict depends on what those tools return — it cannot be answered
in one shot.

### Why RAG is **load-bearing** (not decorative)
"Have we seen this failure before, and was it flaky?" is a **semantic-similarity**
problem over historical failures whose text never matches verbatim (line numbers,
timestamps, UUIDs all differ). That is exactly what embeddings solve and a `WHERE`
clause cannot.

---

## 2. Key design decisions (locked)

| Decision | Choice | Why |
|---|---|---|
| Problem domain | CI test-failure triage | Most credible SDET war-story; agent loop + RAG both undeniable |
| Host app | **Toolshop** (`testsmith-io/practice-software-testing`), `with-bugs` variant | Real, recognizable automation target with **documented intentional bugs** → real regressions + ground-truth labels |
| Run mode | **Local docker** (`with-bugs` image); hosted = fallback only | Offline, deterministic, no live-demo wifi/3rd-party dependency |
| Stack | **Python + pytest** | Lowest-friction agent/RAG/embeddings ecosystem; role isn't Java-specific |
| Agent framework | **Raw, provider-pluggable tool-use loop** (~80 lines/backend) — OpenAI default, Anthropic drop-in, replay fallback | Total transparency; defensible on a whiteboard; no framework "magic"; vendor-agnostic is itself a talking point |
| Retrieval | **Retrieval-as-a-tool** — agent decides when to call it | Enables multi-hop queries + legitimate *skipping*; stronger story than forced RAG |
| Regression smoking gun | **OpenAPI contract comparison** (primary) + `git_blame` (stretch) | API-native; needs no repo ownership |
| Embeddings | **Local `all-MiniLM-L6-v2`** (sentence-transformers) | Free, offline, deterministic; matches docker decision |
| Vector store | **Chroma** | Real, lightweight, persistent, in-process |
| What we embed | **Normalized failure signature**, not raw logs | Identical failures cluster despite run-specific noise — the difference between RAG that works and RAG that demos once |
| Retrieval gating | **top-k with a similarity threshold** | Lets the agent conclude "no strong precedent" and fall back to other tools |
| Demo surface | **CLI with a rich tool-call trace** + end summary | The trace *is* the demo; near-zero UI risk |
| Eval | **~10 labeled failures, per-class accuracy, corpus ⊥ eval** | "I built *and evaluated* a system"; honest failure modes |
| Model | **OpenAI `gpt-4o-mini`** default (`gpt-4o` for max reasoning); Claude `sonnet-4-6` if using an Anthropic key | Runs on the key you have today; design is vendor-agnostic |

---

## 3. The 3 marquee scenarios

Each traces a **distinct, demonstrable path** through the tools.

| | **S1 — Flaky (precedent-decisive)** | **S2 — Real regression (local-signal-decisive)** | **S3 — Environment/config** |
|---|---|---|---|
| Source | An **order-dependent** test we author (deterministic given test order, genuinely a flakiness *class*) | A **real `with-bugs` defect** (documented → ground truth) | Config injection: wrong base URL / dropped auth token |
| Re-run (`×5`) | Mixed (e.g. 3 pass / 2 fail) → **ambiguous alone** | 5 fail / 5 → **decisive** | 5 fail / 5, but `ConnectionRefused`, not assertion |
| Retrieve? | **Yes — must.** Only history disambiguates | **No — correctly skips** (contract already nails it) | **Yes** — finds past `ConnectionRefused → env` notes |
| Verdict | `FLAKY` → quarantine | `REAL_REGRESSION` → owner, block build | `ENVIRONMENT` → route to infra, not a code bug |
| Proves | RAG is load-bearing; multi-hop retrieval | Agent uses tools over history; deliberate non-retrieval | A **third category** beyond the flaky/real binary |

Example trace (S2):
```
─ Failure: test_create_product_returns_201 ──────────────
  🔧 get_failure_details → AssertionError: expected 201, got 500
  🔧 rerun_test (×5)      → 5 fail / 0 pass   (deterministic)
  🔧 check_contract       → VIOLATION: response missing required field `id`
  💭 Deterministic + contract violation; no flaky precedent needed
  ✅ VERDICT: REAL_REGRESSION  (confidence 0.91)  owner → team-catalog
     action: block build, file bug
```

---

## 4. The agent's tool set (6 + 1 stretch)

| # | Tool | Signature → returns | Purpose | Scenarios |
|---|---|---|---|---|
| 1 | `get_failure_details` | `(test_id)` → name, error type, stack, assertion, endpoint, status, logs | Entry evidence ("read") | all |
| 2 | `rerun_test` | `(test_id, times=5)` → pass/fail tally + new errors | Flaky vs. deterministic | S1, S2 |
| 3 | `search_past_failures` ⭐ | `(query, k=5)` → similar past records {signature, verdict, root_cause, owner, date} | **RAG**; agent-decided, multi-hop | S1, S3 |
| 4 | `check_contract` | `(test_id)` → OpenAPI violations (missing/mis-typed/invalid fields, wrong status) | Real-regression smoking gun | S2 |
| 5 | `check_service_health` | `(target)` → reachable? conn-refused / 5xx / auth-fail | Environment signal | S3 |
| 6 | `submit_triage` (terminal) | `(verdict, confidence, evidence[], owner, suggested_action)` → ends loop | Forces **structured output**, clean stop | all |
| 7 | `git_blame` (**stretch**) | `(path, line)` → author/commit | "Is the *test* wrong?" branch | optional |

**Design notes for the interview:**
- `submit_triage` as a *terminal tool* = structured output without regex parsing.
- `search_past_failures` is *one tool among many* — retrieval is chosen, not hardcoded.
- Each scenario = a distinct visible tool path; the trace explains the branching.

---

## 5. RAG implementation

### 5.1 Corpus record schema (one past triage per record)
```json
{
  "id": "F-2026-0417",
  "signature": "AssertionError: expected 200 got 500 @ POST /products [normalized stack]",
  "verdict": "FLAKY | REAL_REGRESSION | ENVIRONMENT",
  "root_cause": "Async wait — product index not yet committed",
  "owner": "team-catalog",
  "date": "2026-04-17",
  "fix_ref": "PR #1822 / quarantined"
}
```
`signature` is embedded; everything else is **metadata**.

### 5.2 What we embed — normalized signature (the key detail)
Naive RAG embeds the **raw** stack trace and fails: line numbers, timestamps,
hex addresses, UUIDs, ports differ every run, so "the same failure" never matches
itself. We normalize to a stable **signature**: error type + stable stack frames +
endpoint + assertion shape, with run-specific noise stripped. See
`rag/normalize.py`.

> Talking point: *"I don't embed raw logs — I normalize to a failure signature so
> semantically-identical failures cluster regardless of run-specific noise."*

### 5.3 Stack
- **Embeddings:** local `all-MiniLM-L6-v2` (sentence-transformers) — offline, free.
- **Vector store:** Chroma (persistent, in-process).
- **Retrieval:** top-k (k=5) **with a similarity threshold**, so the agent can
  legitimately conclude *"no strong precedent"* and fall back to `check_contract`
  (this is what makes S2's skip real, not cosmetic).

---

## 6. Evaluation

- **Show** the 3 marquee scenarios in full traced detail (the narrative).
- **Measure** over a larger **~10-failure labeled batch** spanning all 3 classes.
- **Ground truth:**
  - `REAL_REGRESSION` ← Toolshop `with-bugs` **Bug Hunting Guide** (documented).
  - `FLAKY` / `ENVIRONMENT` ← authored by us, label known by construction.
- **Report per-class accuracy** (flaky / real / env) — make the confusion visible,
  don't hide it behind one number. "10/12, here are the 2 misses and why" reads as
  rigor.
- **Leakage discipline (⭐):** the corpus must **not** contain the exact record
  being triaged. Same *signature class* is fine (legit precedent); the eval
  failure's own answer row is not. Keep `rag/corpus/` and `eval/failures/`
  **disjoint**.
  > *"Precedent and test set are disjoint — the agent generalizes from similar
  > past failures, it does not retrieve its own answer key."*

---

## 7. Demo surface

CLI: `triage-agent ./eval/failures/failures.xml`

For each failure it streams the tool-call trace + a verdict card; after all
failures it prints the per-class accuracy summary. The **trace format** is the
part worth polishing. Web UI is explicit **future work**.

---

## 8. Repo layout
```
triage-agent/                      (this repo)
  agent/
    loop.py          # raw Anthropic SDK tool-use loop
    tools.py         # the 6 tools (+ git_blame stretch)
    prompts.py       # system prompt + retrieval/verdict policy
  rag/
    corpus/          # ~40 past-triage records (json) — DISJOINT from eval
    normalize.py     # signature normalization
    index.py         # build the Chroma index from corpus/
    retrieve.py      # search_past_failures (threshold-gated top-k)
  suite/
    conftest.py      # base_url / auth fixtures (env-toggle lives here)
    test_*.py        # pytest API tests vs with-bugs Toolshop
  eval/
    failures/        # ~10 labeled failure reports (junit xml + labels.json)
    run_eval.py      # batch triage + per-class accuracy
  cli.py             # entry point: triage-agent <report.xml>
  README.md
  DESIGN.md          # this file
```

---

## 9. 2-day build plan (risk-first)

**Principle:** do the demo-killers first, so failures surface Day 1 morning.

### Day 1 — engine
| Time | Task | Done-when |
|---|---|---|
| 0:00–1:00 | **Docker spike** (riskiest first): stand up `with-bugs`, hit API | `localhost` API responds; else fall back to hosted |
| 1:00–2:30 | pytest suite (8–10 API tests) + author **order-dependent flaky** test + **bad-base-url env** toggle; capture JUnit XML | real failures + XML emitted |
| 2:30–4:00 | RAG: ~40 corpus records (synthetic + IDoFT slice), `normalize.py`, build Chroma, `retrieve.py` + threshold | retrieval returns sane precedent |
| 4:00–6:00 | Agent loop: SDK tool-use loop + wire all 6 tools + system prompt/policy | **triages ONE failure end-to-end correctly** |

### Day 2 — showcase
| Time | Task | Done-when |
|---|---|---|
| 0:00–1:30 | All 3 scenarios branch correctly (tune policy: S2 skips retrieval, etc.) | 3 distinct correct traces |
| 1:30–3:00 | CLI rich trace (tool steps + verdict cards) | matches the mockup |
| 3:00–4:30 | Eval harness: ~10 labeled failures, per-class accuracy | metric prints; misses explainable |
| 4:30–5:30 | README + architecture diagram + talking points; **cold offline dry-run** | runs from a fresh terminal, no wifi |
| 5:30–6:00 | Buffer / `git_blame` stretch | — |

**Cut-list if behind (in order):** `git_blame` → color formatting → trim eval to 6 → hosted instead of docker. Irreducible core = engine + 3 traces + a metric.

---

## 10. Interview talking points
1. **Retrieval-as-a-tool** — agent *chooses* when to consult history.
2. **Signature normalization** — embed signatures, not raw logs.
3. **Threshold → legitimate skip** — low similarity → fall back to `check_contract`.
4. **Corpus ⊥ eval** — it generalizes; it doesn't look up its answer key.
5. **Measured accuracy** — per-class, with honest failure modes.
6. **Language-agnostic** — same design runs against JUnit suites.
7. **Vendor-agnostic loop** — the agent loop is decoupled from the LLM provider:
   OpenAI today, Claude by swapping one adapter. Plus a **rule-based replay mode**
   that drives the *same tools* with no LLM — my demo-day insurance and a clean
   way to show the tool paths deterministically.
   **Future work:** action tools (`quarantine`/`file_ticket`), web UI, real CI pipeline.

---

## 11. Data sources
- **Host app / real bugs:** `testsmith-io/practice-software-testing` (`with-bugs`).
  Bug Hunting Guide → ground-truth labels for `REAL_REGRESSION`.
- **RAG corpus:** ~40 synthetic triage records + a slice of **IDoFT**
  (*International Dataset of Flaky Tests*) mapped to our schema — so the honest
  answer to "where's this data from?" cites a published flaky-test dataset.

  **IDoFT (verified):**
  - Repo: https://github.com/TestingResearchIllinois/idoft
    (website: http://mir.cs.illinois.edu/flakytests). 8,000+ flaky tests, 100+
    real projects, curated by the Illinois testing-research group.
  - CSVs: `pr-data.csv` (Java/Maven), `gr-data.csv` (Java/Gradle),
    `py-data.csv` (Python).
  - `pr-data.csv` columns (verbatim):
    `Project URL, SHA Detected, Module Path, Fully-Qualified Test Name
    (packageName.ClassName.methodName), Category, Status, PR Link, Notes`
  - `Category` vocab (→ our `root_cause` taxonomy): `OD` (Order-Dependent),
    `OD-Vic`/`OD-Brit`, `ID` (Implementation-Dependent), `NOD` (Non-Deterministic),
    `NDOD`/`NDOI`, `TD` (Time-Dependent), `TZD`, `OSD`, `UD`, `NIO`.

  **Mapping → our schema (and the honest framing):** IDoFT gives REAL test names,
  projects, root-cause categories, and fix PRs — but NO stack traces. So:
  `verdict`←`FLAKY` (real), `root_cause`←`Category` (real), `owner`←`Project URL`
  (real), `fix_ref`←`PR Link`/`Status` (real), **`signature`← synthesized** from
  the category (fabricated — disclose it).
  > Interview line: *"The flaky labels and root-cause categories are real IDoFT
  > data; I synthesized representative signatures on top, since IDoFT catalogs
  > tests, not stack traces."*
  > Tie-in: our authored S1 flaky is an **`OD`-class** failure — IDoFT's most
  > common flakiness category.

  *Check the IDoFT repo LICENSE before redistributing rows; cite + use a small
  slice for the demo.*

---

## 12. Implementation status (built today)

**Working end-to-end, fully offline (`replay` mode), verified:**
- 3 marquee scenario traces render correctly, each a distinct tool path
  (`python cli.py eval/failures/failures.xml`).
- Eval over a **9-failure batch, 3 per class → 9/9 per-class accuracy**
  (`python -m eval.run_eval`).
- RAG: 40-record corpus (7 seed + 12 real IDoFT + 21 synthetic), MiniLM + Chroma
  index built and retrieving with clean per-class discrimination; threshold 0.55.

**Run modes (auto-selected; `TRIAGE_MODE` overrides):**
- `replay` — deterministic rule-based driver over the real tools; no key. Default
  fallback + demo-day insurance.
- `openai` — real LLM tool-calling loop (`OPENAI_API_KEY`, `gpt-4o-mini` default).
- `anthropic` — same loop on a Claude key (drop-in).

**Fixtures vs. live:** the 5 tools read `fixtures/recorded.json` so nothing
depends on a running app. `# LIVE:` markers in `agent/tools.py` show exactly
where to swap in real Toolshop API calls once `API_BASE_URL` is set.

**Embedder fallback:** MiniLM primary; pure-Python hashing embedder kicks in if
torch is absent, so retrieval always runs (`rag/embedder.py`).

**Remaining (the Day-1 "engine" slot, now optional polish):** stand up Toolshop
`with-bugs` via docker, write the real pytest request bodies, and flip the
tools from fixtures to live. Everything downstream already works against that
shape.

### What only *you* can supply
- Your `OPENAI_API_KEY` (not in the build environment) → to run `openai` mode.
- Running docker for live Toolshop (optional — fixtures stand in for the demo).
