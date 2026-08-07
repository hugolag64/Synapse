# Audit Remediation Design

**Date:** 2026-08-07

**Goal:** Restore the correctness and operational reliability of Synapse's P0 audit findings, then address the highest-value P1 and P2 defects without changing unrelated product behavior.

## Scope

The work is delivered in three independently verifiable batches:

- **P0:** Rang A classification, error-signal ingestion, data-backed dashboard prioritization, and the human-validation gate for visual UNESS corrections.
- **P1:** Gemini resilience, durable Notion retry handling, test database isolation, and visible Google Calendar authentication failures.
- **P2:** startup/network caching, mastery caching in `/stats`, off-thread semantic-graph persistence, and integration data-quality fixes.

Existing user changes in `UNESS/.imported.json`, `docs/AUDIT_2026-08-07.md`, and `docs/SYNAPSE_AI_CONTEXT.md` are outside the scope and must be preserved.

## Design

### P0 correctness boundary

Rang A thresholds are applied only when the course has actual Rang A OIC evidence. The snapshot may keep the score value for display compatibility, but the level calculation and explanatory reasons must consult the evidence flag. Tests cover both a course with no OIC evidence and a course with measured Rang A evidence.

Every scored closed QCM attempt produces idempotent error signals for its linked item when the response contains a discordance. The attempt ID is the evidence identity; repeated saves of the same attempt must not create duplicate signals. Existing categories (`omission`, `exces`, and the zero-score reason) are reused instead of inventing a second taxonomy.

Dashboard gain items read frequency and available-question data from local stores. Missing data produces a neutral fallback and an explicit low-confidence state; constants must not pretend that every item has equal frequency or ten available questions.

Visual UNESS corrections are marked as requiring human validation before they are treated as final. The gate is enforced at the production call path, not only by `extract_grid` tests, and the response metadata/status makes the pending state visible to callers.

### P1 resilience boundary

Gemini visual calls use a bounded retry policy for transient failures and a clear terminal error. Retry behavior is tested without real network calls. Notion updates that fail after the existing client retries are persisted for later replay rather than silently discarded. Test fixtures use a temporary SQLite path and never write production telemetry.

Calendar authentication errors are converted into an explicit user-visible failure state while preserving the existing no-events behavior only for successful empty results.

### P2 performance and integration boundary

Streak counts are cached until the local day changes. `/stats` reuses the existing mastery cache. Semantic-graph rebuilding and persistence run off the NiceGUI event loop. Obsidian resolution and UNESS/EDNpro deduplication are corrected only where the audit identifies a concrete data-integrity mismatch.

## Acceptance criteria

- No course without Rang A evidence is classified as Rang A-fragile solely because `score_rang_a` is below 75.
- A failed linked QCM attempt creates observable error-signal data exactly once per attempt/item/category.
- Dashboard gain items vary with stored frequency and question availability, with deterministic neutral fallbacks for missing data.
- Production visual UNESS corrections cannot bypass the human-validation status.
- Transient Gemini failures retry within a bounded budget; terminal failures are explicit.
- Failed Notion writes remain recoverable after the request returns.
- Tests run against temporary databases and do not add rows to the production database.
- P2 changes preserve current behavior while eliminating the audited avoidable network/blocking work.

## Testing strategy

Each behavior follows red-green-refactor: add one regression test, run it to observe the expected failure, implement the smallest fix, run the focused test, then run the relevant regression suite. The full suite is run after each priority batch.
