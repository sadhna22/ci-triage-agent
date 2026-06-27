# RAG corpus — past triaged failures

Target: **~40 records** = hand-authored synthetic + a slice of **IDoFT**
(*International Dataset of Flaky Tests*, UIUC MIR) mapped to our schema. The
sample files here seed the structure; expand during the Day-1 RAG slot.

## Schema (one record per past triage)
```json
{
  "id": "F-2026-0417",
  "signature": "<normalized failure signature — this is what gets embedded>",
  "verdict": "FLAKY | REAL_REGRESSION | ENVIRONMENT",
  "root_cause": "...",
  "owner": "team-...",
  "date": "YYYY-MM-DD",
  "fix_ref": "PR #.. / quarantined / config change"
}
```
Only `signature` is embedded; the rest is metadata.

## ⚠️ Leakage rule (corpus ⊥ eval)
These records must **NOT** contain the answer row for any failure in
`eval/failures/`. The same *signature class* is allowed and intended (legitimate
precedent — e.g. several past Async-Wait flakies). The eval failure's own labeled
answer is not. Precedent and test set stay disjoint so the agent **generalizes**
rather than looking up its own answer key.

## What to seed
- A **cluster (~4–5)** sharing Scenario 1's flaky Async-Wait signature → makes the
  precedent verdict land.
- A few **ConnectionRefused / env** records for Scenario 3.
- **Decoys**: past REAL_REGRESSIONs with superficially similar stack traces, so
  retrieval must actually discriminate (proves semantic match, not keyword grep).
