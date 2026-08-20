"""Rapproche un thème abrégé de conférence (ex: "HGE", "Cardio", "MI") du
référentiel collège UNESS déjà connu de Synapse (items_mapping._ABBR_TO_NOTION
et les noms Notion complets qui en dérivent).

Deux passes, dans cet ordre :
  1. Table d'abréviations exactes (insensible à la casse) — couvre les sigles
     qui ne sont pas de simples préfixes du nom complet (ex: "MI", "GO").
  2. Préfixe des mots "forts" (>= 4 caractères) du thème contre les mots du
     nom de collège complet — couvre les troncatures lisibles ("Cardio" ->
     "Cardiovasculaire"). Les mots courts sont ignorés : trop peu
     discriminants pour un rapprochement fiable.
Un thème sans mot fort qui n'a pas matché en passe 1, ou qui matche
plusieurs collèges en passe 2, part en validation humaine plutôt que
de risquer un mauvais rapprochement.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from backend.core.qcm.items_mapping import abbreviation_to_college, all_college_names

_STOPWORDS = {"de", "du", "des", "la", "le", "les", "et", "en", "d", "l"}


@dataclass(frozen=True)
class MatchResult:
    status: str
    college_name: str | None


def _normalize(text: str) -> str:
    text = unicodedata.normalize("NFD", text or "")
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    text = re.sub(r"[^\w\s]", " ", text.lower())
    return " ".join(text.split())


def _words(text: str) -> list[str]:
    return [w for w in _normalize(text).split() if w not in _STOPWORDS and len(w) >= 2]


def match_college(theme_raw: str) -> MatchResult:
    for word in theme_raw.split():
        college = abbreviation_to_college(word)
        if college:
            return MatchResult(status="matched", college_name=college)

    strong_words = [w for w in _words(theme_raw) if len(w) >= 4]
    if not strong_words:
        return MatchResult(status="needs_validation", college_name=None)

    candidates: set[str] = set()
    for college_name in all_college_names():
        college_words = _words(college_name)
        if all(any(cw.startswith(sw) for cw in college_words) for sw in strong_words):
            candidates.add(college_name)

    if len(candidates) == 1:
        return MatchResult(status="matched", college_name=next(iter(candidates)))
    return MatchResult(status="needs_validation", college_name=None)
