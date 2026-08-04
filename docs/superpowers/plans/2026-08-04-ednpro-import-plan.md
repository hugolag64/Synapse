# EDNpro Import Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Collecter les annales EDNpro depuis 2023 avec une session Google locale, les importer comme EDN complets et conserver une provenance de correction tierce fiable.

**Architecture:** Ajouter un adaptateur EDNpro qui produit le modèle d’examen canonique déjà consommé par le lecteur QCM. Le collecteur sauvegarde des artefacts et un manifest reprenable ; l’import reste idempotent. La classification question→item est exécutée après normalisation, avec les liaisons confiantes dans `ai_practice_question_items` et les autres en vérification.

**Tech Stack:** Python, Playwright async, SQLite via `backend.core.reviews.local_store`, modèles UNESS existants, NiceGUI, pytest.

## Global Constraints

- EDNpro est une source tierce très fiable, mais ses corrections ne sont pas des corrections officielles.
- L’utilisateur effectue lui-même la connexion Google dans une fenêtre Playwright visible.
- Aucun mot de passe, cookie ou secret ne doit apparaître dans les logs, manifests ou URL persistées.
- Les vidéos sont indexées par page et métadonnées ; leurs fichiers ne sont pas téléchargés.
- Une question non classée reste jouable mais ne produit pas automatiquement de preuve de maîtrise.
- La collecte doit être idempotente, relançable et limitée aux contenus accessibles au compte de l’utilisateur.

---

### Task 1: Ajouter la provenance multi-source aux regroupements d’annales

**Files:**
- Modify: `backend/core/reviews/local_store.py` autour de `_migrate_uness_annales`, `create_uness_annale` et `list_uness_annales`
- Modify: `backend/core/uness/import_service.py` autour de `ANNALE_TYPE_LABELS` et `import_uness_exam`
- Test: `tests/test_exam_provenance.py`

**Interfaces:**
- Produces `source` (`UNESS` par défaut, `EDNpro` pour le nouvel adaptateur), `source_exam_id` et `metadata_json` sur le regroupement d’annale.
- Preserves the existing `type_annale="edn_complet"` and all existing UNESS callers.

- [ ] **Step 1: Write the failing migration and API tests**

```python
def test_annale_provenance_defaults_to_uness_and_accepts_ednpro():
    annale_id = local_store.create_uness_annale(
        source_url="https://ednpro.app/annales/2023-p1",
        collected_at="2026-08-04T08:00:00+00:00",
        faculte="",
        niveau="EDN",
        annee=2023,
        matiere="Cardiologie",
        titre="EDN 2023 — P1",
        type_annale="edn_complet",
        source="EDNpro",
        source_exam_id="2023-p1",
    )
    row = local_store.get_uness_annale(annale_id)
    assert row["source"] == "EDNpro"
    assert row["source_exam_id"] == "2023-p1"
```

- [ ] **Step 2: Run the focused test to verify it fails**

Run: `pytest tests/test_exam_provenance.py -q`

Expected: FAIL because the migration and `create_uness_annale` do not yet accept the new source fields.

- [ ] **Step 3: Implement the additive SQLite migration**

Add nullable-compatible columns with defaults, keep the table name for backward compatibility, and extend the insert/list functions with keyword-only defaults. Update annale labels so the UI can display `EDNpro · EDN complet` without changing existing UNESS rows.

- [ ] **Step 4: Run the focused test and the existing annale tests**

Run: `pytest tests/test_exam_provenance.py tests/test_annales_page.py tests/test_annale_detail_page.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/core/reviews/local_store.py backend/core/uness/import_service.py tests/test_exam_provenance.py
git commit -m "feat: add multi-source exam provenance"
```

### Task 2: Implement the visible Google session for EDNpro

**Files:**
- Create: `backend/core/ednpro/__init__.py`
- Create: `backend/core/ednpro/session.py`
- Test: `tests/test_ednpro_session.py`

**Interfaces:**
- Produces `EdnproSessionStatus(status: str, url: str, profile_dir: str)` and `async def open_ednpro_session(profile_dir: Path) -> EdnproSessionStatus`.
- Consumes a dedicated local profile path from configuration; it never receives username/password arguments.

- [ ] **Step 1: Write tests for URL classification and secret-free configuration**

```python
def test_authenticated_url_is_ednpro():
    assert is_authenticated_url("https://ednpro.app/training-v2") is True
    assert is_authenticated_url("https://ednpro.app/auth") is False

def test_session_config_has_no_credentials_fields():
    assert "password" not in SessionConfig.__annotations__
    assert "cookie" not in SessionConfig.__annotations__
```

- [ ] **Step 2: Run the focused tests to verify they fail**

Run: `pytest tests/test_ednpro_session.py -q`

Expected: FAIL because the session module does not exist.

- [ ] **Step 3: Implement the persistent visible context**

Use `async_playwright()` and `chromium.launch_persistent_context(str(profile_dir), headless=False)`. Navigate to `https://ednpro.app/auth`, wait for the user to complete Google authentication, then detect an authenticated EDNpro route. Do not inspect or export cookies; only return the status and current URL. Reuse the profile directory on later runs and return `connexion_requise` when the page remains on `/auth`.

- [ ] **Step 4: Run tests and a manual smoke check**

Run: `pytest tests/test_ednpro_session.py -q`.

Manual check: launch the session command, click `Continuer avec Google`, complete login manually, and verify that Synapse reports `connecté` without printing credentials.

- [ ] **Step 5: Commit**

```bash
git add backend/core/ednpro tests/test_ednpro_session.py
git commit -m "feat: add visible EDNpro Google session"
```

### Task 3: Collect EDNpro exams and video page metadata

**Files:**
- Create: `scripts/ednpro/collector.py`
- Create: `backend/core/ednpro/artifacts.py`
- Test: `tests/test_ednpro_collector.py`
- Test fixture: `tests/fixtures/ednpro/annales.html`
- Test fixture: `tests/fixtures/ednpro/videos.html`

**Interfaces:**
- Produces `collect_ednpro(start_year: int, end_year: int | None, profile_dir: Path, output_dir: Path) -> Path`.
- Produces manifest records with `external_exam_id`, `external_session_id`, `external_question_id`, `source_url`, `video_page_url`, `title`, `category`, and `item_numbers`.

- [ ] **Step 1: Write parser tests against local HTML fixtures**

```python
def test_video_index_keeps_page_url_and_metadata_without_media_download():
    rows = parse_video_index(FIXTURES / "videos.html", "https://ednpro.app/videos")
    assert rows[0]["title"] == "ECG"
    assert rows[0]["category"] == "videos"
    assert rows[0]["page_url"].startswith("https://ednpro.app/")
    assert "media_url" not in rows[0]

def test_video_title_with_item_number_is_linkable():
    row = parse_video_card({"title": "Item 123 — Sujet âgé", "href": "/videos/123"})
    assert row["item_numbers"] == ["123"]
```

- [ ] **Step 2: Run the focused tests to verify they fail**

Run: `pytest tests/test_ednpro_collector.py -q`

Expected: FAIL because the EDNpro parsers do not exist.

- [ ] **Step 3: Implement safe extraction**

Use the authenticated Playwright page to navigate the annual annales and video categories. Capture visible links, titles, categories, item numbers explicitly present in titles or page metadata, and the canonical page URL. Never persist a signed CDN URL, token query parameter, `<video>` blob, or downloaded video file. If a video opens in a modal, capture the stable `Ouvrir la fiche`/page URL from the modal and close it before continuing.

- [ ] **Step 4: Implement the resumable manifest**

Write one manifest per run, record completed/failed sessions, sleep between navigations, and skip records whose logical key or content fingerprint already exists. A failed page must be recorded as `échec relançable` and must not abort the rest of the collection.

- [ ] **Step 5: Run fixture tests and a one-category live pilot**

Run: `pytest tests/test_ednpro_collector.py -q`.

Manual pilot: collect only the EDNpro `Vidéos` index and one annale page. Confirm that the manifest contains page links and titles but no credentials, cookies, signed media URLs, or video files.

- [ ] **Step 6: Commit**

```bash
git add scripts/ednpro backend/core/ednpro/artifacts.py tests/test_ednpro_collector.py tests/fixtures/ednpro
git commit -m "feat: collect EDNpro exams and video metadata"
```

### Task 4: Normalize EDNpro corrections into the existing exam importer

**Files:**
- Create: `backend/core/ednpro/normalizer.py`
- Modify: `backend/core/uness/models.py` to accept source-neutral provenance/correction metadata while preserving compatibility
- Modify: `backend/core/uness/import_service.py`
- Test: `tests/test_ednpro_normalizer.py`

**Interfaces:**
- Produces `UnessExam`-compatible payloads with `provenance["source"] == "EDNpro"` and `metadata["correction_source"] == "ednpro"`.
- Consumes the collector manifest and raw HTML/JSON artifacts.

- [ ] **Step 1: Write tests for correction provenance and partial correction**

```python
def test_normalizer_marks_ednpro_correction_as_non_official():
    exam = normalize_ednpro_exam(FIXTURE_PATH)
    assert exam.provenance["source"] == "EDNpro"
    assert exam.metadata["correction_source"] == "ednpro"
    assert exam.metadata["correction_official"] is False

def test_missing_ai_verification_does_not_remove_ednpro_correction():
    exam = normalize_ednpro_exam(FIXTURE_PATH)
    imported = import_source_exam(exam, source="EDNpro", type_annale="edn_complet")
    assert imported > 0
```

- [ ] **Step 2: Run the focused tests to verify they fail**

Run: `pytest tests/test_ednpro_normalizer.py -q`

Expected: FAIL because source-neutral normalization is not implemented.

- [ ] **Step 3: Normalize official-looking page structure without relabeling it**

Map EDNpro’s question/proposition/correction fields into the existing canonical model. Keep the EDNpro answer and explanation as source data; set the IA fields only when the verifier actually ran. The import facade must accept `source="EDNpro"`, create `type_annale="edn_complet"`, and delegate to the existing replayable QCM persistence.

- [ ] **Step 4: Run focused import and existing QCM tests**

Run: `pytest tests/test_ednpro_normalizer.py tests/test_ai_practice.py tests/test_practice_importer.py -q`.

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/core/ednpro/normalizer.py backend/core/uness/models.py backend/core/uness/import_service.py tests/test_ednpro_normalizer.py
git commit -m "feat: normalize EDNpro corrections"
```

### Task 5: Add question-level item classification and verification queue

**Files:**
- Create: `backend/core/uness/question_item_classifier.py`
- Modify: `backend/core/reviews/local_store.py` around `ai_practice_question_items` and session import helpers
- Modify: `backend/core/practice/item_evidence.py`
- Test: `tests/test_question_item_classifier.py`
- Test: `tests/test_practice_question_items.py`

**Interfaces:**
- Produces `classify_question_items(title: str, stem: str, subject: str, candidates: list[dict]) -> ItemClassification`.
- Produces durable rows `(question_id, item_number, confidence, source, classifier_version)`.

- [ ] **Step 1: Write tests for explicit, confident, and uncertain classification**

```python
def test_explicit_source_item_wins_over_ai():
    result = classify_question_items("Item 221 — Athérome", "...", "Cardiologie", [])
    assert result.item_numbers == ("221",)
    assert result.source == "source"

def test_uncertain_ai_result_creates_no_mastery_link():
    result = classification_from_ai([], confident=False)
    assert result.item_numbers == ()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_question_item_classifier.py tests/test_practice_question_items.py -q`

Expected: FAIL because the question-level classifier is not yet wired into EDNpro import.

- [ ] **Step 3: Implement the ordered classification pipeline**

Check explicit item metadata first, then validated mappings, then the existing candidate-limited AI classifier. Reject more than two items without manual validation. Persist confidence, method, and classifier version. Keep unresolved questions playable and mark them `à vérifier`.

- [ ] **Step 4: Ensure evidence queries require a question-level link**

Update evidence aggregation so a broad session-level item suggestion cannot count as question evidence. Add a diagnostic count for imported questions with no item link.

- [ ] **Step 5: Run focused and regression tests**

Run: `pytest tests/test_question_item_classifier.py tests/test_practice_question_items.py tests/test_ai_practice.py tests/test_knowledge_mastery.py -q`.

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/core/uness/question_item_classifier.py backend/core/reviews/local_store.py backend/core/practice/item_evidence.py tests/test_question_item_classifier.py tests/test_practice_question_items.py
git commit -m "feat: classify imported questions by item"
```
