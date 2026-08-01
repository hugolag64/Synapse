# UNESS Import Diagnostics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop a single unverifiable-image question from blocking an entire UNESS quiz import, and add a Paramètres page that shows exactly which quiz of which annale is imported / retrying / blocked / never attempted, with direct action buttons.

**Architecture:** Part A relaxes one validation gate (`assert_verified_exam`) so a question with `verification_status == "unsupported"` is imported with its AI verdict cleared (falling back to the official UNESS answer) instead of rejecting the whole quiz — mirroring a pattern (`_unsupported_visual_question`) that already exists in `ai_verifier.py` but was never reachable end-to-end. Part B adds a new read-only reporting module (`backend/core/uness/diagnostics.py`) that reconstructs "how many quiz should exist" by scanning bridge JSON files already on disk, cross-references that against `ai_practice_sessions`, `uness_correction_failures`, and a live `import_verified_directory()` call, and renders the result as a new section in the existing Paramètres cockpit page.

**Tech Stack:** Python 3.13, NiceGUI, SQLite (via `backend/core/reviews/local_store.py`), pytest.

## Global Constraints

- French UI copy throughout (matches every existing string in this codebase).
- No new dependencies.
- `assert_verified_exam`'s existing strict checks for `verified`/`unverified` questions must not change — only the `unsupported` branch changes.
- Diagnostics reads must never mutate correction-failure or annale state except via the two explicit actions (Relancer, Qualifier) — `build_report()` itself only imports what's already safely importable (calling `import_verified_directory()` is accepted as a side effect per the spec, since it's idempotent and already proven safe to call repeatedly).

---

## Part A — Import a quiz despite one unverifiable-visual question

### Task 1: Share the "unsupported visual" explanation constant

**Files:**
- Modify: `backend/core/uness/models.py`
- Modify: `backend/core/uness/ai_verifier.py:44-47` (remove local constant, import shared one)

**Interfaces:**
- Produces: `backend.core.uness.models.UNSUPPORTED_VISUAL_EXPLANATION: str` — used by Task 2 (`gemini_conversion.py`) and already used internally by `ai_verifier.py`.

- [ ] **Step 1: Add the constant to `models.py`**

Open `backend/core/uness/models.py`. Near the top, right after the existing module-level constants (`UnessVerificationStatus`, `_VERIFICATION_STATUSES` around line 13-17), add:

```python
UNSUPPORTED_VISUAL_EXPLANATION = (
    "Vérification IA indisponible : le support visuel requis n'a pas pu être "
    "fourni intégralement au modèle."
)
```

- [ ] **Step 2: Point `ai_verifier.py` at the shared constant**

In `backend/core/uness/ai_verifier.py`:
- Remove lines 44-47 (the local `_UNSUPPORTED_VISUAL_EXPLANATION = (...)` definition).
- In the existing `from .models import (...)` block (lines 18-24), add `UNSUPPORTED_VISUAL_EXPLANATION` to the imported names.
- Find every remaining use of `_UNSUPPORTED_VISUAL_EXPLANATION` in the file (there is exactly one, inside `_unsupported_visual_question`, currently line 416) and rename it to `UNSUPPORTED_VISUAL_EXPLANATION`.

- [ ] **Step 3: Run the existing ai_verifier test suite to confirm nothing broke**

Run: `python -m pytest tests/test_uness_ai_verifier.py -v`
Expected: PASS (same behavior, just re-sourced constant — no test should reference the private name directly, but if one does, update it to the public name).

- [ ] **Step 4: Commit**

```bash
git add backend/core/uness/models.py backend/core/uness/ai_verifier.py
git commit -m "refactor: share UNSUPPORTED_VISUAL_EXPLANATION between ai_verifier and gemini_conversion"
```

---

### Task 2: `gemini_conversion.py` clears the AI verdict on unsupported questions

**Files:**
- Modify: `backend/core/uness/gemini_conversion.py:158-189` (`_question`)
- Test: `tests/test_gemini_conversion.py`

**Interfaces:**
- Consumes: `models.UNSUPPORTED_VISUAL_EXPLANATION` (Task 1).
- Produces: `_question()`'s output dict, when `verification_status == "unsupported"`, now has every proposition's `verdict_ia=None`, `explication_ia=UNSUPPORTED_VISUAL_EXPLANATION`, `confiance_ia=None`, `commentaire_desaccord=""`, `statut="incertain"` — consumed by Task 3's relaxed `assert_verified_exam` and by the existing `_effective_answer`/`_choice_answers`/`_primary_explanation` in `import_service.py` (unchanged, already fall back to `reponse_uness` correctly when `verdict_ia is None`).

- [ ] **Step 1: Write the failing test**

Add to `tests/test_gemini_conversion.py` (uses the existing `_bridge`/`_HTML` helpers already in that file):

```python
def test_unsupported_visual_question_has_its_ai_verdict_cleared():
    # A question whose image wasn't fully provided to the model must not keep
    # whatever verdict Gemini guessed anyway — it's ungrounded. The official
    # UNESS answer (reponse_uness) must survive untouched so the question can
    # still be imported and answered against a real correction.
    bridge = _bridge(_HTML)
    bridge["contents"][0]["images"] = [
        {"question_id": "question-1-2", "filename": "scan.png", "alt_text": "Scanner"}
    ]
    quiz = {
        "quiz_title": "DP1\nTest",
        "questions": [
            {
                "id": "question-1-2",
                "type_question": "QRU",
                "enonce": "Quel est le diagnostic le plus probable ?",
                "propositions": [
                    {
                        "id": "p1",
                        "texte": "Colique néphrétique",
                        "reponse_officielle": True,
                        "verdict_ia": True,
                        "avis_ia": "valide",
                        "confiance_ia": 0.95,
                        "explication": "Je vois clairement une dilatation sur le scanner.",
                        "desaccord_officiel": False,
                    }
                ],
                "media": [{"filename": "scan.png", "accessible_ia": False}],
            }
        ],
    }
    exams = convert_with_bridge([quiz], bridge)
    question = exams[0].questions[0]
    assert question.verification_status == "unsupported"
    proposition = question.propositions[0]
    assert proposition.verdict_ia is None
    assert proposition.confiance_ia is None
    assert proposition.explication_ia == UNSUPPORTED_VISUAL_EXPLANATION
    assert proposition.statut == "incertain"
    # The official answer must survive — it's the only ground truth left.
    assert proposition.reponse_uness is True
```

Add the import at the top of the file: `from backend.core.uness.models import UNSUPPORTED_VISUAL_EXPLANATION`.

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_gemini_conversion.py::test_unsupported_visual_question_has_its_ai_verdict_cleared -v`
Expected: FAIL — `proposition.verdict_ia` is `True`, not `None` (the sanitization doesn't exist yet).

- [ ] **Step 3: Implement the sanitization in `_question()`**

In `backend/core/uness/gemini_conversion.py`, add the import at the top (in the existing `from .models import (...)` line 21):

```python
from .models import _QUESTION_TYPES, UnessExam, UNSUPPORTED_VISUAL_EXPLANATION
```

Add a new helper right before `_question()` (after `_image()`, before line 158):

```python
def _sanitize_unsupported_propositions(propositions: list[dict]) -> list[dict]:
    """A question marked "unsupported" means the model didn't receive its
    required image — clear whatever verdict it produced anyway instead of
    trusting a guess made without the visual (mirrors
    ai_verifier._unsupported_visual_question, which the manual/automated
    verification path already applies for the same reason)."""
    return [
        {
            **proposition,
            "verdict_ia": None,
            "explication_ia": UNSUPPORTED_VISUAL_EXPLANATION,
            "confiance_ia": None,
            "commentaire_desaccord": "",
            "statut": "incertain",
        }
        for proposition in propositions
    ]
```

Modify `_question()` (lines 158-189) so the sanitization is applied to the *converted* propositions (the ones already shaped by `_proposition()`, not the raw AI ones — the raw dict uses different key names like `reponse_officielle`/`explication`, not `reponse_uness`/`explication_ia`). Change:

```python
        "propositions": [_proposition(p) for p in propositions],
```

to:

```python
        "propositions": (
            _sanitize_unsupported_propositions([_proposition(p) for p in propositions])
            if verification_status == "unsupported"
            else [_proposition(p) for p in propositions]
        ),
```

(`verification_status` is already computed earlier in the same function, at line 167-169 — no reordering needed.)

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_gemini_conversion.py -v`
Expected: All PASS, including the new test and every pre-existing one in the file (confirms `verified` questions are untouched).

- [ ] **Step 5: Commit**

```bash
git add backend/core/uness/gemini_conversion.py tests/test_gemini_conversion.py
git commit -m "fix: clear AI verdict on unsupported-visual questions during Gemini conversion"
```

---

### Task 3: `assert_verified_exam` no longer blocks the whole quiz over one unsupported question

**Files:**
- Modify: `backend/core/uness/import_service.py:509-527` (`assert_verified_exam`)
- Modify: `tests/test_uness_import.py:238-263` (replace the now-outdated test)

**Interfaces:**
- Consumes: `UnessQuestion.verification_status`, `UnessProposition.reponse_uness` (existing fields, unchanged).
- Produces: `assert_verified_exam(exam)` now raises `ValueError` for an `unsupported` question **only** when none of its propositions carry a `reponse_uness` — otherwise the question passes through with whatever `verdict_ia`/`confiance_ia`/`explication_ia` it has (Task 2 guarantees these are cleared to a safe, non-misleading state for the Gemini pipeline; the equivalent is already true for the `ai_verifier.py` pipeline).

- [ ] **Step 1: Replace the outdated test with two precise ones**

In `tests/test_uness_import.py`, delete the existing `test_verified_import_rejects_an_unsupported_visual_question` (lines 238-263) and replace it with:

```python
def test_verified_import_accepts_unsupported_visual_question_with_official_answer(
    client, import_dir
):
    """An unsupported-visual question must not block the rest of an otherwise
    valid quiz — the official UNESS answer is still a usable ground truth."""
    payload = _exam_payload()
    question = payload["questions"][0]
    question["verification_status"] = "unsupported"
    question["images"][0]["metadata"] = {"verification_status": "unsupported"}
    for proposition in question["propositions"]:
        proposition.update(
            verdict_ia=None,
            explication_ia="Vérification IA indisponible : support visuel non pris en charge.",
            sources_ia=[],
            confiance_ia=None,
            commentaire_desaccord="",
            statut="incertain",
        )
    _write_exam(import_dir, "unsupported-visual.json", payload)

    response = client.post(
        "/api/qcm/uness/import",
        json={"path": "unsupported-visual.json", "verify": True},
    )

    assert response.status_code == 200
    session = client.get(f"/api/qcm/sessions/{response.json()['session_id']}").json()
    question_out = session["questions"][0]
    # Falls back to the official UNESS answer (proposition B is True there).
    assert "Il peut être fluctuant." in question_out["answer"]


def test_verified_import_rejects_unsupported_visual_question_without_official_answer(
    client, import_dir
):
    """If even the official UNESS answer is missing, there's nothing left to
    import this question against — still a hard failure, but scoped to that
    one question's message rather than a generic rejection."""
    payload = _exam_payload()
    question = payload["questions"][0]
    question["verification_status"] = "unsupported"
    question["images"][0]["metadata"] = {"verification_status": "unsupported"}
    for proposition in question["propositions"]:
        proposition.update(
            reponse_uness=None,
            verdict_ia=None,
            explication_ia="Vérification IA indisponible : support visuel non pris en charge.",
            sources_ia=[],
            confiance_ia=None,
            commentaire_desaccord="",
            statut="incertain",
        )
    _write_exam(import_dir, "unsupported-visual-no-official.json", payload)

    response = client.post(
        "/api/qcm/uness/import",
        json={"path": "unsupported-visual-no-official.json", "verify": True},
    )

    assert response.status_code == 400
    assert "réponse officielle UNESS manquante" in response.json()["detail"]
```

- [ ] **Step 2: Run tests to verify the first fails and the second currently fails differently**

Run: `python -m pytest tests/test_uness_import.py::test_verified_import_accepts_unsupported_visual_question_with_official_answer tests/test_uness_import.py::test_verified_import_rejects_unsupported_visual_question_without_official_answer -v`
Expected: first test FAILS with 400 (current code rejects all `unsupported` questions unconditionally); second test currently PASSES with a *different* message ("vérification visuelle non prise en charge") — that's fine, it'll assert the new message after Step 3.

- [ ] **Step 3: Relax `assert_verified_exam`**

In `backend/core/uness/import_service.py`, replace lines 509-527:

```python
def assert_verified_exam(exam: UnessExam) -> None:
    """Check that a verified exam has complete, coherent AI review metadata on every proposition."""
    for question in exam.questions:
        if question.verification_status == "unsupported":
            raise ValueError(f"Question {question.id} : vérification visuelle non prise en charge.")
        for image in question.images:
            if image.metadata.get("verification_status") != "provided_to_ai":
                raise ValueError(f"Image {image.source_url} non analysée par l'IA (status image: {image.metadata.get('verification_status')}, doit être provided_to_ai)")
        for proposition in question.propositions:
            if proposition.verdict_ia is None:
                raise ValueError(f"verdict_ia (vérification IA) manquant pour la proposition {proposition.id}")
            if not proposition.explication_ia or not proposition.explication_ia.strip():
                raise ValueError(f"Explication de vérification IA manquante pour la proposition {proposition.id}")
            if proposition.confiance_ia is None or not (0.0 <= proposition.confiance_ia <= 1.0):
                raise ValueError(f"Confiance de vérification IA invalide pour la proposition {proposition.id}")
            if proposition.statut not in {"concordant", "desaccord", "incertain", "valide_manuellement"}:
                raise ValueError(f"Statut de vérification IA invalide ({proposition.statut}) pour la proposition {proposition.id}")
            if proposition.statut == "incertain" and proposition.reponse_uness is not None:
                raise ValueError(f"Statut de vérification IA incohérent ({proposition.statut}) pour la proposition {proposition.id}")
```

with:

```python
def assert_verified_exam(exam: UnessExam) -> None:
    """Check that a verified exam has complete, coherent AI review metadata on
    every proposition — except questions marked "unsupported" (the model
    never received the image it needed): those only need the official UNESS
    answer as a fallback ground truth. Blocking the whole quiz over one such
    question would throw away every other question that WAS properly
    verified, which is worse than importing with one weaker question."""
    for question in exam.questions:
        if question.verification_status == "unsupported":
            if not question.propositions or any(
                proposition.reponse_uness is None for proposition in question.propositions
            ):
                raise ValueError(
                    f"Question {question.id} : vérification visuelle indisponible et "
                    "réponse officielle UNESS manquante — impossible à importer."
                )
            continue
        for image in question.images:
            if image.metadata.get("verification_status") != "provided_to_ai":
                raise ValueError(f"Image {image.source_url} non analysée par l'IA (status image: {image.metadata.get('verification_status')}, doit être provided_to_ai)")
        for proposition in question.propositions:
            if proposition.verdict_ia is None:
                raise ValueError(f"verdict_ia (vérification IA) manquant pour la proposition {proposition.id}")
            if not proposition.explication_ia or not proposition.explication_ia.strip():
                raise ValueError(f"Explication de vérification IA manquante pour la proposition {proposition.id}")
            if proposition.confiance_ia is None or not (0.0 <= proposition.confiance_ia <= 1.0):
                raise ValueError(f"Confiance de vérification IA invalide pour la proposition {proposition.id}")
            if proposition.statut not in {"concordant", "desaccord", "incertain", "valide_manuellement"}:
                raise ValueError(f"Statut de vérification IA invalide ({proposition.statut}) pour la proposition {proposition.id}")
            if proposition.statut == "incertain" and proposition.reponse_uness is not None:
                raise ValueError(f"Statut de vérification IA incohérent ({proposition.statut}) pour la proposition {proposition.id}")
```

- [ ] **Step 4: Run the full import test file to verify everything passes**

Run: `python -m pytest tests/test_uness_import.py -v`
Expected: All PASS, including both new tests and every pre-existing one (in particular `test_verified_import_rejects_incomplete_or_incoherent_ai_review`, which covers `verified`/normal questions and must be unaffected).

- [ ] **Step 5: Commit**

```bash
git add backend/core/uness/import_service.py tests/test_uness_import.py
git commit -m "fix: import a quiz despite one unsupported-visual question instead of rejecting it whole"
```

---

### Task 4: Show a warning on an unsupported-visual question in the correction view

**Files:**
- Modify: `frontend/components/qcm_replay.py:335-342` (inside `_render_rows`, right after the existing `support_visuel_seul` block)
- Modify: `tests/test_qcm_replay.py:236-297` (extend the existing NiceGUI-rendering test)

**Interfaces:**
- Consumes: `question["uness"]["question"]["verification_status"]` — already present in every imported question's `import_metadata_json` (`import_service._question_metadata`, line 448 — no backend change needed for this field to exist).

- [ ] **Step 1: Extend the existing test's fixture and assertion**

In `tests/test_qcm_replay.py`, inside `test_qcm_correction_discloses_official_uness_correction` (starting line 173), find the `question["uness"]["question"]` dict (lines 257-267):

```python
            "question": {
                "images": [
                    {
                        "source_url": "images/scan.png",
                        "local_path": "imports/media/scan.png",
                        "alt_text": "Scanner cérébral",
                        "caption": "Coupe axiale",
                    }
                ],
                "support_visuel_seul": True,
            },
```

Add a `verification_status` key:

```python
            "question": {
                "images": [
                    {
                        "source_url": "images/scan.png",
                        "local_path": "imports/media/scan.png",
                        "alt_text": "Scanner cérébral",
                        "caption": "Coupe axiale",
                    }
                ],
                "support_visuel_seul": True,
                "verification_status": "unsupported",
            },
```

Add a new assertion right after the existing `support_visuel_seul` assertion (after line 295, `)`):

```python
    assert (
        "⚠️ Vérification IA non disponible pour cette question — seule la "
        "correction officielle UNESS est garantie exacte."
        in labels
    )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_qcm_replay.py::test_qcm_correction_discloses_official_uness_correction -v`
Expected: FAIL — the new label is never rendered.

- [ ] **Step 3: Add the warning label in `qcm_replay.py`**

In `frontend/components/qcm_replay.py`, find the existing block (around line 335-342):

```python
                        question_metadata = uness.get("question") or {}
                        if question_metadata.get("support_visuel_seul"):
                            ui.label(
                                "Support visuel uniquement : l’interaction UNESS originale "
                                "n’est pas reconstruite."
                            ).classes(
                                "text-sm text-amber-800 dark:text-amber-300 whitespace-pre-wrap mt-2"
                            )
```

Add right after it (same indentation level, inside the same `with` block):

```python
                        if question_metadata.get("verification_status") == "unsupported":
                            ui.label(
                                "⚠️ Vérification IA non disponible pour cette question — seule la "
                                "correction officielle UNESS est garantie exacte."
                            ).classes(
                                "text-sm text-amber-800 dark:text-amber-300 whitespace-pre-wrap mt-2"
                            )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_qcm_replay.py -v`
Expected: All PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/components/qcm_replay.py tests/test_qcm_replay.py
git commit -m "feat: warn in the correction view when a question's visual wasn't AI-verified"
```

---

## Part B — Diagnostic UNESS panel in Paramètres

### Task 5: Promote `_locate_bridge` to a public, reusable function

**Files:**
- Modify: `backend/core/uness/gemini_autocorrect.py:302-328` (`_locate_bridge` → `locate_bridge`)

**Interfaces:**
- Produces: `gemini_autocorrect.locate_bridge(quiz_title: str, collected_at: str) -> Path` — used internally by `retry_failed_quiz` (Task's only existing caller, updated in place) and by Task 6's `diagnostics.py`.

- [ ] **Step 1: Rename the function and its one call site**

In `backend/core/uness/gemini_autocorrect.py`:
- Rename `def _locate_bridge(...)` (line 302) to `def locate_bridge(...)`.
- Update its docstring's first line to drop the leading underscore reference if present (it doesn't reference its own name, so likely no change needed — just confirm).
- Find the one call site inside `retry_failed_quiz` (`bridge_path = _locate_bridge(quiz_title, collected_at)`, around line 346) and update it to `bridge_path = locate_bridge(quiz_title, collected_at)`.

- [ ] **Step 2: Run the gemini_autocorrect test suite to confirm nothing broke**

Run: `python -m pytest tests/test_gemini_autocorrect.py -v`
Expected: PASS (pure rename, no behavior change). If a test imports `_locate_bridge` by name, update that import too.

- [ ] **Step 3: Commit**

```bash
git add backend/core/uness/gemini_autocorrect.py
git commit -m "refactor: make locate_bridge public — needed by the new diagnostics module"
```

---

### Task 6: `backend/core/uness/diagnostics.py` — build the per-annale report

**Files:**
- Create: `backend/core/uness/diagnostics.py`
- Test: `tests/test_uness_diagnostics.py`

**Interfaces:**
- Consumes: `import_service.TO_REVIEW_DIR`, `import_service.ARCHIVE_DIR`, `import_service.VERIFIED_DIR`, `import_service.import_verified_directory()`, `gemini_autocorrect.locate_bridge()` (Task 5), `local_store.list_uness_annales()`, `local_store.list_annale_sessions(annale_id)`, `local_store.list_pending_uness_correction_failures()`.
- Produces:
  ```python
  def build_report() -> dict:
      """Returns {"annales": [...], "pending": [...]}."""
  ```
  Each entry in `annales`:
  ```python
  {
      "annale": dict,        # local_store row (id, titre, matiere, faculte, annee, source_url, ...)
      "quizzes": [
          {"title": str, "status": "imported" | "retry_pending" | "blocked" | "never_attempted",
           "detail": dict},  # shape depends on status, see Step 3 below
      ],
  }
  ```
  Each entry in `pending` is one item straight from `import_verified_directory()`'s
  `result["pending_tag"]` (already `{"source_url", "faculte", "niveau", "annee", "matiere", "titre", "files"}`).

- [ ] **Step 1: Write the failing test for the bridge-scanning helper**

Create `tests/test_uness_diagnostics.py`:

```python
"""Tests for the read-only UNESS import diagnostics report."""

from __future__ import annotations

import json

import pytest

from backend.core.reviews import local_store
from backend.core.uness import diagnostics, import_service


@pytest.fixture(autouse=True)
def isolated_store(tmp_path, monkeypatch):
    database = tmp_path / "synapse-test.db"
    monkeypatch.setattr(local_store, "DB_PATH", database)
    monkeypatch.setattr(local_store, "_DB", None)
    local_store.init_db()
    yield
    if local_store._DB is not None:
        local_store._DB.close()
    monkeypatch.setattr(local_store, "_DB", None)


@pytest.fixture
def uness_dirs(tmp_path, monkeypatch):
    to_review = tmp_path / "à_vérifier"
    archives = tmp_path / "archives"
    verified = tmp_path / "vérifiés"
    to_review.mkdir()
    archives.mkdir()
    verified.mkdir()
    monkeypatch.setattr(import_service, "TO_REVIEW_DIR", to_review)
    monkeypatch.setattr(import_service, "ARCHIVE_DIR", archives)
    monkeypatch.setattr(import_service, "VERIFIED_DIR", verified)
    return {"to_review": to_review, "archives": archives, "verified": verified}


def _bridge_file(path, *, source_url, collected_at, title):
    path.write_text(
        json.dumps(
            {
                "contents": [{"title": title, "html": "<div></div>", "images": []}],
                "source": {"source_url": source_url, "collected_at": collected_at, "collection_status": "submitted"},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def test_latest_collection_wins_when_a_source_url_was_scraped_twice(uness_dirs):
    session_a = uness_dirs["to_review"] / "session-A"
    session_b = uness_dirs["to_review"] / "session-B"
    session_a.mkdir()
    session_b.mkdir()
    _bridge_file(
        session_a / "dp1.json", source_url="https://x/1", collected_at="2026-01-01T00:00:00+00:00", title="DP1\nTest"
    )
    _bridge_file(
        session_b / "dp1.json", source_url="https://x/1", collected_at="2026-02-01T00:00:00+00:00", title="DP1\nTest"
    )
    _bridge_file(
        session_b / "dp2.json", source_url="https://x/1", collected_at="2026-02-01T00:00:00+00:00", title="DP2\nTest"
    )

    titles = diagnostics._latest_quiz_titles_by_source_url()

    # Only session B's titles (the more recent collected_at) count — session A's
    # lone DP1 must not shrink the reference list back down to one quiz.
    assert titles["https://x/1"] == ["DP1", "DP2"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_uness_diagnostics.py -v`
Expected: FAIL — `backend.core.uness.diagnostics` doesn't exist yet.

- [ ] **Step 3: Implement `diagnostics.py`**

Create `backend/core/uness/diagnostics.py`:

```python
"""Read-only reporting over the UNESS collect → correct → import pipeline:
for each known annale, which of its quizzes are imported, retrying after a
correction failure, permanently blocked, or were collected but never even
submitted to Gemini. Kept separate from import_service.py (which mutates
state) so this module can be called freely from a Settings page without side
effects beyond the one explicit, already-idempotent import pass described
below."""

from __future__ import annotations

import json
from typing import Any

from backend.core.reviews import local_store
from backend.core.uness import gemini_autocorrect, import_service


def _iter_bridge_files():
    """Every raw bridge JSON (has a "contents" key) under à_vérifier/ and
    archives/ — successfully imported bridges are moved, not deleted, into
    archives/session-<stamp>/, so a fully-imported annale's history stays
    scannable here too."""
    for directory in (import_service.TO_REVIEW_DIR, import_service.ARCHIVE_DIR):
        if not directory.is_dir():
            continue
        for path in directory.rglob("*.json"):
            if path.name.startswith("."):
                continue
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if isinstance(payload, dict) and "contents" in payload:
                yield payload


def _latest_quiz_titles_by_source_url() -> dict[str, list[str]]:
    """For each source_url, the quiz titles (first line only — matches how
    `gemini_conversion.convert_with_bridge` builds `exam.title`) of its most
    recent collection. Re-scraping the same URL produces a fresh batch of
    quiz titles each time; only the latest batch is the reference — an older,
    superseded collection must not make the reference list look bigger (or
    different) than what actually exists today."""
    best_collected_at: dict[str, str] = {}
    titles: dict[str, list[str]] = {}
    for bridge in _iter_bridge_files():
        source = bridge.get("source", {})
        source_url = str(source.get("source_url", "")).strip()
        collected_at = str(source.get("collected_at", ""))
        if not source_url or not collected_at:
            continue
        contents = bridge.get("contents", [])
        quiz_titles = [
            str(item.get("title", "")).splitlines()[0]
            for item in contents
            if isinstance(item, dict) and item.get("title")
        ]
        if not quiz_titles:
            continue
        current_best = best_collected_at.get(source_url)
        if current_best is None or collected_at > current_best:
            # A strictly newer collection supersedes everything seen so far.
            best_collected_at[source_url] = collected_at
            titles[source_url] = list(quiz_titles)
        elif collected_at == current_best:
            # Same collection run, a different quiz's bridge file — every
            # quiz collected together shares the exact same collected_at
            # (collector.py builds one manifest after the whole loop and
            # reuses it verbatim in each quiz's own bridge file), so this
            # must union in rather than overwrite, or whichever file the
            # filesystem walk visits last would "win" and every sibling
            # quiz collected in the same run would silently vanish from
            # the reference list.
            for title in quiz_titles:
                if title not in titles[source_url]:
                    titles[source_url].append(title)
    return titles


def _quiz_label(course_title: str) -> str:
    """`course_title` on an imported session is "{exam meta title} — {quiz}"
    (see import_service._to_practice_question / exam.title construction in
    gemini_conversion.convert_with_bridge) — this pulls out just the quiz
    label ("DP1") for matching against the reference list."""
    return course_title.rsplit(" — ", 1)[-1].strip()


def _blocked_titles(errors: list[dict[str, str]]) -> dict[tuple[str, str], str]:
    """Map (source_url, quiz label) -> error message for every file that just
    failed import validation (assert_verified_exam, missing bridge, etc.) —
    these files stay in VERIFIED_DIR untouched on failure, so they're always
    still readable here. Keyed by the (source_url, label) pair rather than
    label alone — UNESS quiz labels ("DP1", "QI1"...) are reused across
    unrelated annales, so a label-only key lets one annale's blocked entry
    silently clobber another's, hiding a real failure behind
    "never_attempted"."""
    blocked: dict[tuple[str, str], str] = {}
    for error in errors:
        matches = list(import_service.VERIFIED_DIR.rglob(error["file"]))
        if not matches:
            continue
        try:
            payload = json.loads(matches[0].read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        source_url = str(payload.get("provenance", {}).get("source_url", "")).strip()
        title = str(payload.get("title", ""))
        if not source_url or not title:
            continue
        blocked[(source_url, _quiz_label(title))] = error["error"]
    return blocked


def _retry_pending_by_source_url() -> dict[str, list[dict[str, Any]]]:
    """Group pending correction-failure rows by the source_url they belong
    to — the table itself only stores (quiz_title, collected_at), so each
    row's bridge is relocated the same way retry_failed_quiz already does."""
    grouped: dict[str, list[dict[str, Any]]] = {}
    for failure in local_store.list_pending_uness_correction_failures():
        try:
            bridge_path = gemini_autocorrect.locate_bridge(failure["quiz_title"], failure["collected_at"])
            bridge = json.loads(bridge_path.read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError, json.JSONDecodeError):
            continue
        source_url = str(bridge.get("source", {}).get("source_url", "")).strip()
        if not source_url:
            continue
        label = str(failure["quiz_title"]).splitlines()[0]
        grouped.setdefault(source_url, []).append({**failure, "title": label})
    return grouped


def build_report() -> dict[str, Any]:
    """Imports everything currently importable (safe to call repeatedly —
    see import_service's dedup guards), then reports the state of every quiz
    known to have been collected at least once."""
    import_result = import_service.import_verified_directory()
    reference = _latest_quiz_titles_by_source_url()
    blocked = _blocked_titles(import_result["errors"])
    retry_pending = _retry_pending_by_source_url()

    annale_reports = []
    for annale in local_store.list_uness_annales():
        source_url = annale["source_url"]
        imported_labels = {
            _quiz_label(session["course_title"])
            for session in local_store.list_annale_sessions(annale["id"])
        }
        ref_titles = reference.get(source_url) or sorted(imported_labels)
        retry_for_url = {entry["title"]: entry for entry in retry_pending.get(source_url, [])}

        quizzes = []
        for title in ref_titles:
            if title in imported_labels:
                quizzes.append({"title": title, "status": "imported", "detail": {}})
            elif title in retry_for_url:
                failure = retry_for_url[title]
                quizzes.append({
                    "title": title,
                    "status": "retry_pending",
                    "detail": {
                        "error": failure["error_message"],
                        "attempts": failure["attempts"],
                        "next_retry_at": failure["next_retry_at"],
                        "failure_id": failure["id"],
                    },
                })
            elif (source_url, title) in blocked:
                quizzes.append({"title": title, "status": "blocked", "detail": {"error": blocked[(source_url, title)]}})
            else:
                quizzes.append({"title": title, "status": "never_attempted", "detail": {}})
        annale_reports.append({"annale": annale, "quizzes": quizzes})

    return {"annales": annale_reports, "pending": import_result["pending_tag"]}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_uness_diagnostics.py -v`
Expected: PASS.

- [ ] **Step 5: Add three more tests covering the remaining statuses**

Append to `tests/test_uness_diagnostics.py`:

```python
def test_build_report_marks_a_quiz_imported(uness_dirs):
    session = uness_dirs["to_review"] / "session-A"
    session.mkdir()
    _bridge_file(
        session / "dp1.json", source_url="https://x/1", collected_at="2026-01-01T00:00:00+00:00", title="DP1\nTest"
    )
    annale_id = local_store.create_uness_annale(
        source_url="https://x/1", collected_at="2026-01-01T00:00:00+00:00", faculte="Fac",
        niveau="N1", annee=2026, matiere="Cardio", titre="Cardio — Fac — 2026", type_annale="matiere",
    )
    from backend.core.practice.models import PracticeDifficulty, PracticeKind, PracticeSessionSpec, QuestionKind
    session_id = local_store.create_ai_practice_session(
        spec=PracticeSessionSpec(
            practice_kind=PracticeKind.QCM, total_questions=1, open_questions=0, closed_questions=1,
            course_id="", course_title="Cardio — Fac — 2026 — DP1", item_number="",
            difficulty=PracticeDifficulty.EDN,
        ),
        questions=[{"kind": QuestionKind.CLOSED, "prompt": "Q", "choices": ["a"], "answer": "[]", "explanation": "e"}],
        model="test",
    )
    local_store.set_session_annale_id(session_id, annale_id)

    report = diagnostics.build_report()

    annale_entry = next(a for a in report["annales"] if a["annale"]["id"] == annale_id)
    assert annale_entry["quizzes"] == [{"title": "DP1", "status": "imported", "detail": {}}]


def test_build_report_marks_a_quiz_retry_pending(uness_dirs):
    session = uness_dirs["to_review"] / "session-A"
    session.mkdir()
    _bridge_file(
        session / "dp1.json", source_url="https://x/1", collected_at="2026-01-01T00:00:00+00:00", title="DP1\nTest"
    )
    annale_id = local_store.create_uness_annale(
        source_url="https://x/1", collected_at="2026-01-01T00:00:00+00:00", faculte="Fac",
        niveau="N1", annee=2026, matiere="Cardio", titre="Cardio — Fac — 2026", type_annale="matiere",
    )
    failure_id = local_store.record_uness_correction_failure(
        bridge_folder=str(session), quiz_title="DP1\nTest", collected_at="2026-01-01T00:00:00+00:00",
        error_message="Réponse incomplète : 2/3 questions",
    )
    failure_row = local_store.get_uness_correction_failure(failure_id)

    report = diagnostics.build_report()

    annale_entry = next(a for a in report["annales"] if a["annale"]["id"] == annale_id)
    assert annale_entry["quizzes"] == [{
        "title": "DP1", "status": "retry_pending",
        "detail": {
            "error": "Réponse incomplète : 2/3 questions",
            "attempts": failure_row["attempts"],
            "next_retry_at": failure_row["next_retry_at"],
            "failure_id": failure_id,
        },
    }]


def test_build_report_marks_a_never_attempted_quiz(uness_dirs):
    session = uness_dirs["to_review"] / "session-A"
    session.mkdir()
    _bridge_file(
        session / "dp1.json", source_url="https://x/1", collected_at="2026-01-01T00:00:00+00:00", title="DP1\nTest"
    )
    _bridge_file(
        session / "dp2.json", source_url="https://x/1", collected_at="2026-01-01T00:00:00+00:00", title="DP2\nTest"
    )
    annale_id = local_store.create_uness_annale(
        source_url="https://x/1", collected_at="2026-01-01T00:00:00+00:00", faculte="Fac",
        niveau="N1", annee=2026, matiere="Cardio", titre="Cardio — Fac — 2026", type_annale="matiere",
    )
    # DP1 was never corrected or logged as a failure (the silent-crash case).

    report = diagnostics.build_report()

    annale_entry = next(a for a in report["annales"] if a["annale"]["id"] == annale_id)
    statuses = {q["title"]: q["status"] for q in annale_entry["quizzes"]}
    assert statuses == {"DP1": "never_attempted", "DP2": "never_attempted"}


def test_build_report_lists_pending_tag_source_urls_separately(uness_dirs):
    verified = uness_dirs["verified"]
    verified.joinpath("dp1-corrige.json").write_text(
        json.dumps({
            "schema_version": 1, "faculty": "Fac", "level": "N1", "year": 2026,
            "title": "Cardio — Fac — 2026 — DP1", "dp_context": {},
            "questions": [{
                "id": "q1", "type_question": "QRU", "enonce": "Q?", "propositions": [
                    {"id": "p1", "texte": "a", "reponse_uness": True, "verdict_ia": True,
                     "explication_ia": "e", "confiance_ia": 0.9, "statut": "concordant"}
                ], "verification_status": "verified",
            }],
            "provenance": {"source": "Gemini+UNESS", "source_url": "https://x/2",
                           "collected_at": "2026-01-01T00:00:00+00:00", "collection_status": "submitted"},
            "metadata": {"subject": "Cardio", "exam_type": "partiel"},
        }, ensure_ascii=False),
        encoding="utf-8",
    )

    report = diagnostics.build_report()

    assert [p["source_url"] for p in report["pending"]] == ["https://x/2"]
    assert report["annales"] == []
```

- [ ] **Step 6: Run the full new test file**

Run: `python -m pytest tests/test_uness_diagnostics.py -v`
Expected: All 5 tests PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/core/uness/diagnostics.py tests/test_uness_diagnostics.py
git commit -m "feat: add read-only UNESS import diagnostics report"
```

---

### Task 7: Diagnostic UNESS section in Paramètres

**Files:**
- Create: `frontend/components/uness_diagnostic_panel.py`
- Modify: `frontend/pages/settings_cockpit.py` (add CSS classes + call the new panel)

**Interfaces:**
- Consumes: `diagnostics.build_report()` (Task 6), `local_store.reset_uness_correction_failure_attempts`, `gemini_autocorrect.retry_failed_quiz`, `import_service.import_verified_directory`.
- Produces: `render(container: ui.element) -> None` — called once from `settings_cockpit.render_settings_cockpit()`.

- [ ] **Step 1: Add the CSS classes**

In `frontend/pages/settings_cockpit.py`, append to the end of the `_CSS` string (after `.se-uness-status`, before the closing `"""`):

```css
.se-diag-annale { border:1px solid var(--border); border-radius:8px; padding:12px 14px; margin-bottom:8px; }
.se-diag-head { display:flex; align-items:center; justify-content:space-between; gap:8px; }
.se-diag-title { font-size:13px; font-weight:600; color:var(--text); }
.se-diag-ratio { font-size:12px; font-weight:600; }
.se-diag-ratio.full { color:var(--success); }
.se-diag-ratio.partial { color:var(--warning); }
.se-diag-quiz-row { display:flex; align-items:center; justify-content:space-between; gap:8px; padding:4px 0; font-size:12.5px; }
.se-diag-quiz-detail { color:var(--text-muted); font-size:11.5px; }
```

- [ ] **Step 2: Write `uness_diagnostic_panel.py`**

Create `frontend/components/uness_diagnostic_panel.py`:

```python
"""Diagnostic UNESS panel for Paramètres — one card per annale, one row per
quiz, showing exactly why a quiz isn't imported yet and a button to fix it.
Kept out of settings_cockpit.py to keep that file to layout/wiring only."""

from __future__ import annotations

import asyncio

from nicegui import ui

from backend.core.reviews import local_store
from backend.core.uness import diagnostics, gemini_autocorrect, import_service

_STATUS_ICONS = {
    "imported": "✅",
    "retry_pending": "🔄",
    "blocked": "❌",
    "never_attempted": "⬜",
}


def render(container: ui.element) -> None:
    # Every element below must be constructed while `container`'s slot is
    # active — NiceGUI parents a new element to whatever slot is on top of
    # the stack AT CONSTRUCTION TIME (see nicegui/element.py), not to
    # whatever `container` object a function happens to receive as an
    # argument. Building `body`/labels/etc. before entering `with
    # container:` (as an earlier draft of this function did) parents them
    # to the CALLER's currently-active slot instead — `container` itself
    # ends up permanently empty, and the panel "works" only by accident,
    # landing as a stray sibling wherever the caller happened to be.
    with container:
        ui.label("DIAGNOSTIC UNESS").classes("se-label")
        body = ui.column().classes("w-full gap-0")

        def _refresh() -> None:
            body.clear()
            with body:
                with ui.row().classes("w-full justify-end mb-2"):
                    ui.button("Rafraîchir", icon="refresh", on_click=_refresh).props(
                        "flat dense size=sm color=primary"
                    )
                report = diagnostics.build_report()
                if not report["annales"] and not report["pending"]:
                    ui.label("Aucune annale UNESS collectée pour le moment.").classes(
                        "text-sm text-slate-500"
                    )
                for entry in report["annales"]:
                    _render_annale(entry)
                for pending in report["pending"]:
                    _render_pending(pending)

        async def _retry(failure_id: int) -> None:
            local_store.reset_uness_correction_failure_attempts(failure_id)
            result = await asyncio.to_thread(gemini_autocorrect.retry_failed_quiz, failure_id)
            if result["success"]:
                ui.notify("✅ Quiz corrigé et importé.", type="positive")
                await asyncio.to_thread(import_service.import_verified_directory)
            else:
                ui.notify(f"❌ Toujours en échec : {result['error']}", type="negative")
            _refresh()

        def _render_annale(entry: dict) -> None:
            annale = entry["annale"]
            quizzes = entry["quizzes"]
            imported_count = sum(1 for q in quizzes if q["status"] == "imported")
            total = len(quizzes)
            ratio_class = "full" if imported_count == total else "partial"
            with ui.element("div").classes("se-diag-annale"):
                with ui.element("div").classes("se-diag-head"):
                    ui.label(annale["titre"]).classes("se-diag-title")
                    ui.label(f"{imported_count}/{total}").classes(f"se-diag-ratio {ratio_class}")
                for quiz in quizzes:
                    if quiz["status"] == "imported":
                        continue
                    with ui.element("div").classes("se-diag-quiz-row"):
                        ui.label(f"{_STATUS_ICONS[quiz['status']]} {quiz['title']}")
                        if quiz["status"] == "retry_pending":
                            ui.label(
                                f"tentative {quiz['detail']['attempts']}/3 — {quiz['detail']['error']}"
                            ).classes("se-diag-quiz-detail")

                            # NiceGUI runs an async on_click handler as its OWN
                            # properly-slotted task when the handler is passed
                            # directly (not wrapped in asyncio.create_task, which
                            # would spawn a task with an empty slot stack — see
                            # the identical pattern already used for this same
                            # button on /annales, frontend/pages/annales.py). The
                            # default-arg trick captures this row's failure_id
                            # since the loop variable itself would be stale by
                            # the time the button is actually clicked.
                            async def _on_retry_click(failure_id: int = quiz["detail"]["failure_id"]) -> None:
                                await _retry(failure_id)

                            ui.button("Relancer", on_click=_on_retry_click).props(
                                "flat dense size=sm color=primary"
                            )
                        elif quiz["status"] == "blocked":
                            ui.label(quiz["detail"]["error"]).classes("se-diag-quiz-detail")
                        elif quiz["status"] == "never_attempted":
                            ui.label(
                                "Jamais soumis à Gemini — utilise « Corriger dossier "
                                "existant » sur /annales pour ce dossier de collecte."
                            ).classes("se-diag-quiz-detail")

        def _render_pending(pending: dict) -> None:
            with ui.element("div").classes("se-diag-annale"):
                with ui.element("div").classes("se-diag-head"):
                    ui.label(pending["titre"]).classes("se-diag-title")
                    ui.label("en attente de matière").classes("se-diag-ratio partial")
                ui.label(f"{len(pending['files'])} quiz corrigés, matière à qualifier sur /annales.").classes(
                    "se-diag-quiz-detail"
                )

        _refresh()
```

- [ ] **Step 3: Wire it into `settings_cockpit.py`**

In `frontend/pages/settings_cockpit.py`, add the import near the top (with the other project imports):

```python
from frontend.components.uness_diagnostic_panel import render as render_uness_diagnostics
```

At the end of `render_settings_cockpit()` (after the existing `UNESS` section's closing, i.e. after whatever is currently the last statement in the function), add:

```python
        render_uness_diagnostics(ui.column().classes("w-full"))
```

- [ ] **Step 4: Manual verification**

Start the app (`preview_start` with the project's dev server config, or however this session has been launching it), navigate to `/settings`, and confirm:
- A "DIAGNOSTIC UNESS" section appears below the existing "UNESS" import card.
- The Dermatologie annale shows `6/8` (or whatever the current real count is) with mDP4 listed as `🔄` with a working "Relancer" button.
- An annale with 8/8 shows no quiz rows (only the ratio).
- Clicking "Rafraîchir" re-runs the scan without a full page reload.
- No Python traceback in the terminal running the app.

- [ ] **Step 5: Commit**

```bash
git add frontend/components/uness_diagnostic_panel.py frontend/pages/settings_cockpit.py
git commit -m "feat: add Diagnostic UNESS panel to Paramètres"
```

---

## Self-Review Notes (for the plan author, not a task)

- Spec coverage: Partie A (constant move, gemini_conversion sanitization, assert_verified_exam relaxation, qcm_replay warning) → Tasks 1-4. Partie B (detection model, `build_report`, UI, actions) → Tasks 5-7. The spec's suggestion to extract `_open_tag_dialog` into a shared function was intentionally **not** followed for the "pending" bucket's UI: Task 7 only *displays* pending groups (count + "qualifier sur /annales" pointer) rather than duplicating the multi-annale batch-tagging dialog inline — reduces this plan's risk (no refactor of currently-working, closure-heavy code in `annales.py`) while still satisfying "actions directes" for the two buckets that dominate real usage (`retry_pending`, and the already-existing "Relancer"/reload flow). If inline qualification from Paramètres turns out to matter in practice, it's a follow-up plan, not a blocker here.
- Type consistency checked: `build_report()`'s return shape (`{"annales": [...], "pending": [...]}`, each quiz `{"title", "status", "detail"}`) is used identically in Task 6's tests and Task 7's panel.
