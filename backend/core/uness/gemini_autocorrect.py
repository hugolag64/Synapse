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
from backend.core.reviews import local_store
from backend.core.uness import gemini_conversion, import_service
from bs4 import BeautifulSoup

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


def _clean_moodle_html(html: str) -> str:
    """Strip navigation, accessibility noise, styles, scripts and redundant containers
    from Moodle quiz HTML to drastically reduce token costs (5x to 10x savings)
    while retaining all clinical text, questions, choices and feedback."""
    soup = BeautifulSoup(html, "html.parser")
    
    # 1. Decompose irrelevant elements
    for selector in [
        "script", "style", "link", "svg", "header", "footer", "nav", ".breadcrumb",
        ".info", ".questionflag", ".accesshide", ".submitbtns", ".singlebutton",
        ".qn_buttons", ".othernav", ".m-t-1", ".editquestionlink"
    ]:
        for el in soup.select(selector):
            el.decompose()

    # 2. Extract context description block if present
    context_text = ""
    desc_block = soup.select_one("div.que.description")
    if desc_block:
        context_text = desc_block.get_text(separator="\n", strip=True)

    # 3. Clean each question container
    cleaned_questions = []
    # Select question blocks (Moodle uses div.que or div[id^='question-'])
    question_divs = soup.select("div.que, div[id^='question-']")
    for q_div in question_divs:
        # Ignore description/context blocks here
        classes = q_div.get("class", [])
        if "description" in classes:
            continue
        q_id = q_div.get("id", "") or str(q_div.get("data-question-id", ""))
        # Question formulation
        qtext_el = q_div.select_one(".qtext, .question-text, .formulation")
        qtext = qtext_el.get_text(separator="\n", strip=True) if qtext_el else ""

        # Answer choices & official responses
        choices = []
        for choice_row in q_div.select(".answer > div, .answer li, .answer tr, .answer .r0, .answer .r1"):
            label_text = choice_row.get_text(separator=" ", strip=True)
            if not label_text:
                continue
            is_checked = choice_row.select_one("input[checked]") is not None
            is_correct = "correct" in choice_row.get("class", []) or bool(choice_row.select(".correct"))
            is_incorrect = "incorrect" in choice_row.get("class", []) or bool(choice_row.select(".incorrect"))
            
            choices.append({
                "text": label_text,
                "checked": is_checked,
                "correct_class": is_correct,
                "incorrect_class": is_incorrect
            })

        # Feedback/outcome
        outcome_el = q_div.select_one(".outcome, .rightanswer, .generalfeedback, .feedback")
        outcome = outcome_el.get_text(separator="\n", strip=True) if outcome_el else ""

        cleaned_questions.append({
            "id": q_id,
            "qtext": qtext,
            "choices": choices,
            "outcome": outcome
        })

    compact_payload = {
        "context": context_text,
        "questions": cleaned_questions
    }
    return json.dumps(compact_payload, ensure_ascii=False)


def _expected_question_count(html: str) -> int:
    """Compte les blocs de question réels du HTML Moodle du bridge — même
    convention de sélection que _clean_moodle_html : les div.que qui ne sont
    pas le bloc de description partagé (vignette clinique, pas une question)."""
    soup = BeautifulSoup(html, "html.parser")
    count = 0
    for q_div in soup.select("div.que, div[id^='question-']"):
        if "description" in q_div.get("class", []):
            continue
        count += 1
    return count


def _correct_one_quiz(
    bridge_path: Path,
    bridge: dict,
    quiz: dict,
    prompt: str,
    folder: Path,
    service: AIService | None,
) -> tuple[str | None, str | None, int, int]:
    """Corrige un seul quiz avec Gemini et écrit sa sortie canonique dans
    import_service.VERIFIED_DIR.

    Retourne (written_filename, message, input_tokens, output_tokens) :
      - written_filename n'est pas None en cas de succès (message peut quand
        même porter un avertissement non bloquant, ex. images manquantes).
      - written_filename est None en cas d'échec (message est alors toujours
        renseigné : erreur API, JSON invalide, ou question(s) manquante(s))."""
    title = str(quiz.get("title", bridge_path.stem))
    try:
        images, missing = _quiz_images(quiz, folder)
        raw_html = quiz.get("html", "")
        # Clean and compact HTML to reduce token usage by up to 90%
        cleaned_content = _clean_moodle_html(raw_html) if raw_html else ""
        expected_questions = _expected_question_count(raw_html) if raw_html else 0

        message = (
            f"{prompt}\n\n"
            f"{json.dumps({'title': quiz.get('title'), 'content': cleaned_content}, ensure_ascii=False)}"
        )

        # Retry loop for rate limits (429) - Free Tier friendly
        max_retries = 5
        response = None
        for attempt in range(max_retries):
            try:
                response = generate_uness_correction(
                    message,
                    images=images,
                    context=title,
                    service=service,
                )
                break
            except AIServiceError as err:
                if ("429" in str(err) or "Too Many Requests" in str(err)) and attempt < max_retries - 1:
                    import time
                    wait_time = 10 * (attempt + 1)  # 10s, 20s, 30s
                    time.sleep(wait_time)
                    continue
                raise err

        if response is None:
            raise AIServiceError("Aucune réponse obtenue du service IA.")

        payload = _parsed_response(response.text)
        quiz_objects = payload if isinstance(payload, list) else [payload]
        exams = gemini_conversion.convert_with_bridge(quiz_objects, bridge)

        got_questions = sum(len(exam.questions) for exam in exams)
        if expected_questions and got_questions < expected_questions:
            return (
                None,
                f"Réponse incomplète : {got_questions}/{expected_questions} questions",
                response.input_tokens or 0,
                response.output_tokens or 0,
            )

        written = None
        for index, exam in enumerate(exams):
            suffix = f"-{index}" if len(exams) > 1 else ""
            out_path = import_service.VERIFIED_DIR / f"{_slug(title)}-{bridge_path.stem}{suffix}.json"
            out_path.write_text(
                json.dumps(exam.to_dict(), ensure_ascii=False) + "\n", encoding="utf-8"
            )
            written = out_path.name

        warning = f"Images manquantes (ignorées) : {', '.join(missing)}" if missing else None
        return written, warning, response.input_tokens or 0, response.output_tokens or 0
    except (AIServiceError, ValueError, KeyError, json.JSONDecodeError, OSError) as exc:
        return None, str(exc), 0, 0


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
        collected_at = str(bridge.get("source", {}).get("collected_at", ""))
        for quiz in bridge.get("contents", []):
            title = str(quiz.get("title", bridge_path.stem))
            written, message, in_tok, out_tok = _correct_one_quiz(
                bridge_path, bridge, quiz, prompt, folder, service
            )
            input_tokens += in_tok
            output_tokens += out_tok
            if written:
                corrected.append(written)
                local_store.resolve_uness_correction_failure(title, collected_at)
            else:
                local_store.record_uness_correction_failure(
                    bridge_folder=str(folder),
                    quiz_title=title,
                    collected_at=collected_at,
                    error_message=message or "Erreur inconnue",
                )
            if message:
                errors.append({"file": bridge_path.name, "error": message})

    return {
        "corrected": corrected,
        "errors": errors,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
    }


def _locate_bridge(quiz_title: str, collected_at: str) -> Path:
    """Cherche le bridge JSON (dans UNESS/à_vérifier puis UNESS/archives) dont
    source.collected_at correspond et dont les contents incluent quiz_title —
    un bridge peut migrer de à_vérifier/ vers archives/<faculté>/ une fois ses
    quiz voisins importés avec succès, donc les deux emplacements sont
    cherchés, à_vérifier/ en premier (le plus frais)."""
    for directory in (import_service.TO_REVIEW_DIR, import_service.ARCHIVE_DIR):
        if not directory.is_dir():
            continue
        for path in sorted(directory.rglob("*.json")):
            if path.name.startswith("."):
                continue
            try:
                bridge = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if not isinstance(bridge, dict) or "contents" not in bridge:
                continue
            source = bridge.get("source", {})
            if str(source.get("collected_at", "")) != collected_at:
                continue
            titles = {item.get("title") for item in bridge.get("contents", []) if isinstance(item, dict)}
            if quiz_title in titles:
                return path
    raise FileNotFoundError(
        f"Bridge introuvable pour le quiz {quiz_title!r} (collected_at={collected_at!r})"
    )


def retry_failed_quiz(failure_id: int, *, service: AIService | None = None) -> dict:
    """Retente exactement un quiz précédemment en échec (clic manuel "Relancer"
    ou boucle de retry en arrière-plan). Relocalise son bridge (qui a pu migrer
    vers archives/ depuis l'échec), le corrige, et met à jour la ligne
    uness_correction_failures en conséquence.

    Retourne {"success": bool, "error": str | None}."""
    failure = local_store.get_uness_correction_failure(failure_id)
    if failure is None:
        return {"success": False, "error": "Entrée introuvable"}

    quiz_title = failure["quiz_title"]
    collected_at = failure["collected_at"]

    try:
        bridge_path = _locate_bridge(quiz_title, collected_at)
    except FileNotFoundError as exc:
        local_store.record_uness_correction_failure(
            bridge_folder=failure["bridge_folder"],
            quiz_title=quiz_title,
            collected_at=collected_at,
            error_message=str(exc),
        )
        return {"success": False, "error": str(exc)}

    bridge = json.loads(bridge_path.read_text(encoding="utf-8"))
    prompt = _prompt_text(bridge)
    quiz = next(
        (item for item in bridge.get("contents", []) if item.get("title") == quiz_title),
        None,
    )
    if quiz is None:
        error = f"Quiz {quiz_title!r} absent du bridge relocalisé ({bridge_path})"
        local_store.record_uness_correction_failure(
            bridge_folder=str(bridge_path.parent),
            quiz_title=quiz_title,
            collected_at=collected_at,
            error_message=error,
        )
        return {"success": False, "error": error}

    import_service.VERIFIED_DIR.mkdir(parents=True, exist_ok=True)
    written, message, _in_tok, _out_tok = _correct_one_quiz(
        bridge_path, bridge, quiz, prompt, bridge_path.parent, service
    )
    if written:
        local_store.resolve_uness_correction_failure(quiz_title, collected_at)
        return {"success": True, "error": message}

    local_store.record_uness_correction_failure(
        bridge_folder=str(bridge_path.parent),
        quiz_title=quiz_title,
        collected_at=collected_at,
        error_message=message or "Erreur inconnue",
    )
    return {"success": False, "error": message}

