# UNESS Gériatrie Prototype Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Import one Gériatrie UNESS annale from a user-provided URL, normalize its corrected questions, verify every proposition with the existing AI service, and expose the result for a local Synapse QCM session.

**Architecture:** The first prototype is URL-driven and user-assisted: the user provides the exact annale URL while Chrome remains authenticated, and the collector produces a local raw artifact after the user confirms submission. A backend normalizer converts that artifact to a canonical JSON model, then an AI verifier enriches each proposition while preserving the UNESS answer. The existing QCM session/history pipeline consumes the validated import; no multi-faculty crawler or hotspot reconstruction is included in this iteration.

**Tech Stack:** Python 3.11, Pydantic/dataclasses already used by the backend, pytest, existing AI routing service, existing SQLite review store, Chrome browser automation for the collection step.

## Global Constraints

- Never request or store UNESS credentials, cookies, local storage, or session tokens.
- Require explicit confirmation before the first irreversible “Tout envoyer et terminer” submission.
- Preserve `reponse_uness` separately from `verdict_ia`; never overwrite the official correction.
- Produce an explanation for every proposition, whether true or false.
- Treat complex point-and-click questions as visual-only when their interaction geometry cannot be extracted.
- Keep imported artifacts local and retain provenance (`source_url`, faculty, level, subject, year).

---

### Task 1: Canonical UNESS data model and JSON validation

**Files:**
- Create: `backend/core/uness/__init__.py`
- Create: `backend/core/uness/models.py`
- Create: `backend/core/uness/json_io.py`
- Test: `tests/test_uness_models.py`

**Interfaces:**
- `UnessExam.from_dict(payload: dict) -> UnessExam`
- `UnessExam.to_dict() -> dict`
- `load_exam(path: Path) -> UnessExam`
- `save_exam(exam: UnessExam, path: Path) -> None`
- `UnessProposition.reponse_finale: bool | None` remains null until a user validation exists; consumers use `verdict_ia` when it is non-null, otherwise `reponse_uness`.

- [ ] **Step 1: Write failing tests** for round-tripping faculty/level/year metadata, DP context, proposition-level official/IA/final answers, image metadata, and `support_visuel_seul`.
- [ ] **Step 2: Run `pytest tests/test_uness_models.py -v`** and confirm the model/import functions are absent.
- [ ] **Step 3: Implement typed dataclasses/Pydantic models** with enum-like string validation for `statut` (`concordant`, `desaccord`, `incertain`, `valide_manuellement`) and question types (`QRM`, `QRU`, `QRP/L`, `DP`, `KFP`, `QROC`).
- [ ] **Step 4: Implement UTF-8 JSON load/save** with stable indentation and an explicit schema version `"schema_version": 1`.
- [ ] **Step 5: Run the focused tests and commit** with `git add backend/core/uness tests/test_uness_models.py && git commit -m "feat: add UNESS canonical exam model"`.

### Task 2: Gériatrie raw artifact normalizer

**Files:**
- Create: `backend/core/uness/normalizer.py`
- Create: `backend/core/uness/artifacts.py`
- Test: `tests/test_uness_normalizer.py`
- Fixture: `tests/fixtures/uness/geriatry_review.html`

**Interfaces:**
- `RawUnessArtifact(source_url: str, html_by_content: dict[str, str], media: list[RawMedia])`
- `normalize_artifact(artifact: RawUnessArtifact, metadata: ExamMetadata) -> UnessExam`
- `extract_review_content(html: str) -> list[UnessQuestion]`

- [ ] **Step 1: Add a sanitized Gériatrie review fixture** containing one QRM, one DP context, green/red answer classes, and one image reference; remove patient-identifying or account-specific data.
- [ ] **Step 2: Write failing parser tests** asserting exact question/proposition text, official booleans from green/red classes, score text, and image linkage.
- [ ] **Step 3: Run `pytest tests/test_uness_normalizer.py -v`** and confirm extraction fails.
- [ ] **Step 4: Implement DOM parsing** with BeautifulSoup, robust selectors for question blocks and answer classes, and a fallback `official_answer: null` when the correction is not visible.
- [ ] **Step 5: Implement media copying/renaming** under a per-exam artifact directory and mark unsupported interactive widgets with `interaction.support_visuel_seul = true`.
- [ ] **Step 6: Run tests and commit** with `git add backend/core/uness tests/test_uness_normalizer.py tests/fixtures/uness && git commit -m "feat: normalize UNESS review artifacts"`.

### Task 3: AI proposition verification

**Files:**
- Create: `backend/core/uness/ai_verifier.py`
- Modify: `backend/core/ai/service.py` only if a structured JSON response helper is required by the existing routing abstraction
- Test: `tests/test_uness_ai_verifier.py`

**Interfaces:**
- `verify_question(question: UnessQuestion, context: VerificationContext, ai_service) -> UnessQuestion`
- `verify_exam(exam: UnessExam, context: VerificationContext, ai_service) -> UnessExam`
- `VerificationContext(course_text: str, item_refs: list[str], external_refs: list[str])`

- [ ] **Step 1: Write failing tests** with a fake AI service returning one verdict and explanation per proposition, including a deliberate disagreement with `reponse_uness`.
- [ ] **Step 2: Run `pytest tests/test_uness_ai_verifier.py -v`** and confirm the verifier is absent.
- [ ] **Step 3: Implement a strict structured prompt** requiring one result per proposition: `verdict_ia`, `explication_ia`, `sources_ia`, `confiance_ia`, and `commentaire_desaccord`.
- [ ] **Step 4: Implement response validation**: reject missing proposition results, clamp confidence to `0.0..1.0`, calculate status, and keep the official answer untouched.
- [ ] **Step 5: Implement source context loading** from existing Notion/course services when an item reference is available; otherwise label the result as context-limited.
- [ ] **Step 6: Run tests and commit** with `git add backend/core/uness backend/core/ai/service.py tests/test_uness_ai_verifier.py && git commit -m "feat: verify UNESS propositions with AI"`.

### Task 4: Import into existing QCM flow

**Files:**
- Create: `backend/core/uness/import_service.py`
- Modify: `backend/core/reviews/local_store.py` to persist source/proposition verification metadata alongside imported questions
- Modify: `backend/api/qcm.py` to expose `POST /api/qcm/uness/import`
- Test: `tests/test_uness_import.py`

**Interfaces:**
- `import_uness_exam(exam: UnessExam) -> int` returns the created local practice session id.
- `POST /api/qcm/uness/import` accepts `{ "path": "...json", "verify": true }` and returns `{ "session_id": int, "questions": int, "disagreements": int }`.

- [ ] **Step 1: Write failing API tests** for successful import, malformed JSON (400), missing file (404), and disagreement count.
- [ ] **Step 2: Run `pytest tests/test_uness_import.py -v`** and confirm the endpoint/service is absent.
- [ ] **Step 3: Map canonical questions** to the existing AI-practice/QCM question shape, preserving official and IA correction fields in the stored payload.
- [ ] **Step 4: Implement the endpoint** with path validation restricted to the configured local import directory and no network fetch.
- [ ] **Step 5: Extend correction payloads** so the UI can render IA explanation as primary and official correction in a secondary disclosure.
- [ ] **Step 6: Run focused API/store tests and commit** with `git add backend/core/uness backend/core/reviews/local_store.py backend/api/qcm.py tests/test_uness_import.py && git commit -m "feat: import verified UNESS exams into QCM"`.

### Task 5: URL-driven Gériatrie collection runbook and smoke test

**Files:**
- Create: `scripts/uness/README.md`
- Create: `scripts/uness/geriatry_collect_checklist.md`
- Test: `tests/test_uness_smoke_fixture.py`

**Interfaces:**
- The collection input is the exact annale URL pasted by the user, for example `https://entrainement.uness.fr/annales/course/view.php?id=29135`.
- The collector output is a local `RawUnessArtifact` directory consumed by `normalize_artifact`.

- [ ] **Step 1: Document the manual handoff**: user opens/signs in to Chrome, sends the exact URL, agent confirms the target title/faculty/level, and asks before the first final submission.
- [ ] **Step 2: Document the automated navigation** through each content, blank attempt submission, review extraction, and local artifact save; include recovery points after each content.
- [ ] **Step 3: Add a fixture smoke test** that runs normalize → verify(fake AI) → import and asserts one session with one explanation per proposition.
- [ ] **Step 4: Run the complete prototype suite** with `pytest tests/test_uness_models.py tests/test_uness_normalizer.py tests/test_uness_ai_verifier.py tests/test_uness_import.py tests/test_uness_smoke_fixture.py -v`.
- [ ] **Step 5: Commit the runbook and smoke test** with `git add scripts/uness tests/test_uness_smoke_fixture.py && git commit -m "test: add UNESS Gériatrie prototype runbook"`.

## Prototype acceptance check

The prototype is complete when one user-provided Gériatrie URL yields a local JSON file, every visible proposition has an IA explanation, any UNESS/IA disagreement is shown with an explicit warning and preserved official answer, one image is retained if present, and the resulting exam launches in Synapse’s existing QCM reader without requiring a second manual copy/paste step.
