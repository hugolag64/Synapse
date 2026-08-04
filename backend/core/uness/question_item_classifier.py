"""Question-level item classification for imported EDN sessions."""

from __future__ import annotations

from dataclasses import replace

from loguru import logger

from .item_classifier import classify_exam_items
from .models import UnessExam

MAX_ITEMS_PER_QUESTION = 2


def classify_exam_questions(exam: UnessExam, matiere: str = "") -> UnessExam:
    """Keep explicit item metadata and classify only unresolved questions."""
    classified = []
    for question in exam.questions:
        if question.item_numbers:
            classified.append(question)
            continue
        try:
            result = classify_exam_items(
                question.enonce,
                matiere or str(exam.metadata.get("subject", "")),
                context_text=str(question.dp_context.get("enonce_general", "")),
            )
            numbers = tuple(dict.fromkeys(str(item).strip() for item in result.item_numbers if str(item).strip()))
            if not result.confident or not numbers or len(numbers) > MAX_ITEMS_PER_QUESTION:
                classified.append(question)
            else:
                classified.append(replace(question, item_numbers=numbers))
        except Exception as exc:  # classification must not block a usable import
            logger.warning(f"Classification item question {question.id!r} échouée : {exc}")
            classified.append(question)
    return replace(exam, questions=tuple(classified))
