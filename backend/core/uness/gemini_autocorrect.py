"""Automate the manual ChatGPT/Gemini correction step for UNESS annales: call the
Gemini API directly for every bridge JSON in a folder and convert its response
immediately, using the exact bridge this module already read — unlike a manual
ChatGPT/Gemini paste, this never needs the downstream title-based bridge search
(gemini_conversion.find_bridge_for_title), which raises an ambiguity error as soon
as two à_vérifier sessions happen to share a quiz title (e.g. the same course
collected twice)."""

from __future__ import annotations

import json
import re
from pathlib import Path

from backend.core.ai.routing import AIImageContent, AIServiceError
from backend.core.ai.service import AIService
from backend.core.ai.tasks import generate_uness_correction
from backend.core.uness import gemini_conversion, import_service

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


_json_decoder = json.JSONDecoder()


def _parsed_response(text: str) -> object:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else ""
        if cleaned.rstrip().endswith("```"):
            cleaned = cleaned.rstrip()[:-3]
    # Seen live: Gemini sometimes appends extra content after a fully valid JSON
    # value (e.g. a trailing note). json.loads rejects that outright, so parse
    # just the leading JSON value and ignore whatever follows it.
    value, _ = _json_decoder.raw_decode(cleaned.strip())
    return value


def correct_directory(folder: Path, *, service: AIService | None = None) -> dict:
    """Call Gemini once per quiz for every bridge JSON directly in `folder`,
    converting each response with its own bridge on the spot and writing the
    already-canonical exam into UNESS/vérifiés/."""
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
                quiz_objects = payload if isinstance(payload, list) else [payload]
                exams = gemini_conversion.convert_with_bridge(quiz_objects, bridge)
                for index, exam in enumerate(exams):
                    suffix = f"-{index}" if len(exams) > 1 else ""
                    out_path = (
                        import_service.VERIFIED_DIR / f"{_slug(title)}-{bridge_path.stem}{suffix}.json"
                    )
                    out_path.write_text(
                        json.dumps(exam.to_dict(), ensure_ascii=False) + "\n", encoding="utf-8"
                    )
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
            except (AIServiceError, ValueError, KeyError, json.JSONDecodeError, OSError) as exc:
                errors.append({"file": bridge_path.name, "error": str(exc)})

    return {
        "corrected": corrected,
        "errors": errors,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
    }
