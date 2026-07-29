# Economic AI Model Routing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task with review checkpoints.

**Goal:** Add a tested AI façade that routes OIC/QCM/ECOS/DP/KFP and grid-extraction tasks to Gemini Flash-Lite or Flash, while keeping scoring deterministic in Synapse.

**Architecture:** Introduce a pure task-to-model policy and a transport-neutral `AIService`. Implement a small Gemini REST client using the existing `requests` dependency, then adapt the existing OIC evaluator through the façade without removing its AnythingLLM/RAG fallback. Expose task-specific entry points for future DP/KFP/ECOS callers without inventing new UI flows.

**Tech Stack:** Python 3.11+, Pydantic Settings, requests, pytest, existing NiceGUI/AnythingLLM integration.

## Global Constraints

- Never log API keys, prompts, medical content, or full provider responses.
- No real network calls in automated tests.
- Scores, levels, thresholds, and progression remain computed by Synapse code.
- Flash-Lite is the default for OIC/QCM/simple ECOS; Flash is required for DP/KFP, complex ECOS, and complex grid extraction.
- Existing OIC JSON parsing and AnythingLLM workspace behavior must remain compatible.

### Task 1: Add routing policy and response contracts

**Files:**
- Create: `backend/core/ai/__init__.py`
- Create: `backend/core/ai/routing.py`
- Test: `tests/test_ai_routing.py`

**Interfaces:**
- Produces `AITask`, `AIModel`, `AIResponse`, `AIServiceError`, and `model_for_task(task)`.

- [ ] Write failing tests for every task mapping, unknown task rejection, and response metadata.
- [ ] Run `pytest tests/test_ai_routing.py -q`; expect failure because the module does not exist.
- [ ] Implement the enum, immutable response dataclass, and pure policy.
- [ ] Run the focused tests and confirm they pass.
- [ ] Run `ruff check backend/core/ai tests/test_ai_routing.py`.

### Task 2: Add Gemini REST transport and settings

**Files:**
- Modify: `backend/config/settings.py`
- Modify: `.env.example`
- Create: `backend/core/ai/gemini_client.py`
- Test: `tests/test_gemini_client.py`

**Interfaces:**
- `GeminiClient.generate(prompt, model, response_format="text") -> AIResponse`.
- Settings fields: `gemini_api_key`, `gemini_lite_model`, `gemini_flash_model`, `gemini_timeout_seconds`.

- [ ] Write failing tests for request URL, model selection, JSON response parsing, usage metadata, timeout wrapping, and absent-key handling.
- [ ] Run the focused tests and verify the expected missing-module/API failures.
- [ ] Implement the minimal REST client against `generativelanguage.googleapis.com/v1beta/models/{model}:generateContent` using `requests.post`.
- [ ] Restrict response MIME type to JSON when `response_format="json"` and return a clear provider error when the response has no text.
- [ ] Run focused tests and confirm they pass without network access.
- [ ] Run settings/config validation tests.

### Task 3: Add the AI façade with task routing

**Files:**
- Create: `backend/core/ai/service.py`
- Test: `tests/test_ai_service.py`

**Interfaces:**
- `AIService(client).generate(task, prompt, *, context=None, response_format="text") -> AIResponse`.
- The service selects the model using `model_for_task` and passes the selected model to the client.

- [ ] Write failing tests proving Lite is selected for OIC, QCM, and simple ECOS, while Flash is selected for DP, KFP, complex ECOS, and grid extraction.
- [ ] Write a failing test proving context is appended in a bounded, explicit format and scores are not routed through the service.
- [ ] Run the focused tests and verify the expected failures.
- [ ] Implement the façade with dependency injection and no provider-specific branching outside the client.
- [ ] Run focused tests and confirm they pass.

### Task 4: Integrate OIC without losing AnythingLLM RAG fallback

**Files:**
- Modify: `backend/core/lisa/anythingllm_client.py`
- Modify: `backend/core/lisa/evaluator.py`
- Test: `tests/test_oic_evaluator.py`
- Test: `tests/test_anythingllm_client.py`

**Interfaces:**
- Preserve existing `generate_questions` and `evaluate_open_answer` signatures.
- Add an injectable AI service seam so tests can verify task selection while the default path preserves workspace RAG.

- [ ] Add failing characterization tests for OIC generation and open-answer evaluation using a fake routed service.
- [ ] Add a failing test for a provider timeout returning a typed, user-safe error.
- [ ] Implement the smallest adapter that keeps AnythingLLM as the default OIC transport when a workspace slug is available and uses the routed Gemini service for direct calls.
- [ ] Ensure QCM grading remains local and does not call any provider.
- [ ] Run all OIC/evaluation tests and confirm they pass.

### Task 5: Add reusable DP/KFP/ECOS task entry points

**Files:**
- Create: `backend/core/ai/tasks.py`
- Test: `tests/test_ai_tasks.py`

**Interfaces:**
- `generate_qcm(prompt, service=...)` uses `AITask.QCM`.
- `generate_ecos(prompt, complex_case=False, service=...)` uses simple or complex ECOS routing.
- `generate_dp(prompt, service=...)` and `generate_kfp(prompt, service=...)` use Flash.
- `extract_grid(prompt, service=...)` uses Flash and returns unapproved content marked for human validation.

- [ ] Write failing tests for each helper’s task, JSON response format, and validation marker.
- [ ] Run focused tests and verify failures.
- [ ] Implement thin helpers only; do not add UI or persistence in this task.
- [ ] Run focused tests and confirm they pass.

### Task 6: Integrate configuration, documentation, and verification

**Files:**
- Modify: `docs/README.md` or the existing AI configuration documentation file selected after inspection.
- Modify: `tests/test_settings.py` if present, otherwise create it.
- Modify: `.env.example` only if Task 2 did not cover all fields.

- [ ] Add a configuration example that defaults to Flash-Lite and documents the Flash escalation policy.
- [ ] Run the full relevant test suite: `pytest tests/test_ai_routing.py tests/test_gemini_client.py tests/test_ai_service.py tests/test_ai_tasks.py tests/test_oic_evaluator.py tests/test_anythingllm_client.py -q`.
- [ ] Run `ruff check backend tests` and `git diff --check`.
- [ ] Confirm no debug prefixes or secrets are present.
- [ ] Run a mocked end-to-end OIC route and a real local smoke test only if the user’s API configuration is intentionally available.

