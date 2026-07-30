"""Convert local UNESS review HTML into the canonical UNESS exam model."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import replace
from pathlib import Path
from urllib.parse import unquote, urlparse

from bs4 import BeautifulSoup, Tag

from .artifacts import ExamMetadata, RawMedia, RawUnessArtifact
from .models import UnessExam, UnessImage, UnessProposition, UnessQuestion

_QUESTION_TYPES = {"QRM", "QRU", "QRP/L", "DP", "KFP", "QROC"}
_TRUE_CLASSES = {"correct", "is-correct", "answer-green", "green", "success"}
_FALSE_CLASSES = {"incorrect", "is-incorrect", "answer-red", "red", "error"}


def _text(node: Tag | None) -> str:
    return node.get_text(" ", strip=True) if node else ""


def _first(node: Tag, selectors: str) -> Tag | None:
    for selector in selectors.split(","):
        found = node.select_one(selector.strip())
        if found:
            return found
    return None


def _question_type(node: Tag) -> str:
    raw = str(node.get("data-question-type", "")).upper().strip()
    if raw in _QUESTION_TYPES:
        return raw
    visible = _text(_first(node, ".question-type, .type-question"))
    for candidate in _QUESTION_TYPES:
        if candidate in visible.upper():
            return candidate
    return "QRM"


def _answer_value(node: Tag) -> bool | None:
    classes = {str(value).lower() for value in node.get("class", [])}
    if classes & _FALSE_CLASSES:
        return False
    if classes & _TRUE_CLASSES:
        return True
    return None


def _propositions(node: Tag) -> tuple[UnessProposition, ...]:
    answers = node.select("li.answer, .answers > .answer, [data-answer]")
    unique_answers = list(dict.fromkeys(answers))
    propositions: list[UnessProposition] = []
    for index, answer in enumerate(unique_answers, start=1):
        label_node = _first(answer, ".answer-label, .label, [data-answer-label]")
        label = str(answer.get("data-answer-label", "")) or _text(label_node)
        match = re.match(r"\s*([A-Za-z0-9]+)[.)]?", label)
        proposition_id = match.group(1).upper() if match else str(index)
        text_node = _first(answer, ".answer-text, .text, [data-answer-text]")
        proposition_text = _text(text_node)
        if not proposition_text:
            proposition_text = _text(answer)
            if label:
                proposition_text = proposition_text.removeprefix(label).strip()
        propositions.append(
            UnessProposition(
                id=proposition_id,
                texte=proposition_text,
                reponse_uness=_answer_value(answer),
            )
        )
    return tuple(propositions)


def _images(node: Tag) -> tuple[UnessImage, ...]:
    images: list[UnessImage] = []
    for image in node.select("img[src]"):
        figure = image.find_parent("figure")
        images.append(
            UnessImage(
                source_url=str(image.get("src", "")),
                alt_text=str(image.get("alt", "")),
                caption=_text(figure.select_one("figcaption")) if figure else "",
            )
        )
    return tuple(images)


def _dp_context(node: Tag) -> dict[str, str]:
    context = node.find_previous(class_=lambda value: value and "dp-context" in value)
    score = _text(_first(node, ".review-score, .score, [data-score]"))
    result: dict[str, str] = {}
    if context:
        context_id = str(context.get("data-dp-id", ""))
        if context_id:
            result["id"] = context_id
        result["text"] = _text(context)
    if score:
        result["score_text"] = score
    return result


def extract_review_content(html: str) -> list[UnessQuestion]:
    """Extract reviewed questions from a local UNESS HTML snapshot.

    The parser relies on semantic and CSS-class alternatives because the review page
    markup differs slightly between content types.  It never makes a network request.
    """
    soup = BeautifulSoup(html, "html.parser")
    nodes = soup.select("[data-question-id], .review-question, .question-block")
    questions: list[UnessQuestion] = []
    for index, node in enumerate(dict.fromkeys(nodes), start=1):
        question_id = str(node.get("data-question-id", "")).strip() or f"question-{index}"
        prompt = _text(_first(node, ".question-text, .qtext, .question-content, .prompt"))
        if not prompt:
            prompt = _text(node.select_one("header p, h3, h4"))
        questions.append(
            UnessQuestion(
                id=question_id,
                type_question=_question_type(node),
                enonce=prompt,
                propositions=_propositions(node),
                images=_images(node),
                support_visuel_seul=bool(
                    node.select_one(".interactive-widget, [data-widget], .hotspot, canvas")
                ),
                dp_context=_dp_context(node),
            )
        )
    return questions


def _slug(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-z0-9]+", "-", normalized.lower()).strip("-")
    return slug or "uness-exam"


def _safe_filename(filename: str) -> str:
    name = Path(unquote(urlparse(filename).path)).name
    safe = re.sub(r"[^A-Za-z0-9._-]+", "-", name).strip(".-")
    return safe or "media"


def _copy_media(media: list[RawMedia], directory: Path) -> dict[str, str]:
    directory.mkdir(parents=True, exist_ok=True)
    copied: dict[str, str] = {}
    for index, item in enumerate(media, start=1):
        prefix = f"q{item.question_number:02d}" if item.question_number else f"media-{index:02d}"
        target = directory / f"{prefix}-{_safe_filename(item.filename)}"
        target.write_bytes(item.content)
        copied[_safe_filename(item.filename)] = str(target)
    return copied


def _link_images(question: UnessQuestion, copied_media: dict[str, str]) -> UnessQuestion:
    images = tuple(
        replace(image, local_path=copied_media.get(_safe_filename(image.source_url), ""))
        for image in question.images
    )
    return replace(question, images=images)


def normalize_artifact(artifact: RawUnessArtifact, metadata: ExamMetadata) -> UnessExam:
    """Normalize captured local content, preserving source provenance and visual files."""
    root = artifact.artifact_root or Path("data") / "uness" / "artifacts"
    directory = Path(root) / _slug(metadata.titre)
    copied_media = _copy_media(artifact.media, directory)
    questions = [
        _link_images(question, copied_media)
        for html in artifact.html_by_content.values()
        for question in extract_review_content(html)
    ]
    first_context = next((question.dp_context for question in questions if question.dp_context), {})
    return UnessExam(
        faculty=metadata.faculte,
        level=metadata.niveau,
        year=metadata.annee,
        title=metadata.titre,
        dp_context=first_context,
        questions=tuple(questions),
        provenance={
            "source": "UNESS",
            "source_url": artifact.source_url,
            "contents": list(artifact.html_by_content),
        },
        metadata={"subject": metadata.matiere, "exam_type": metadata.type_epreuve},
    )
