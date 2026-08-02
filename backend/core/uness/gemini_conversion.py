"""Merge a raw AI (ChatGPT/Gemini) correction response with its source bridge.

The AI receives a bridge JSON bundling one or more quizzes' raw Moodle HTML
(see `scripts/uness/collector.py`) and returns one quiz object — or a JSON
array of them, when several quizzes were corrected in one exchange — per
`prompts/uness_correction_prompt.txt`. This module locates the bridge a given
response was generated from (by matching quiz titles) and merges the two into
canonical `UnessExam` records ready for `import_service`.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup

from .models import _QUESTION_TYPES, UnessExam, UNSUPPORTED_VISUAL_EXPLANATION

_SHORT_ANSWER_TYPES = {"shortanswer"}
_ZONE_TYPES = {"qzone"}

# Used when the breadcrumb doesn't yield a usable value, so an import never
# blocks on missing metadata — the user corrects it afterward via the
# annale's edit form instead of losing the whole partiel.
PLACEHOLDER = "À renseigner"


def _general_context(html: str) -> str:
    """Extract a DP/KFP/mDP quiz's shared clinical vignette straight from the Moodle
    HTML — deterministic (no risk of AI transcription drift), and the only place
    that text exists since the per-question prompt schema never asks the AI to
    echo it back."""
    soup = BeautifulSoup(html, "html.parser")
    block = soup.select_one("div.que.description")
    if block is None:
        return ""
    for junk in block.select(".info, .questionflag, .accesshide"):
        junk.decompose()
    return block.get_text(separator="\n", strip=True)


def _breadcrumb(html: str) -> list[str]:
    nav = re.search(r'<ol class="breadcrumb">(.*?)</ol>', html, re.S)
    if not nav:
        return []
    items = re.findall(r'<a[^>]*>([^<]+)</a>|<span>([^<]+)</span>', nav.group(1))
    return [a or b for a, b in items]


def _extract_year(text: str) -> int | None:
    match = re.search(r"(\d{2})(\d{2})(\d{2})$", text)  # trailing DDMMYY, e.g. "..._090224"
    if match:
        return 2000 + int(match.group(3))
    match = re.search(r"(\d{1,2})/(\d{1,2})/(\d{4})", text)  # DD/MM/YYYY anywhere
    if match:
        return int(match.group(3))
    match = re.search(r"\b(20\d{2})\b", text)  # bare 4-digit year anywhere
    if match:
        return int(match.group(1))
    return None


def _exam_metadata(bridge_html: str, *, content_label: str = "", fallback_year: int | None = None) -> dict[str, Any]:
    """Best-effort faculty/level/subject/course_title/year from the Moodle breadcrumb.

    Different UNESS sites nest their breadcrumb to different depths (some end at
    the course, some one level deeper at the quiz itself) and use different date
    formats. Never raises — falls back to `PLACEHOLDER`/`fallback_year` so an
    exam always imports; the user corrects it afterward if needed."""
    crumbs = _breadcrumb(bridge_html)
    if crumbs and content_label and crumbs[-1].strip() == content_label.strip():
        crumbs = crumbs[:-1]
    if len(crumbs) >= 4:
        faculty, category, course_title = crumbs[1], crumbs[2], crumbs[3]
    elif len(crumbs) >= 2:
        faculty, category, course_title = crumbs[0], crumbs[-2], crumbs[-1]
    else:
        faculty = category = course_title = ""
    level_match = re.search(r"\(([^)]+)\)", category)
    level = level_match.group(1) if level_match else category
    subject = re.sub(r"\s*\([^)]*\)\s*$", "", category).strip()
    return {
        "faculty": faculty.strip() or PLACEHOLDER,
        "level": level.strip() or PLACEHOLDER,
        "subject": subject or PLACEHOLDER,
        "course_title": course_title.strip() or PLACEHOLDER,
        "year": _extract_year(course_title) or fallback_year,
    }


def _question_count_hint(question_text: str) -> int | None:
    match = re.search(r"(\d+)\s*réponses?\s+(?:est|sont)\s+attendue", question_text, re.I)
    return int(match.group(1)) if match else None


def _type_question(raw_type: str, question_text: str, propositions: list[dict]) -> str:
    """Fallback heuristic used only when the AI omits the required `type_question`."""
    if raw_type in _QUESTION_TYPES:
        return raw_type
    if raw_type in _SHORT_ANSWER_TYPES or raw_type in _ZONE_TYPES:
        return "QROC"
    text_lower = question_text.lower()
    if "hypothèse" in text_lower and ("information additionnelle" in text_lower or "effet sur l'hypothèse" in text_lower):
        return "TCS"
    hint = _question_count_hint(question_text)
    if hint is not None and hint > 1:
        return "QRP/L"
    correct_count = sum(1 for p in propositions if p.get("reponse_officielle") is True)
    return "QRU" if correct_count <= 1 else "QRM"


def _proposition(raw: dict) -> dict:
    official = raw.get("reponse_officielle")
    verdict = raw.get("verdict_ia")
    confidence = raw.get("confiance_ia")
    if verdict is None:
        # The manual bridge's import gate requires a boolean verdict (no "indéterminé"
        # state), matching the automated ai_verifier contract. Defer to the official
        # answer but cap the confidence so the AI's uncertainty stays visible.
        verdict = bool(official) if official is not None else False
        confidence = min(confidence, 0.6) if isinstance(confidence, (int, float)) else 0.5
    statut = "incertain" if official is None else ("concordant" if official == verdict else "desaccord")
    commentaire = raw.get("commentaire_desaccord", "")
    if statut == "desaccord" and not commentaire.strip():
        commentaire = "Désaccord entre la correction officielle et l'avis IA."
    return {
        "id": raw["id"],
        "texte": raw["texte"],
        "reponse_uness": official,
        "verdict_ia": verdict,
        "explication_ia": raw.get("explication", ""),
        "confiance_ia": confidence,
        "commentaire_desaccord": commentaire,
        "statut": statut,
    }


def _image(raw: dict, bridge_image: dict) -> dict:
    """`bridge_image` is what we know from downloading it (real local filename);
    `raw` is the AI's own report on whether it could analyze that image."""
    accessible = bool(raw.get("accessible_ia"))
    return {
        "source_url": "",
        "local_path": bridge_image.get("filename", ""),
        "alt_text": bridge_image.get("alt_text") or raw.get("type", ""),
        "caption": "",
        "metadata": {
            **{k: v for k, v in raw.items() if k not in {"accessible_ia", "filename"}},
            "verification_status": "provided_to_ai" if accessible else "not_provided",
        },
    }


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


def _question(raw: dict, bridge_images: list[dict]) -> dict:
    propositions = raw.get("propositions", [])
    question_images = [img for img in bridge_images if img.get("question_id") == raw.get("id")]
    media_by_filename = {m.get("filename"): m for m in raw.get("media", [])}
    all_media_accessible = (
        all(bool(media_by_filename.get(img["filename"], {}).get("accessible_ia")) for img in question_images)
        if question_images
        else True
    )
    verification_status = raw.get("verification_status", "verified")
    if question_images and not all_media_accessible:
        verification_status = "unsupported"
    enonce = raw.get("enonce", raw.get("question", ""))
    type_question = raw.get("type_question")
    if type_question not in _QUESTION_TYPES:
        type_question = _type_question(raw.get("type", ""), enonce, propositions)
    return {
        "id": raw["id"],
        "type_question": type_question,
        "enonce": enonce,
        "propositions": (
            _sanitize_unsupported_propositions([_proposition(p) for p in propositions])
            if verification_status == "unsupported"
            else [_proposition(p) for p in propositions]
        ),
        "images": [_image(media_by_filename.get(img["filename"], {}), img) for img in question_images],
        "support_visuel_seul": bool(question_images) and not propositions,
        "verification_status": verification_status,
        # Deliberately empty: question.dp_context is rendered before the learner
        # answers (shared vignette / pre-answer context). The AI's own correction
        # commentary (correction_globale, reponse_officielle_texte, etc.) must never
        # go here — nothing downstream reads it from this field anyway, and it
        # previously leaked "Réponses officiellement exactes : ..." into the
        # question card before any answer was given.
        "dp_context": {},
    }


def _quiz_objects(payload: Any) -> list[dict]:
    return payload if isinstance(payload, list) else [payload]


def is_raw_ai_response(payload: Any) -> bool:
    """True when `payload` looks like an un-converted AI response (one quiz object,
    or an array of them), as opposed to an already-canonical `UnessExam` dict."""

    def _is_quiz_shape(item: Any) -> bool:
        return isinstance(item, dict) and "quiz_title" in item and "questions" in item

    if isinstance(payload, list):
        return bool(payload) and all(_is_quiz_shape(item) for item in payload)
    return _is_quiz_shape(payload)


def find_bridge_for_title(quiz_title: str, search_dirs: list[Path], target_question_ids: set[str] | None = None) -> Path:
    """Find the single bridge file (across `search_dirs`) that contains this exact
    quiz title. If multiple bridges match by title, filter by target_question_ids if provided."""
    candidates: list[Path] = []
    for directory in search_dirs:
        if not directory.is_dir():
            continue
        for path in sorted(directory.rglob("*.json")):
            if path.name.startswith("obsolete-") or path.name.startswith("."):
                continue
            try:
                raw_text = path.read_text(encoding="utf-8")
                bridge = json.loads(raw_text)
            except (OSError, json.JSONDecodeError):
                continue
            if not isinstance(bridge, dict) or "contents" not in bridge:
                continue
            titles = {item.get("title") for item in bridge.get("contents", []) if isinstance(item, dict)}
            if quiz_title in titles:
                # If target_question_ids provided and multiple candidates exist, verify at least one question ID is in raw_text
                if target_question_ids and not any(qid in raw_text for qid in target_question_ids):
                    continue
                candidates.append(path)
        if candidates:
            break
    if not candidates:
        raise ValueError(
            f"Aucun bridge ne contient le quiz {quiz_title!r} "
            "(vérifie qu'il est toujours dans UNESS/à_vérifier ou UNESS/archives)"
        )
    if len(candidates) > 1:
        names = ", ".join(f"{p.parent.name}/{p.name}" for p in candidates)
        raise ValueError(f"Plusieurs bridges contiennent le quiz {quiz_title!r}, ambigu : {names}")
    return candidates[0]


def _normalize_title(title: str) -> str:
    # Real Gemini responses routinely echo back only the first line of a
    # multi-line bridge title (e.g. "mDP1\nTest" -> "mDP1"), even when given the
    # exact title in the prompt. Match on that first line so a simplified
    # AI-returned title still resolves to its bridge instead of erroring out.
    return str(title).splitlines()[0].strip() if title else ""


def convert_with_bridge(quiz_objects: list[dict], bridge: dict) -> list[UnessExam]:
    """Merge already-parsed quiz responses with an already-parsed bridge dict."""
    bridge_by_title = {_normalize_title(item["title"]): item for item in bridge["contents"]}
    source = bridge["source"]
    collected_year_match = re.match(r"(\d{4})", str(source.get("collected_at", "")))
    fallback_year = (
        int(collected_year_match.group(1)) if collected_year_match else datetime.now(timezone.utc).year
    )

    exams: list[UnessExam] = []
    for quiz in quiz_objects:
        title = str(quiz["quiz_title"])
        bridge_entry = bridge_by_title.get(_normalize_title(title))
        if bridge_entry is None:
            raise ValueError(f"Quiz {title!r} absent du bridge (titres disponibles : {sorted(bridge_by_title)})")
        html = bridge_entry.get("html", "")
        bridge_images = bridge_entry.get("images", [])
        content_label = title.splitlines()[0]
        meta = _exam_metadata(html, content_label=content_label, fallback_year=fallback_year)
        raw_questions = quiz.get("questions", [])
        # Some AI responses include the shared clinical vignette as its own "question"
        # (no propositions to grade) despite the prompt asking it not to — every real
        # question has at least one proposition, so this filters that artifact out
        # without depending on exact wording matching our own HTML-extracted vignette.
        answerable = [
            q
            for q in raw_questions
            if q.get("verification_status") == "unsupported" or q.get("propositions") or q.get("media")
        ]
        claimed_ids = {q.get("id") for q in answerable}
        leftover_images = [img for img in bridge_images if img.get("question_id") not in claimed_ids]
        dp_context: dict[str, Any] = {}
        general_context = _general_context(html)
        if general_context:
            dp_context["enonce_general"] = general_context
        if leftover_images:
            dp_context["images"] = [_image({}, img) for img in leftover_images]
        exam_payload = {
            "schema_version": 1,
            "faculty": meta["faculty"],
            "level": meta["level"],
            "year": meta["year"],
            "title": f"{meta['course_title']} — {content_label}",
            "dp_context": dp_context,
            "questions": [_question(q, bridge_images) for q in answerable],
            "provenance": {
                "source": "Gemini+UNESS",
                "source_url": source["source_url"],
                "collected_at": source["collected_at"],
                "collection_status": source["collection_status"],
            },
            "metadata": {
                "subject": meta["subject"],
                "exam_type": "partiel",
                "metadonnees_a_verifier": PLACEHOLDER in (meta["faculty"], meta["level"], meta["subject"]),
            },
        }
        exams.append(UnessExam.from_dict(exam_payload))
    return exams


def convert_raw_payload(payload: Any, search_dirs: list[Path]) -> list[UnessExam]:
    """Merge a raw AI response (one quiz, or an array of quizzes) with its matching
    bridge file(s) — auto-located across `search_dirs`, independently per quiz since
    a response can combine quizzes collected into separate bridge files — to produce
    one canonical `UnessExam` per quiz."""
    bridges_by_path: dict[Path, dict] = {}
    exams: list[UnessExam] = []
    for quiz in _quiz_objects(payload):
        title = str(quiz["quiz_title"])
        question_ids = {q["id"] for q in quiz.get("questions", []) if isinstance(q, dict) and "id" in q}
        bridge_path = find_bridge_for_title(title, search_dirs, target_question_ids=question_ids)
        if bridge_path not in bridges_by_path:
            bridges_by_path[bridge_path] = json.loads(bridge_path.read_text(encoding="utf-8"))
        exams.extend(convert_with_bridge([quiz], bridges_by_path[bridge_path]))
    return exams
