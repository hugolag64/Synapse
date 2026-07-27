# Façade métier d’évaluation — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Centraliser l’enregistrement des évaluations QCM, auto-évaluation et OIC derrière une façade qui retourne des conséquences métier consultatives.

**Architecture:** `backend/core/evaluation` contient des dataclasses sans dépendance UI et un service qui délègue aux stockages existants. Les adaptateurs conservent les tables historiques (`qcm_sessions`, `study_sessions`, `oic_attempts`) et les règles de répétition, tandis que l’outcome normalise l’identifiant persisté, les propositions de lacune et la recommandation.

**Tech Stack:** Python 3.11+, SQLite, pytest, dataclasses.

## Global Constraints

- Réutiliser les tables existantes ; aucune migration ni double stockage.
- Ne créer aucune interface ni onglet Évaluation dans ce lot.
- Ne pas modifier `mastery.py`, ses scores ou ses statuts.
- Une erreur isolée ne crée jamais de `weak_point`.
- Conserver le seuil `RECURRENCE_THRESHOLD = 2`.
- Les recommandations sont uniquement `none`, `review_errors`, `practice_oic` ou `consolidate`.
- Aucune tâche ni date de planning ne peut être créée par la façade.

---

## File structure

- Create: `backend/core/evaluation/__init__.py` — export public de la façade.
- Create: `backend/core/evaluation/models.py` — `EvaluationInput`, `EvaluationOutcome`, sources et recommandations.
- Create: `backend/core/evaluation/service.py` — `record_evaluation`.
- Create: `tests/test_evaluation_service.py` — contrat de façade et persistance réelle SQLite.

### Task 1: Modèle public et recommandations pures

**Files:**
- Create: `backend/core/evaluation/__init__.py`
- Create: `backend/core/evaluation/models.py`
- Create: `tests/test_evaluation_service.py`

**Interfaces:**
- Produces: `EvaluationSource = Literal["qcm", "auto_eval", "oic"]`.
- Produces: `EvaluationRecommendation = Literal["none", "review_errors", "practice_oic", "consolidate"]`.
- Produces: immutable `EvaluationInput` and `EvaluationOutcome` dataclasses.
- Produces: `recommend_evaluation(input: EvaluationInput) -> EvaluationRecommendation`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_evaluation_service.py`:

```python
from backend.core.evaluation.models import EvaluationInput, recommend_evaluation


def test_failed_qcm_with_error_type_recommends_error_review():
    evaluation = EvaluationInput(
        source="qcm", course_id="course-1", item_number="75",
        score_percent=55, error_types=("raisonnement",),
    )

    assert recommend_evaluation(evaluation) == "review_errors"


def test_low_confidence_auto_evaluation_recommends_error_review():
    evaluation = EvaluationInput(
        source="auto_eval", course_id="course-1", item_number="75", confidence=2,
    )

    assert recommend_evaluation(evaluation) == "review_errors"


def test_low_oic_score_recommends_oic_practice():
    evaluation = EvaluationInput(
        source="oic", course_id="course-1", item_number="75", score_percent=40,
    )

    assert recommend_evaluation(evaluation) == "practice_oic"


def test_successful_evaluation_recommends_consolidation():
    evaluation = EvaluationInput(
        source="qcm", course_id="course-1", item_number="75", score_percent=85,
    )

    assert recommend_evaluation(evaluation) == "consolidate"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_evaluation_service.py -q`

Expected: FAIL during collection because `backend.core.evaluation` does not exist.

- [ ] **Step 3: Write minimal implementation**

Create `backend/core/evaluation/models.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

EvaluationSource = Literal["qcm", "auto_eval", "oic"]
EvaluationRecommendation = Literal["none", "review_errors", "practice_oic", "consolidate"]


@dataclass(frozen=True)
class EvaluationInput:
    source: EvaluationSource
    course_id: str
    item_number: str = ""
    course_title: str = ""
    context: str = "college"
    score_percent: float | None = None
    confidence: int | None = None
    error_types: tuple[str, ...] = ()
    detail: str | None = None
    platform: str | None = None
    session_date: str | None = None
    oic_code: str | None = None
    questions_json: str | None = None
    course_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class EvaluationOutcome:
    source: EvaluationSource
    persisted_id: int
    gap_proposal_ids: tuple[int, ...] = ()
    recommendation: EvaluationRecommendation = "none"
    ignored_signals: tuple[str, ...] = ()


def recommend_evaluation(evaluation: EvaluationInput) -> EvaluationRecommendation:
    if evaluation.source == "oic" and (evaluation.score_percent or 0) < 70:
        return "practice_oic"
    if evaluation.source == "auto_eval" and (evaluation.confidence or 5) <= 2:
        return "review_errors"
    if evaluation.source == "qcm" and (
        (evaluation.score_percent is not None and evaluation.score_percent < 70)
        or evaluation.error_types
    ):
        return "review_errors"
    if evaluation.score_percent is not None and evaluation.score_percent >= 70:
        return "consolidate"
    return "none"
```

Create `backend/core/evaluation/__init__.py` exporting `EvaluationInput`, `EvaluationOutcome` and `record_evaluation` (the latter is supplied in Task 2).

- [ ] **Step 4: Run tests to verify they pass**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_evaluation_service.py -q`

Expected: PASS for the recommendation tests.

- [ ] **Step 5: Commit**

```powershell
git add -- backend/core/evaluation/__init__.py backend/core/evaluation/models.py tests/test_evaluation_service.py
git commit -m "feat: define evaluation domain models"
```

### Task 2: Façade de persistance et outcome

**Files:**
- Create: `backend/core/evaluation/service.py`
- Modify: `backend/core/evaluation/__init__.py`
- Modify: `tests/test_evaluation_service.py`

**Interfaces:**
- Consumes: `EvaluationInput`, `local_store.add_qcm_session_full`, `local_store.add_study_session`, `item_service.save_item_oic_attempt`.
- Produces: `record_evaluation(evaluation: EvaluationInput) -> EvaluationOutcome`.

- [ ] **Step 1: Write the failing tests**

Append these tests with the isolated database fixture already used by `tests/test_review_completion_service.py`:

```python
def test_record_qcm_evaluation_persists_and_returns_recurrence_proposals():
    result = record_evaluation(EvaluationInput(
        source="qcm", course_id="course-1", course_title="Cardiologie",
        item_number="75", platform="Synapse", session_date="2026-07-27",
        score_percent=55, error_types=("raisonnement",),
    ))

    assert result.source == "qcm"
    assert result.persisted_id > 0
    assert result.recommendation == "review_errors"
    assert local_store.get_qcm_sessions_all(course_id="course-1")[0]["score_percent"] == 55


def test_record_auto_evaluation_persists_without_immediate_weak_point():
    result = record_evaluation(EvaluationInput(
        source="auto_eval", course_id="course-1", item_number="75",
        confidence=2, error_types=("raisonnement",), detail="Erreur clinique",
    ))

    with local_store._conn() as con:
        weak_points = con.execute("SELECT COUNT(*) FROM weak_points").fetchone()[0]
    assert result.recommendation == "review_errors"
    assert result.persisted_id > 0
    assert weak_points == 0


def test_record_oic_evaluation_requires_canonical_aliases():
    with pytest.raises(ValueError, match="course_ids"):
        record_evaluation(EvaluationInput(
            source="oic", course_id="course-1", oic_code="OIC-1", score_percent=80,
        ))


def test_record_oic_evaluation_preserves_existing_attempt_and_success_state():
    local_store.upsert_lisa_oic(
        "course-1", [{"oic_code": "OIC-1", "intitule": "Évaluer", "rang": "A"}]
    )

    result = record_evaluation(EvaluationInput(
        source="oic", course_id="course-1", course_ids=("course-1",),
        oic_code="OIC-1", score_percent=85, questions_json="[]",
    ))

    row = local_store.get_lisa_oic("course-1")[0]
    assert result.persisted_id > 0
    assert result.recommendation == "consolidate"
    assert local_store.get_oic_attempts(row["id"])[0]["session_score"] == 85
    assert row["mastered"] == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_evaluation_service.py -q`

Expected: FAIL because `record_evaluation` has not been implemented.

- [ ] **Step 3: Write minimal implementation**

Create `backend/core/evaluation/service.py`:

```python
from __future__ import annotations

import datetime

from backend.core.evaluation.models import EvaluationInput, EvaluationOutcome, recommend_evaluation
from backend.core.lisa import item_service
from backend.core.reviews import local_store


def record_evaluation(evaluation: EvaluationInput) -> EvaluationOutcome:
    if evaluation.source == "qcm":
        persisted_id = local_store.add_qcm_session_full(
            platform=evaluation.platform or "Synapse",
            session_date=evaluation.session_date or datetime.date.today().isoformat(),
            course_id=evaluation.course_id,
            course_title=evaluation.course_title,
            item_number=evaluation.item_number,
            score_percent=evaluation.score_percent,
            error_types=list(evaluation.error_types),
            comments=evaluation.detail,
        )
        gap_proposal_ids = _pending_gap_ids(evaluation.item_number, evaluation.error_types)
    elif evaluation.source == "auto_eval":
        persisted_id = local_store.add_study_session(
            course_id=evaluation.course_id,
            course_title=evaluation.course_title,
            item_number=evaluation.item_number,
            context=evaluation.context,
            confidence=evaluation.confidence,
            weak_category=evaluation.error_types[0] if evaluation.error_types else None,
            weak_detail=evaluation.detail,
        )
        gap_proposal_ids = _pending_gap_ids(evaluation.item_number, evaluation.error_types)
    elif evaluation.source == "oic":
        if not evaluation.course_ids:
            raise ValueError("course_ids est requis pour une évaluation OIC")
        if not evaluation.oic_code:
            raise ValueError("oic_code est requis pour une évaluation OIC")
        persisted_id = item_service.save_item_oic_attempt(
            evaluation.course_ids,
            evaluation.oic_code,
            int(evaluation.score_percent or 0),
            evaluation.questions_json or "[]",
        )
        gap_proposal_ids = ()
    else:
        raise ValueError(f"Source d'évaluation inconnue: {evaluation.source!r}")

    return EvaluationOutcome(
        source=evaluation.source,
        persisted_id=persisted_id,
        gap_proposal_ids=tuple(gap_proposal_ids),
        recommendation=recommend_evaluation(evaluation),
    )
```

Implement `_pending_gap_ids(item_number, error_types)` by filtering `local_store.get_pending_proposals()` to the same item and error types. It must return a tuple of integers and must not create or alter proposals itself.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_evaluation_service.py tests/test_recurring_study_feedback.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add -- backend/core/evaluation/__init__.py backend/core/evaluation/service.py tests/test_evaluation_service.py
git commit -m "feat: add evaluation recording facade"
```

## Plan self-review

- **Spec coverage:** Task 1 supplies normalized input, outcome and all four recommendation statuses. Task 2 preserves historical persistence and recurrence while returning an explicit outcome. The façade is ready for the future QCM cockpit entry point without changing existing UI in this lot.
- **Placeholder scan:** no unfinished implementation, unspecified test or implicit interface is left in the task steps.
- **Type consistency:** every task imports `EvaluationInput`, `EvaluationOutcome` and `record_evaluation` from `backend.core.evaluation`; source strings and recommendation strings match the model literals.
