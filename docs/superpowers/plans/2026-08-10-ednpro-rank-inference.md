# EDNpro Rank Inference Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enrichir les questions EDNpro sans rang avec les OIC de l’item, appeler Gemini une seule fois par item et par session, puis alimenter les statistiques A/B uniquement pour les inférences de confiance strictement supérieure à 85 %.

**Architecture:** Ajouter un module de domaine pur pour construire et parser les lots d’inférence, réutiliser `AITask.ITEM_CLASSIFICATION` et le modèle Gemini Flash-Lite existant, puis enrichir le payload avant `import_session` et `record_imported_evaluations`. Étendre les tables EDNpro et QCM avec la provenance/confiance et les compteurs A/B, en conservant les rangs officiels EDNpro comme source prioritaire.

**Tech Stack:** Python 3.13, NiceGUI/FastAPI, SQLite, pytest, client Gemini HTTP existant, cache OIC `lisa_oic`.

## Global Constraints

- Un rang A/B extrait du DOM EDNpro est officiel et prioritaire.
- Les OIC sont fournis une seule fois par couple session/item.
- Une inférence Gemini alimente les statistiques uniquement si le rang est A/B et la confiance est strictement supérieure à `0.85`.
- Une absence de clé Gemini, une erreur réseau ou une réponse invalide ne bloque jamais l’import des questions et scores bruts.
- Les questions existantes ne sont pas recréées ; les nouvelles tentatives restent importées.
- Ne pas afficher ni journaliser de clé Gemini ou de contenu secret.

---

### Task 1: Modèle pur d’inférence par lot

**Files:**
- Create: `backend/core/ednpro/rank_inference.py`
- Test: `tests/test_ednpro_rank_inference.py`

**Interfaces:**
- Produces `RankInference(rank: str, confidence: float | None, oic_codes: tuple[str, ...], rationale: str, source: str)`.
- Produces `group_missing_rank_questions(questions) -> dict[str, tuple[question, ...]]`.
- Produces `build_rank_inference_prompt(item_number, questions, oics) -> str`.
- Produces `parse_rank_inference_response(text, question_ids, threshold=0.85) -> dict[str, RankInference]`.

- [ ] **Step 1: Write failing tests**

Tester les contrats publics : les questions sont groupées par item, celles qui ont déjà A/B sont exclues, les OIC sont présents une seule fois dans le prompt, et seules les réponses A/B strictement au-dessus de `0.85` sont acceptées.

```python
def test_groups_only_questions_without_official_rank_by_item():
    questions = [
        fake_question("q1", "233", rank=""),
        fake_question("q2", "233", rank="B"),
        fake_question("q3", "75", rank=""),
    ]
    assert group_missing_rank_questions(questions) == {
        "233": (questions[0],),
        "75": (questions[2],),
    }

def test_parser_rejects_threshold_boundary_and_unknown_rank():
    result = parse_rank_inference_response(
        '{"questions":['
        '{"id":"q1","rank":"A","confidence":0.850}',
        '{"id":"q2","rank":"B","confidence":0.91}',
        '{"id":"q3","rank":"C","confidence":0.99}'
        ']}',
        ("q1", "q2", "q3"),
    )
    assert "q1" not in result
    assert result["q2"].rank == "B"
    assert "q3" not in result
```

- [ ] **Step 2: Run the focused tests and verify they fail**

Run: `pytest tests/test_ednpro_rank_inference.py -q`

Expected: FAIL because the new module and public functions do not exist.

- [ ] **Step 3: Implement the pure module**

Use a frozen dataclass, normalize ranks to uppercase, clamp/reject invalid confidences, parse a JSON object only, preserve question identifiers, and truncate rationale to a bounded length. Build one JSON prompt containing the item, the complete OIC list, and an array of questions.

- [ ] **Step 4: Run focused tests**

Run: `pytest tests/test_ednpro_rank_inference.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/core/ednpro/rank_inference.py tests/test_ednpro_rank_inference.py
git commit -m "feat: add batched EDNpro rank inference contracts"
```

### Task 2: Résolution groupée des OIC et persistance de provenance

**Files:**
- Modify: `backend/core/reviews/local_store.py`
- Modify: `backend/core/ednpro/qcm_capture.py`
- Test: `tests/test_ednpro_rank_inference.py`
- Test: `tests/test_ednpro_qcm_capture.py`

**Interfaces:**
- Add `local_store.get_lisa_oic_for_item(item_number: str, course_ids: Sequence[str]) -> list[dict]`, returning deduplicated active OIC rows with `code`, `intitule`, `rang`, and `rubrique`.
- Extend `EdnproQuestionObservation` with `rank_source: str = "unknown"`, `rank_confidence: float | None = None`, and `rank_evidence: tuple[str, ...] = ()`.
- Add `enrich_observations_with_ranks(observations, *, course_ids_by_item, service=None) -> tuple[EdnproQuestionObservation, ...]`.

- [ ] **Step 1: Write failing tests**

Cover duplicate OIC codes across multiple course IDs, official EDNpro precedence, Gemini provenance for an accepted inference, and unchanged observations when no OICs or no Gemini key are available.

```python
def test_oics_are_deduplicated_across_college_aliases(local_store):
    local_store.upsert_lisa_oic("course-a", [{"oic_code":"OIC-1", "intitule":"X", "rang":"A"}])
    local_store.upsert_lisa_oic("course-b", [{"oic_code":"OIC-1", "intitule":"X", "rang":"A"},
                                               {"oic_code":"OIC-2", "intitule":"Y", "rang":"B"}])
    assert [o["code"] for o in local_store.get_lisa_oic_for_item("233", ["course-a", "course-b"])] == ["OIC-1", "OIC-2"]
```

- [ ] **Step 2: Run tests and verify failure**

Run: `pytest tests/test_ednpro_rank_inference.py tests/test_ednpro_qcm_capture.py -q`

Expected: FAIL on missing resolver/fields.

- [ ] **Step 3: Add the OIC resolver and rank metadata**

Query `lisa_oic` only for requested course IDs, deduplicate by OIC code, and return deterministic ordering by rank/code. Set `rank_source="ednpro"` when DOM extraction finds A/B; leave it `unknown` otherwise. During `import_session`, update an existing canonical question only when its stored rank is empty and the incoming observation has a higher-priority rank; never overwrite an existing official rank.

- [ ] **Step 4: Add idempotent SQLite migrations**

Add to `ednpro_qcm_questions` and `ednpro_qcm_attempts`: `rank_source`, `rank_confidence`, and `rank_evidence_json`. Existing rows default to `unknown`, `NULL`, and `[]`. Store the metadata on both the canonical question and each attempt.

- [ ] **Step 5: Run focused tests**

Run: `pytest tests/test_ednpro_rank_inference.py tests/test_ednpro_qcm_capture.py -q`

Expected: PASS, including all existing capture/idempotency tests.

- [ ] **Step 6: Commit**

```bash
git add backend/core/reviews/local_store.py backend/core/ednpro/qcm_capture.py tests/test_ednpro_rank_inference.py tests/test_ednpro_qcm_capture.py
git commit -m "feat: persist EDNpro rank provenance and OIC context"
```

### Task 3: Appel Gemini groupé et enrichissement avant import

**Files:**
- Modify: `backend/core/ai/tasks.py`
- Modify: `main.py`
- Modify: `backend/core/ednpro/qcm_capture.py`
- Test: `tests/test_ai_tasks.py`
- Test: `tests/test_ednpro_qcm_capture.py`
- Test: `tests/test_runtime_config.py`

**Interfaces:**
- Add `infer_ednpro_ranks(prompt: str, *, service=None) -> AIResponse`, routed through `AITask.ITEM_CLASSIFICATION` with JSON output.
- Add `enrich_session_ranks(session: Mapping[str, Any], *, courses: Sequence[Any], service=None) -> dict[str, Any]`.
- The API route calls enrichment with `await asyncio.to_thread(enrich_session_ranks, payload, courses=data_store.cours)` before `import_session`.

- [ ] **Step 1: Write failing tests**

Mock the existing `AIService` and assert one Gemini call for two missing questions of one item, no call for an official rank, the full OIC list is present once, and a failed AI call returns the original session.

```python
def test_enrich_session_calls_gemini_once_per_item(service, monkeypatch):
    service.generate.return_value = AIResponse(
        '{"questions":[{"id":"q1","rank":"A","confidence":0.9,"oic_codes":["OIC-1"]}]}',
        AIModel.FLASH_LITE,
    )
    enriched = enrich_session_ranks(session_with_two_questions_same_item(), courses=[course_with_oics() ], service=service)
    assert service.generate.call_count == 1
    assert enriched["questions"][0]["question"]["rank"] == "A"
```

- [ ] **Step 2: Run tests and verify failure**

Run: `pytest tests/test_ai_tasks.py tests/test_ednpro_qcm_capture.py -q`

Expected: FAIL because the task wrapper and session enrichment do not exist.

- [ ] **Step 3: Implement the Gemini wrapper and enrichment**

Reuse `AITask.ITEM_CLASSIFICATION` so the existing Flash-Lite model and `GEMINI_API_KEY` configuration apply. Resolve all course IDs for each item, load OICs once per item, group only missing-rank questions, parse the batch response, and apply accepted results with `dataclasses.replace`. If `GeminiClientError`, JSON parsing, missing OICs, or missing API key occurs, log a redacted warning and return the original session.

- [ ] **Step 4: Wire the API before persistence**

In `main.py`, enrich the decoded payload before calling `import_session`; run the synchronous Gemini call in `asyncio.to_thread` so the NiceGUI/FastAPI event loop is not blocked. Keep the existing import response shape and add enrichment counters such as `inferred_ranks` and `unclassified_ranks`.

- [ ] **Step 5: Run focused tests**

Run: `pytest tests/test_ai_tasks.py tests/test_ednpro_qcm_capture.py tests/test_runtime_config.py -q`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/core/ai/tasks.py main.py backend/core/ednpro/qcm_capture.py tests/test_ai_tasks.py tests/test_ednpro_qcm_capture.py tests/test_runtime_config.py
git commit -m "feat: enrich EDNpro ranks in batched Gemini pass"
```

### Task 4: Propager les compteurs A/B dans les statistiques QCM

**Files:**
- Modify: `backend/core/evaluation/models.py`
- Modify: `backend/core/evaluation/service.py`
- Modify: `backend/core/reviews/local_store.py`
- Modify: `backend/core/ednpro/qcm_capture.py`
- Test: `tests/test_ednpro_qcm_capture.py`
- Test: `tests/test_qcm_service.py`

**Interfaces:**
- Extend `EvaluationInput` with optional `rank_a_questions`, `rank_a_correct`, `rank_b_questions`, `rank_b_correct`, and `rank_unknown_questions`.
- Persist those values as nullable/defaulted columns in `qcm_sessions` through the existing `add_qcm_session_full`/`record_evaluation` path.
- Extend item stats with `rank_unknown` while preserving existing `rank_a` and `rank_b` shapes.

- [ ] **Step 1: Write failing tests**

Assert that a session with one official/inferred A, one B, and one unknown stores the three buckets and that an inferred rank above the threshold is counted identically to an official rank in A/B statistics.

- [ ] **Step 2: Run tests and verify failure**

Run: `pytest tests/test_ednpro_qcm_capture.py tests/test_qcm_service.py -q`

Expected: FAIL because `qcm_sessions` has no rank bucket columns and `EvaluationInput` has no fields.

- [ ] **Step 3: Add idempotent qcm_sessions migration**

Add nullable/defaulted columns for A/B/unknown question and correct counts. Update `add_qcm_session_full` with optional parameters so all existing QCM callers remain compatible.

- [ ] **Step 4: Pass session item rank statistics**

Update `record_imported_evaluations` to populate the new fields from `result.session_item_stats`. Do not count unknown ranks in A/B denominators. Keep score and total question behavior unchanged.

- [ ] **Step 5: Run focused tests**

Run: `pytest tests/test_ednpro_qcm_capture.py tests/test_qcm_service.py -q`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/core/evaluation/models.py backend/core/evaluation/service.py backend/core/reviews/local_store.py backend/core/ednpro/qcm_capture.py tests/test_ednpro_qcm_capture.py tests/test_qcm_service.py
git commit -m "feat: include EDNpro rank buckets in QCM stats"
```

### Task 5: Vérification intégrée et documentation d’exploitation

**Files:**
- Modify: `docs/EDNPRO_IMPORT.md`
- Modify: `docs/AI_MODEL_ROUTING.md`
- Test: `tests/test_ednpro_pipeline.py`
- Test: `tests/test_ednpro_qcm_capture_ui.py`

- [ ] **Step 1: Add an end-to-end mocked import test**

Simulate a session with two items, three questions missing rank, one official rank, grouped mocked Gemini responses, then assert persisted questions, attempts, provenance, and QCM rank buckets.

- [ ] **Step 2: Document configuration and failure behavior**

Document that `GEMINI_API_KEY` is optional for capture, `GEMINI_LITE_MODEL` is reused, AI inference is best-effort, and the UI/API still imports raw questions when Gemini is unavailable.

- [ ] **Step 3: Run the complete verification suite**

Run:

```bash
python -m py_compile main.py backend/core/ednpro/rank_inference.py backend/core/ednpro/qcm_capture.py
pytest -q
```

Expected: all tests pass.

- [ ] **Step 4: Commit documentation and integration tests**

```bash
git add docs/EDNPRO_IMPORT.md docs/AI_MODEL_ROUTING.md tests/test_ednpro_pipeline.py tests/test_ednpro_qcm_capture_ui.py
git commit -m "test: verify EDNpro rank enrichment pipeline"
```

- [ ] **Step 5: Prepare deployment instructions**

After pushing, update Ubuntu with `git pull --ff-only origin main`, rebuild the `synapse` image, recreate the container, and verify `/api/healthz`. Then run one small capture session and inspect `ednpro_qcm_questions.rank_source`, `ednpro_qcm_attempts.rank`, and the new `qcm_sessions` rank bucket columns.
