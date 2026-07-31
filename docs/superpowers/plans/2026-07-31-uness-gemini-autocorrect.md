# UNESS Gemini Auto-Correct Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the manual ChatGPT/Gemini copy-paste correction step for UNESS annales with a direct Gemini API call (`gemini-3-flash-preview`), triggered by a new button in the "Importer une annale UNESS" dialog that takes a folder path.

**Architecture:** A new orchestrator module (`backend/core/uness/gemini_autocorrect.py`) finds every bridge JSON directly inside a given folder, calls Gemini once per quiz via the existing `AIService`/`AITask` routing layer, and writes each raw response into `UNESS/vérifiés/` — exactly the file a human would produce by pasting into ChatGPT/Gemini web. The existing, untouched `import_verified_directory()` pipeline then converts, validates, and imports it. The collector is extended to duplicate collected images into the same folder as the bridge JSON so both the manual and the API flow can find them by filename.

**Tech Stack:** Python 3.11+, pytest, NiceGUI, existing `backend/core/ai/*` routing layer (`GeminiClient`, `AIService`, `AITask`).

## Global Constraints

- No new dependency: reuse `backend/core/ai/gemini_client.py::GeminiClient` via the existing `AIService`/`tasks.py` wrapper pattern.
- Model: `AIModel.FLASH` (→ `settings.gemini_flash_model`, currently `gemini-3-flash-preview`). No new setting, no model override.
- `gemini_conversion.py` and `import_service.py`'s conversion/validation contract must not change — the new code only produces raw AI-response JSON files, identical in shape to a manual paste.
- One click must process every bridge JSON found directly in the given folder (a partiel can have several sub-parties: mDP1, mDP2, KFP...).
- Images collected by the collector must end up duplicated in the same folder as the bridge JSON, in addition to the existing `UNESS/images/<stamp>/` staging copy (which stays untouched — it's what `import_service._cleanup_staged_images` cleans up post-import).
- Every batch/network step tolerates partial failure: one bad quiz/file must never abort the rest of the folder, matching `import_verified_directory`'s existing error-tolerant loop.

---

### Task 1: Add a `UNESS_CORRECTION` AI task and route it to Flash

**Files:**
- Modify: `backend/core/ai/routing.py:8-16`
- Test: `tests/test_ai_routing.py`

**Interfaces:**
- Produces: `AITask.UNESS_CORRECTION` (new enum member), routed by the existing `model_for_task` fallthrough to `AIModel.FLASH`.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_ai_routing.py`'s existing `@pytest.mark.parametrize` list (do not remove existing rows):

```python
@pytest.mark.parametrize(
    ("task", "expected"),
    [
        (AITask.OIC, AIModel.FLASH_LITE),
        (AITask.QCM, AIModel.FLASH_LITE),
        (AITask.ECOS_SIMPLE, AIModel.FLASH_LITE),
        (AITask.DP, AIModel.FLASH),
        (AITask.KFP, AIModel.FLASH),
        (AITask.ECOS_COMPLEX, AIModel.FLASH),
        (AITask.EXTRACTION_GRILLE, AIModel.FLASH),
        (AITask.UNESS_CORRECTION, AIModel.FLASH),
    ],
)
def test_model_for_task_uses_the_expected_quality_tier(task, expected):
    assert model_for_task(task) is expected
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_ai_routing.py -v`
Expected: FAIL with `AttributeError: UNESS_CORRECTION` (the enum member doesn't exist yet).

- [ ] **Step 3: Add the enum member**

In `backend/core/ai/routing.py`, change:

```python
class AITask(StrEnum):
    OIC = "oic"
    QCM = "qcm"
    ECOS_SIMPLE = "ecos_simple"
    DP = "dp"
    KFP = "kfp"
    ECOS_COMPLEX = "ecos_complex"
    EXTRACTION_GRILLE = "extraction_grille"
    SCORE = "score"
```

to:

```python
class AITask(StrEnum):
    OIC = "oic"
    QCM = "qcm"
    ECOS_SIMPLE = "ecos_simple"
    DP = "dp"
    KFP = "kfp"
    ECOS_COMPLEX = "ecos_complex"
    EXTRACTION_GRILLE = "extraction_grille"
    UNESS_CORRECTION = "uness_correction"
    SCORE = "score"
```

No change needed in `model_for_task`: `UNESS_CORRECTION` is not in the `FLASH_LITE` tuple, so it already falls through to `return AIModel.FLASH`.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_ai_routing.py -v`
Expected: PASS (all rows, including the new one).

- [ ] **Step 5: Commit**

```bash
git add backend/core/ai/routing.py tests/test_ai_routing.py
git commit -m "feat: add UNESS_CORRECTION AI task routed to Flash"
```

---

### Task 2: Add a `generate_uness_correction` task wrapper with image support

**Files:**
- Modify: `backend/core/ai/tasks.py:1-16`
- Test: `tests/test_ai_tasks.py`

**Interfaces:**
- Consumes: `AITask.UNESS_CORRECTION` (Task 1), `AIService.generate(task, prompt, *, context=None, response_format="text", images=())` (existing, `backend/core/ai/service.py:28-52`).
- Produces: `generate_uness_correction(prompt: str, *, images: Sequence[AIImageContent] = (), service: AIService | None = None) -> AIResponse`, used by Task 4.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_ai_tasks.py`:

```python
from backend.core.ai.routing import AIImageContent, AIModel, AIResponse, AITask
from backend.core.ai.tasks import (
    extract_grid,
    generate_dp,
    generate_ecos,
    generate_kfp,
    generate_qcm,
    generate_uness_correction,
)


def test_generate_uness_correction_uses_flash_json_route_and_forwards_images():
    service = _service()
    images = (AIImageContent(mime_type="image/png", data=b"fixture"),)

    generate_uness_correction("corrige ce quiz", images=images, service=service)

    service.generate.assert_called_once_with(
        AITask.UNESS_CORRECTION,
        "corrige ce quiz",
        response_format="json",
        images=images,
    )


def test_generate_uness_correction_defaults_to_no_images():
    service = _service()

    generate_uness_correction("corrige ce quiz", service=service)

    service.generate.assert_called_once_with(
        AITask.UNESS_CORRECTION,
        "corrige ce quiz",
        response_format="json",
        images=(),
    )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_ai_tasks.py -v`
Expected: FAIL with `ImportError: cannot import name 'generate_uness_correction'`.

- [ ] **Step 3: Implement the wrapper**

In `backend/core/ai/tasks.py`, change the import line:

```python
from backend.core.ai.gemini_client import GeminiClient
from backend.core.ai.routing import AIResponse, AITask
from backend.core.ai.service import AIService
```

to:

```python
from collections.abc import Sequence

from backend.core.ai.gemini_client import GeminiClient
from backend.core.ai.routing import AIImageContent, AIResponse, AITask
from backend.core.ai.service import AIService
```

Then add, after `generate_kfp`:

```python
def generate_uness_correction(
    prompt: str,
    *,
    images: Sequence[AIImageContent] = (),
    service: AIService | None = None,
) -> AIResponse:
    return (service or _default_service()).generate(
        AITask.UNESS_CORRECTION, prompt, response_format="json", images=images
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_ai_tasks.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/core/ai/tasks.py tests/test_ai_tasks.py
git commit -m "feat: add generate_uness_correction task wrapper"
```

---

### Task 3: Duplicate collected images into the review folder

**Files:**
- Modify: `scripts/uness/collector.py:332-340`
- Test: `tests/test_uness_collector.py`

**Interfaces:**
- Produces: `_stage_review_images(images_dir: Path, staging_dir: Path, review_dir: Path) -> list[str]` — pure, synchronous, no Playwright dependency, so it's unit-testable in isolation. Returns the list of copied filenames (empty if `images_dir` has nothing).

- [ ] **Step 1: Write the failing test**

Add to `tests/test_uness_collector.py`:

```python
from scripts.uness.collector import _stage_review_images


def test_stage_review_images_copies_into_both_staging_and_review_dirs(tmp_path):
    images_dir = tmp_path / "artifact" / "images"
    images_dir.mkdir(parents=True)
    (images_dir / "dermato1.jpg").write_bytes(b"fake-image-bytes")
    staging_dir = tmp_path / "UNESS" / "images" / "20260731T140000Z"
    review_dir = tmp_path / "UNESS" / "a_verifier" / "session-20260731T140000Z"
    review_dir.mkdir(parents=True)

    copied = _stage_review_images(images_dir, staging_dir, review_dir)

    assert copied == ["dermato1.jpg"]
    assert (staging_dir / "dermato1.jpg").read_bytes() == b"fake-image-bytes"
    assert (review_dir / "dermato1.jpg").read_bytes() == b"fake-image-bytes"


def test_stage_review_images_returns_empty_list_when_no_images(tmp_path):
    images_dir = tmp_path / "artifact" / "images"
    images_dir.mkdir(parents=True)
    staging_dir = tmp_path / "UNESS" / "images" / "stamp"
    review_dir = tmp_path / "UNESS" / "a_verifier" / "session-stamp"
    review_dir.mkdir(parents=True)

    assert _stage_review_images(images_dir, staging_dir, review_dir) == []
    assert not staging_dir.exists()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_uness_collector.py -v`
Expected: FAIL with `ImportError: cannot import name '_stage_review_images'`.

- [ ] **Step 3: Extract the helper and call it from `collect_annale`**

In `scripts/uness/collector.py`, add this function near the top-level helpers (after `_slug`, around line 46):

```python
def _stage_review_images(images_dir: Path, staging_dir: Path, review_dir: Path) -> list[str]:
    """Copy collected images into both the staging folder (cleaned up by
    import_service after import) and the review folder, alongside the bridge
    JSON — so both the manual ChatGPT/Gemini paste flow and the Gemini
    auto-correct button can find every image in one place without forgetting any."""
    if not images_dir.is_dir() or not any(images_dir.iterdir()):
        return []
    staging_dir.mkdir(parents=True, exist_ok=True)
    copied = []
    for image_file in sorted(images_dir.iterdir()):
        shutil.copy2(image_file, staging_dir / image_file.name)
        shutil.copy2(image_file, review_dir / image_file.name)
        copied.append(image_file.name)
    return copied
```

Then replace lines 333-339 (the current inline staging block):

```python
    if images_dir.is_dir() and any(images_dir.iterdir()):
        staging_dir = Path("UNESS") / "images" / subfolder_name / stamp
        staging_dir.mkdir(parents=True, exist_ok=True)
        for image_file in images_dir.iterdir():
            shutil.copy2(image_file, staging_dir / image_file.name)
        names = ", ".join(path.name for path in upload_paths)
        print(f"Images trouvées : joins le dossier {staging_dir} à Gemini avec le(s) fichier(s) concerné(s) ({names}).")
```

with:

```python
    staging_dir = Path("UNESS") / "images" / subfolder_name / stamp
    copied_images = _stage_review_images(images_dir, staging_dir, review_dir)
    if copied_images:
        names = ", ".join(path.name for path in upload_paths)
        print(
            f"Images trouvées : dossier {review_dir} prêt à corriger "
            f"(JSON + {len(copied_images)} image(s)) ({names})."
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_uness_collector.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/uness/collector.py tests/test_uness_collector.py
git commit -m "feat: duplicate UNESS collector images into the review folder"
```

---

### Task 4: Gemini auto-correct orchestrator

**Files:**
- Create: `backend/core/uness/gemini_autocorrect.py`
- Test: `tests/test_gemini_autocorrect.py`

**Interfaces:**
- Consumes: `generate_uness_correction(prompt, *, images=(), service=None) -> AIResponse` (Task 2), `backend.core.ai.routing.AIImageContent`, `backend.core.uness.import_service` module (for `VERIFIED_DIR`, referenced dynamically so tests can monkeypatch it).
- Produces: `correct_directory(folder: Path, *, service: AIService | None = None) -> dict` returning `{"corrected": list[str], "errors": list[dict[str, str]], "input_tokens": int, "output_tokens": int}`, used by Task 5.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_gemini_autocorrect.py`:

```python
"""Tests for the Gemini API auto-correct orchestrator (backend/core/uness/gemini_autocorrect.py)."""

from __future__ import annotations

import json
from unittest.mock import Mock

import pytest

from backend.core.ai.routing import AIModel, AIResponse, AIServiceError
from backend.core.uness import gemini_autocorrect, import_service


@pytest.fixture(autouse=True)
def _isolated_verified_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(import_service, "VERIFIED_DIR", tmp_path / "verifies")
    return tmp_path / "verifies"


def _bridge_file(folder, *, title="DP1\nTest", images=None):
    payload = {
        "bridge_schema_version": 1,
        "source": {
            "source_url": "https://entrainement.uness.fr/annales/course/view.php?id=1",
            "collected_at": "2026-07-30T09:00:00+00:00",
            "collection_status": "submitted",
        },
        "instructions": "...",
        "prompt": "Corrige ce quiz.",
        "contents": [
            {
                "title": title,
                "url": "https://entrainement.uness.fr/x",
                "html": "<div>question html</div>",
                "status": "reviewed",
                "images": images or [],
            }
        ],
    }
    path = folder / "dp1-20260730T090000Z.json"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def _quiz_response(title="DP1\nTest") -> AIResponse:
    payload = {"quiz_title": title, "questions": []}
    return AIResponse(text=json.dumps(payload), model=AIModel.FLASH, input_tokens=100, output_tokens=20)


def test_correct_directory_writes_raw_response_and_sums_tokens(tmp_path, _isolated_verified_dir):
    _bridge_file(tmp_path)
    service = Mock()
    service.generate.return_value = _quiz_response()

    result = gemini_autocorrect.correct_directory(tmp_path, service=service)

    assert result["errors"] == []
    assert len(result["corrected"]) == 1
    assert result["input_tokens"] == 100
    assert result["output_tokens"] == 20
    written = list(_isolated_verified_dir.glob("*.json"))
    assert len(written) == 1
    assert json.loads(written[0].read_text(encoding="utf-8")) == {"quiz_title": "DP1\nTest", "questions": []}


def test_correct_directory_processes_every_quiz_in_every_bridge(tmp_path, _isolated_verified_dir):
    _bridge_file(tmp_path, title="DP1\nTest")
    second = tmp_path / "kfp-20260730T090000Z.json"
    second.write_text(
        json.dumps(
            {
                "contents": [
                    {"title": "KFP\nTest", "html": "<div>kfp</div>", "images": []}
                ]
            }
        ),
        encoding="utf-8",
    )
    service = Mock()
    service.generate.side_effect = [_quiz_response("DP1\nTest"), _quiz_response("KFP\nTest")]

    result = gemini_autocorrect.correct_directory(tmp_path, service=service)

    assert len(result["corrected"]) == 2
    assert service.generate.call_count == 2


def test_correct_directory_sends_images_found_by_basename(tmp_path, _isolated_verified_dir):
    (tmp_path / "dermato1.jpg").write_bytes(b"fake-jpeg-bytes")
    _bridge_file(
        tmp_path,
        images=[{"question_id": "q1", "filename": "uness-stamp/images/dermato1.jpg"}],
    )
    service = Mock()
    service.generate.return_value = _quiz_response()

    gemini_autocorrect.correct_directory(tmp_path, service=service)

    _, kwargs = service.generate.call_args
    sent_images = kwargs["images"]
    assert len(sent_images) == 1
    assert sent_images[0].mime_type == "image/jpeg"
    assert sent_images[0].data == b"fake-jpeg-bytes"


def test_correct_directory_reports_missing_image_but_still_writes_correction(tmp_path, _isolated_verified_dir):
    _bridge_file(
        tmp_path,
        images=[{"question_id": "q1", "filename": "uness-stamp/images/missing.jpg"}],
    )
    service = Mock()
    service.generate.return_value = _quiz_response()

    result = gemini_autocorrect.correct_directory(tmp_path, service=service)

    assert len(result["corrected"]) == 1
    assert any("missing.jpg" in error["error"] for error in result["errors"])


def test_correct_directory_records_error_for_invalid_json_response_without_aborting_others(
    tmp_path, _isolated_verified_dir
):
    _bridge_file(tmp_path, title="DP1\nTest")
    second = tmp_path / "kfp-20260730T090000Z.json"
    second.write_text(
        json.dumps({"contents": [{"title": "KFP\nTest", "html": "<div>kfp</div>", "images": []}]}),
        encoding="utf-8",
    )
    service = Mock()
    service.generate.side_effect = [
        AIResponse(text="not valid json", model=AIModel.FLASH, input_tokens=10, output_tokens=1),
        _quiz_response("KFP\nTest"),
    ]

    result = gemini_autocorrect.correct_directory(tmp_path, service=service)

    assert len(result["corrected"]) == 1
    assert len(result["errors"]) == 1


def test_correct_directory_reports_missing_folder(tmp_path, _isolated_verified_dir):
    result = gemini_autocorrect.correct_directory(tmp_path / "does-not-exist", service=Mock())

    assert result["corrected"] == []
    assert len(result["errors"]) == 1


def test_correct_directory_continues_after_gemini_api_error_on_one_quiz(tmp_path, _isolated_verified_dir):
    _bridge_file(tmp_path, title="DP1\nTest")
    second = tmp_path / "kfp-20260730T090000Z.json"
    second.write_text(
        json.dumps({"contents": [{"title": "KFP\nTest", "html": "<div>kfp</div>", "images": []}]}),
        encoding="utf-8",
    )
    service = Mock()
    service.generate.side_effect = [
        AIServiceError("Gemini inaccessible : timeout"),
        _quiz_response("KFP\nTest"),
    ]

    result = gemini_autocorrect.correct_directory(tmp_path, service=service)

    assert len(result["corrected"]) == 1
    assert len(result["errors"]) == 1
    assert "Gemini inaccessible" in result["errors"][0]["error"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_gemini_autocorrect.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'backend.core.uness.gemini_autocorrect'`.

- [ ] **Step 3: Implement the orchestrator**

Create `backend/core/uness/gemini_autocorrect.py`:

```python
"""Automate the manual ChatGPT/Gemini correction step for UNESS annales: call the
Gemini API directly for every bridge JSON in a folder and write its raw response
into UNESS/vérifiés/, exactly as a manual copy-paste would — the existing
import_verified_directory() pipeline then converts, validates and imports it
without knowing whether a human or the API produced the file."""

from __future__ import annotations

import json
import re
from pathlib import Path

from backend.core.ai.routing import AIImageContent, AIServiceError
from backend.core.ai.service import AIService
from backend.core.ai.tasks import generate_uness_correction
from backend.core.uness import import_service

_PROMPT_PATH = Path(__file__).resolve().parents[3] / "prompts" / "uness_correction_prompt.txt"
_IMAGE_MIME_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
}


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-") or "quiz"


def _prompt_text(bridge: dict) -> str:
    text = bridge.get("prompt")
    if isinstance(text, str) and text.strip():
        return text
    return _PROMPT_PATH.read_text(encoding="utf-8") if _PROMPT_PATH.is_file() else ""


def _find_bridge_files(folder: Path) -> list[Path]:
    files = []
    for path in sorted(folder.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(payload, dict) and "contents" in payload:
            files.append(path)
    return files


def _quiz_images(quiz: dict, folder: Path) -> tuple[list[AIImageContent], list[str]]:
    parts: list[AIImageContent] = []
    missing: list[str] = []
    for image in quiz.get("images", []):
        filename = image.get("filename")
        if not filename:
            continue
        candidate = folder / Path(filename).name
        mime_type = _IMAGE_MIME_TYPES.get(candidate.suffix.lower())
        if mime_type is None or not candidate.is_file():
            missing.append(str(filename))
            continue
        parts.append(AIImageContent(mime_type=mime_type, data=candidate.read_bytes()))
    return parts, missing


def _parsed_response(text: str) -> object:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else ""
        if cleaned.rstrip().endswith("```"):
            cleaned = cleaned.rstrip()[:-3]
    return json.loads(cleaned)


def correct_directory(folder: Path, *, service: AIService | None = None) -> dict:
    """Call Gemini once per quiz for every bridge JSON directly in `folder`,
    writing each raw response into UNESS/vérifiés/."""
    folder = Path(folder)
    corrected: list[str] = []
    errors: list[dict[str, str]] = []
    input_tokens = 0
    output_tokens = 0

    if not folder.is_dir():
        errors.append({"file": str(folder), "error": "Dossier introuvable"})
        return {
            "corrected": corrected,
            "errors": errors,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
        }

    import_service.VERIFIED_DIR.mkdir(parents=True, exist_ok=True)
    for bridge_path in _find_bridge_files(folder):
        bridge = json.loads(bridge_path.read_text(encoding="utf-8"))
        prompt = _prompt_text(bridge)
        for quiz in bridge.get("contents", []):
            title = str(quiz.get("title", bridge_path.stem))
            try:
                images, missing = _quiz_images(quiz, folder)
                message = (
                    f"{prompt}\n\n"
                    f"{json.dumps({'title': quiz.get('title'), 'html': quiz.get('html')}, ensure_ascii=False)}"
                )
                response = generate_uness_correction(message, images=images, service=service)
                payload = _parsed_response(response.text)
                out_path = import_service.VERIFIED_DIR / f"{_slug(title)}-{bridge_path.stem}.json"
                out_path.write_text(json.dumps(payload, ensure_ascii=False) + "\n", encoding="utf-8")
                corrected.append(out_path.name)
                input_tokens += response.input_tokens or 0
                output_tokens += response.output_tokens or 0
                if missing:
                    errors.append(
                        {
                            "file": bridge_path.name,
                            "error": f"Images manquantes (ignorées) : {', '.join(missing)}",
                        }
                    )
            except (AIServiceError, ValueError, json.JSONDecodeError, OSError) as exc:
                errors.append({"file": bridge_path.name, "error": str(exc)})

    return {
        "corrected": corrected,
        "errors": errors,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_gemini_autocorrect.py -v`
Expected: PASS (all 7 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/core/uness/gemini_autocorrect.py tests/test_gemini_autocorrect.py
git commit -m "feat: add Gemini API auto-correct orchestrator for UNESS annales"
```

---

### Task 5: Wire the "Corriger avec Gemini" button into the import dialog

**Files:**
- Modify: `frontend/pages/annales.py:63-175`
- Test: `tests/test_annales_page.py`

**Interfaces:**
- Consumes: `gemini_autocorrect.correct_directory(folder: Path) -> dict` (Task 4), existing `_finalize_scan()` closure (`frontend/pages/annales.py:88-107`, unchanged).
- Produces: `_format_gemini_summary(result: dict) -> str` (pure, testable), used by the new button's handler.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_annales_page.py`:

```python
def test_format_gemini_summary_reports_counts_and_estimated_cost() -> None:
    from frontend.pages.annales import _format_gemini_summary

    result = {
        "corrected": ["dp1-x.json", "kfp-x.json"],
        "errors": [],
        "input_tokens": 40_000,
        "output_tokens": 6_000,
    }

    summary = _format_gemini_summary(result)

    assert "2 quiz corrigé" in summary
    assert "0 erreur" in summary
    assert "40" in summary  # input token count, in thousands or raw form
    assert "$" in summary


def test_format_gemini_summary_reports_errors() -> None:
    from frontend.pages.annales import _format_gemini_summary

    result = {
        "corrected": [],
        "errors": [{"file": "dp1.json", "error": "Dossier introuvable"}],
        "input_tokens": 0,
        "output_tokens": 0,
    }

    summary = _format_gemini_summary(result)

    assert "0 quiz corrigé" in summary
    assert "1 erreur" in summary
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_annales_page.py -v`
Expected: FAIL with `ImportError: cannot import name '_format_gemini_summary'`.

- [ ] **Step 3: Implement the summary formatter and wire the button**

In `frontend/pages/annales.py`, add near the top of the module (after the existing helper functions, e.g. after `_distinct_values` around line 42):

```python
# Tarif Google officiel pour gemini-3-flash-preview au 2026-07-31 (ai.google.dev/gemini-api/docs/pricing) :
# 0,25 $ / M tokens entrée, 1,50 $ / M tokens sortie — à revérifier périodiquement.
_GEMINI_FLASH_PRICE_PER_M_INPUT = 0.25
_GEMINI_FLASH_PRICE_PER_M_OUTPUT = 1.50


def _format_gemini_summary(result: dict) -> str:
    corrected = len(result["corrected"])
    errors = len(result["errors"])
    input_tokens = result["input_tokens"]
    output_tokens = result["output_tokens"]
    cost = (
        input_tokens / 1_000_000 * _GEMINI_FLASH_PRICE_PER_M_INPUT
        + output_tokens / 1_000_000 * _GEMINI_FLASH_PRICE_PER_M_OUTPUT
    )
    return (
        f"{corrected} quiz corrigé(s), {errors} erreur(s) — "
        f"~{input_tokens} tokens entrée / {output_tokens} sortie (≈ {cost:.4f} $)"
    )
```

Then, inside `_open_import_dialog`, add the imports at the top of the function body (alongside the existing local imports around lines 64-72):

```python
    from backend.core.uness import gemini_autocorrect
```

Add the folder input and button, right after the `status_lbl` line (line 86) and before `_finalize_scan` is defined:

```python
        ui.separator().classes("my-2")
        ui.label("Ou corriger un dossier existant avec Gemini").classes("text-xs text-slate-500")
        folder_input = ui.input(
            label="Dossier du partiel (JSON + images)",
            placeholder="UNESS/à_vérifier/session-...",
        ).props("outlined dense").classes("w-full")
```

Add the handler after `_launch_collect_and_import` (after line 168, before the buttons row):

```python
        async def _run_gemini_autocorrect() -> None:
            raw_path = (folder_input.value or "").strip()
            if not raw_path:
                status_lbl.set_text("Indique le dossier à corriger.")
                status_lbl.classes("text-negative", remove="text-slate-500 text-primary")
                return
            status_lbl.set_text("Correction Gemini en cours (peut prendre 1-2 min)…")
            status_lbl.classes("text-primary", remove="text-negative")
            result = await asyncio.to_thread(gemini_autocorrect.correct_directory, Path(raw_path))
            status_lbl.set_text(_format_gemini_summary(result))
            status_lbl.classes(
                "text-positive" if result["corrected"] else "text-negative",
                remove="text-primary text-slate-500",
            )
            if result["corrected"]:
                _finalize_scan()
```

Finally, add the new button to the existing buttons row (lines 170-174), changing:

```python
        with ui.row().classes("w-full justify-between items-center mt-3"):
            ui.button("Scanner les JSON existants", icon="fact_check", on_click=lambda: _finalize_scan()).props("flat size=sm color=slate")
            with ui.row().classes("gap-2"):
                ui.button("Annuler", on_click=dialog.close).props("flat")
                ui.button("Lancer la collecte", icon="play_arrow", on_click=_launch_collect_and_import).props("unelevated color=primary")
```

to:

```python
        with ui.row().classes("w-full justify-between items-center mt-3"):
            ui.button("Scanner les JSON existants", icon="fact_check", on_click=lambda: _finalize_scan()).props("flat size=sm color=slate")
            with ui.row().classes("gap-2"):
                ui.button("Annuler", on_click=dialog.close).props("flat")
                ui.button("Corriger avec Gemini", icon="auto_awesome", on_click=_run_gemini_autocorrect).props("flat color=primary")
                ui.button("Lancer la collecte", icon="play_arrow", on_click=_launch_collect_and_import).props("unelevated color=primary")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_annales_page.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/pages/annales.py tests/test_annales_page.py
git commit -m "feat: add Corriger avec Gemini button to the annale import dialog"
```

---

### Task 6: Full verification pass

- [ ] **Step 1: Run the full backend test suite**

Run: `pytest tests/ -q`
Expected: all tests pass, no regressions in `test_uness_import.py`, `test_gemini_conversion.py`, `test_uness_collector.py`, `test_annales_page.py`, `test_ai_routing.py`, `test_ai_tasks.py`.

- [ ] **Step 2: Byte-compile the touched modules**

Run: `python -m py_compile backend/core/ai/routing.py backend/core/ai/tasks.py backend/core/uness/gemini_autocorrect.py scripts/uness/collector.py frontend/pages/annales.py`
Expected: no output, exit code 0.

- [ ] **Step 3: Manual live test with 2 real annales (as planned by the user)**

- Set `GEMINI_API_KEY` in `.env` if not already set.
- Run the app, open "Importer une annale", run "Lancer la collecte" on a real UNESS annale URL to produce a real `UNESS/à_vérifier/session-<stamp>/` folder with bridge JSON(s) and duplicated images.
- Paste that folder path into the new field, click "Corriger avec Gemini".
- Confirm: the status line shows a plausible quiz/error count and token usage; the annale appears imported and viewable in `/annales` afterward with the AI corrections attached; check the real per-request cost/token usage in Google AI Studio's usage dashboard against the number shown in the app.
- Repeat for a second annale to get the "coût réel sur 2 annales" the user asked for.

- [ ] **Step 4: Commit any fixes found during manual testing**

If the manual pass surfaces a bug, fix it, add a regression test reproducing it first (red/green), then commit as its own small commit.
