# Anki Native Review in Synapse Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Permettre de réviser les cartes existantes du paquet `Fiches EDN Notion` dans Synapse tout en faisant calculer le planning, les intervalles et la maturité par le moteur natif d'Anki.

**Architecture:** Synapse restera un client de lecture et d'affichage des cartes. Un petit ajout local à AnkiConnect exposera une action `synapseAnswerCard(cardId, ease)` qui utilisera le scheduler Anki natif et renverra l'état recalculé. Synapse enregistrera parallèlement une preuve de révision dédoublonnée pour son algorithme de maîtrise.

**Tech Stack:** Python, AnkiConnect HTTP JSON, NiceGUI, SQLite existant, pytest.

## Global Constraints

- Le paquet source est exclusivement `Fiches EDN Notion`.
- Synapse ne crée aucune carte ni aucun paquet Anki.
- Les réponses utilisent la sémantique Anki : `again`, `hard`, `good`, `easy`.
- Le nombre de lectures et la présence du paquet ne sont pas des preuves directes de maîtrise.
- Les QCM, DP et KFP restent la source principale du score de préparation EDN.
- Une indisponibilité d'AnkiConnect ne doit pas pénaliser l'utilisateur.
- Une même révision ne doit jamais être comptée deux fois dans Synapse.

---

### Task 1: Modèle et client Anki en lecture seule

**Files:**
- Create: `backend/core/anki/__init__.py`
- Create: `backend/core/anki/models.py`
- Create: `backend/core/anki/client.py`
- Test: `tests/test_anki_client.py`

**Interfaces:**
- Produces `AnkiConnectionStatus(connected: bool, reason: str | None)`.
- Produces `AnkiCard(card_id: int, note_id: int | None, deck_name: str, model_name: str, fields: dict[str, str], tags: tuple[str, ...], interval: int, queue: int, card_type: int, due: int, reps: int, lapses: int)`.
- Produces `AnkiClient(base_url: str = "http://127.0.0.1:8765", timeout_seconds: float = 2.5)` with `ping()`, `find_cards(query: str) -> list[int]`, `cards_info(card_ids: list[int]) -> list[AnkiCard]`, `get_reviews(card_ids: list[int]) -> dict[int, list[dict]]`.

- [ ] **Step 1: Write failing tests for request payloads, success responses, API errors and timeout.**
- [ ] **Step 2: Run `pytest tests/test_anki_client.py -q` and verify the new tests fail.**
- [ ] **Step 3: Implement a small JSON HTTP client using the existing project HTTP conventions; check both HTTP errors and AnkiConnect's `error` field.**
- [ ] **Step 4: Normalize missing tags to an empty tuple and never expose raw HTML fields outside `AnkiCard`.**
- [ ] **Step 5: Run the focused test file and verify all cases pass.**

### Task 2: Deck-to-item mapping and synchronization snapshot

**Files:**
- Create: `backend/core/anki/mapping.py`
- Create: `backend/core/anki/service.py`
- Test: `tests/test_anki_mapping.py`

**Interfaces:**
- Produces `parse_item_numbers(deck_name: str) -> tuple[str, ...]` for names such as `221. Athérome` and `231, 232, 236, 237, 342. Rythmologie`.
- Produces `AnkiItemLink(item_number: str, card_ids: tuple[int, ...], note_ids: tuple[int, ...], deck_names: tuple[str, ...])`.
- Produces `AnkiSyncService.sync_fiches_edn() -> AnkiSyncSnapshot` with connection status, card counts, mapped item counts, unmapped decks and last synchronization timestamp.

- [ ] **Step 1: Write tests for one-item decks, multi-item decks, specialty-only decks, unrelated decks and malformed names.**
- [ ] **Step 2: Run `pytest tests/test_anki_mapping.py -q` and verify failure.**
- [ ] **Step 3: Implement parsing restricted to descendants of `Fiches EDN Notion`; keep a card's evidence unique even when a deck maps to several items.**
- [ ] **Step 4: Use `cardsToNotes`/`cardsInfo` data to retain stable card and note IDs.**
- [ ] **Step 5: Run focused tests and verify the snapshot is deterministic.**

### Task 3: Synapse evidence storage and deduplication

**Files:**
- Modify: `backend/core/reviews/local_store.py`
- Modify: `backend/core/evaluation/models.py`
- Modify: `backend/core/evaluation/service.py`
- Test: `tests/test_anki_evidence.py`

**Interfaces:**
- Adds an idempotent store operation `record_anki_review(card_id: int, note_id: int | None, item_numbers: tuple[str, ...], rating: str, reviewed_at: datetime, interval: int | None, source_review_id: str | None) -> str`.
- Adds `get_anki_review_evidence(item_number: str | None = None) -> list[dict]`.
- Uses a stable deduplication key based on `card_id + reviewed_at + rating + interval` when Anki does not provide a review ID.

- [ ] **Step 1: Write tests for first insert, repeated insert, multi-item mapping and concurrent duplicate insert.**
- [ ] **Step 2: Run the focused tests and verify failure.**
- [ ] **Step 3: Add the smallest SQLite table/index required by the existing local store transaction model.**
- [ ] **Step 4: Implement the idempotent write and read operations under the existing database lock.**
- [ ] **Step 5: Run `pytest tests/test_anki_evidence.py -q`.**

### Task 4: Native Anki scheduler bridge

**Files:**
- Create: `scripts/anki_addon/synapse_bridge/__init__.py`
- Create: `scripts/anki_addon/synapse_bridge/manifest.json`
- Create: `scripts/anki_addon/synapse_bridge/bridge.py`
- Create: `scripts/anki_addon/synapse_bridge/README.md`
- Test: `tests/test_anki_scheduler_bridge.py`

**Interfaces:**
- Exposes the AnkiConnect action `synapseAnswerCard` with `{ "cardId": int, "ease": 1|2|3|4 }`.
- Returns `{ "cardId": int, "noteId": int, "ease": int, "interval": int, "queue": int, "type": int, "due": int, "reps": int, "lapses": int, "reviewedAt": int }`.
- Rejects invalid card IDs, invalid ease values, suspended cards and unavailable scheduler state without mutating Anki.

- [ ] **Step 1: Write fake-collection/fake-scheduler tests proving that ease 1–4 is passed to the native scheduler exactly once.**
- [ ] **Step 2: Run `pytest tests/test_anki_scheduler_bridge.py -q` and verify failure.**
- [ ] **Step 3: Implement the action using the Anki collection's native card lookup and scheduler answer operation, with compatibility checks for the installed Anki version.**
- [ ] **Step 4: Return the recalculated card state only after the scheduler operation succeeds.**
- [ ] **Step 5: Document installation into Anki's add-ons directory and the restart requirement.**
- [ ] **Step 6: Run focused tests and manually answer one disposable test card in Anki.**

### Task 5: Synapse review session using Anki scheduling

**Files:**
- Create: `frontend/components/anki_review_session.py`
- Modify: `frontend/pages/course_detail.py`
- Modify: `frontend/pages/course_detail_cockpit.py`
- Test: `tests/test_anki_review_session.py`

**Interfaces:**
- Produces `AnkiReviewSession(item_number: str | None = None)`.
- Loads due cards through `AnkiSyncService`, displays the question/answer fields safely, and exposes four rating actions.
- Calls `synapseAnswerCard`, records the returned review through `record_anki_review`, then loads the next due card.
- Shows explicit states: Anki unavailable, bridge not installed, no due cards, review active and answer saved.

- [ ] **Step 1: Write tests for card loading, rating-to-ease mapping, bridge failure, successful evidence recording and no-due-card state.**
- [ ] **Step 2: Run `pytest tests/test_anki_review_session.py -q` and verify failure.**
- [ ] **Step 3: Implement the component following existing cockpit/wizard dismissal conventions.**
- [ ] **Step 4: Add an entry point from the item/course cockpit labelled `Réviser avec Anki`, without introducing a second card creation flow.**
- [ ] **Step 5: Run focused UI/component tests.**

### Task 6: Feed Anki evidence into knowledge mastery

**Files:**
- Modify: `backend/core/reviews/mastery.py`
- Modify: `backend/core/knowledge/service.py`
- Test: `tests/test_knowledge_mastery.py`

**Interfaces:**
- Adds an Anki evidence aggregate to `CourseProgressSnapshot` without reusing `anki_done` as a boolean.
- Computes a capped, recency-aware Anki contribution from actual ratings and intervals.
- Keeps Anki out of the primary EDN readiness score except for display context.

- [ ] **Step 1: Write tests proving that no Anki history produces no penalty, repeated failures reduce knowledge mastery, mature Good/Easy reviews improve it within a cap, and QCM readiness remains unchanged.**
- [ ] **Step 2: Run `pytest tests/test_knowledge_mastery.py -q` and verify failure.**
- [ ] **Step 3: Implement the aggregate and bounded contribution using the existing hybrid score structure.**
- [ ] **Step 4: Run the mastery and evaluation test files.**

### Task 7: End-to-end verification and documentation

**Files:**
- Modify: `docs/PROGRESSION_SESSION_2026-07-28-ROBUSTESSE.md`
- Modify: `docs/superpowers/specs/2026-07-28-anki-bidirectional-review-design.md`
- Test: `tests/test_anki_integration.py`

- [ ] **Step 1: Add contract tests covering sync → display → native answer → evidence → mastery.**
- [ ] **Step 2: Run `pytest -q` and `python -m compileall backend frontend scripts`.**
- [ ] **Step 3: Run a manual smoke test with Anki open, one disposable card and one real `Fiches EDN Notion` card.**
- [ ] **Step 4: Record the installed addon path, connection behavior and known limitations in the progression document.**
- [ ] **Step 5: Run the full suite again and report the exact result.**
