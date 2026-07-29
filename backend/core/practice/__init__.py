"""Sessions de questions IA rejouables et historique pédagogique."""

from .mastery import record_ai_practice_mastery
from .models import PracticeKind, PracticeSessionSpec, QuestionKind
from .service import PracticeService

__all__ = [
    "PracticeKind", "PracticeSessionSpec", "QuestionKind", "PracticeService",
    "record_ai_practice_mastery",
]
