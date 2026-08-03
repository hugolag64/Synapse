"""backend/core/uness/item_classifier.py — Synapse

entrainement.uness.fr organise ses annales par matière/faculté/année, jamais
par item du programme EDN — ce champ n'existe nulle part en amont du pipeline
(vérifié dans collector.py, json_io.py, chatgpt_bridge.py). Ce module comble ce
vide via un appel Gemini bon marché (flash-lite), borné aux items candidats de
la matière déjà qualifiée manuellement à l'import, pour empêcher toute
invention d'item hors référentiel.
"""
from __future__ import annotations

import json
from dataclasses import dataclass

from loguru import logger

from backend.core.ai.routing import AIModel
from backend.core.ai.tasks import classify_item
from backend.core.qcm.items_mapping import all_items, college_full


@dataclass(frozen=True)
class ItemClassification:
    item_numbers: tuple[str, ...]   # ordonnés, le premier = item principal
    confident: bool                  # False si l'IA n'a identifié aucun candidat fiable


def candidate_items_for_college(college_label: str) -> list[dict]:
    """Items EDN {item, title} dont le collège Notion correspond à `college_label`.

    Retombe sur le référentiel complet (367 items) si le label ne correspond à
    aucun collège connu (ex: matière libre "Autre") plutôt que de bloquer la
    classification.
    """
    if college_label:
        scoped = [e for e in all_items() if college_full(e.get("college", "")) == college_label]
        if scoped:
            return scoped
    return all_items()


def _build_prompt(title: str, matiere: str, context_text: str, candidates: list[dict]) -> str:
    candidate_lines = "\n".join(f"- {c['item']} : {c['title']}" for c in candidates)
    extract = (context_text or "").strip()[:800]
    context_line = f"Extrait de l'énoncé : {extract}\n" if extract else ""
    return f"""Tu dois identifier le ou les items du programme officiel EDN concernés par cette annale médicale.

Titre de l'annale : {title}
Matière qualifiée : {matiere or "non précisée"}
{context_line}
Items candidats (choisis EXCLUSIVEMENT parmi cette liste, n'invente aucun numéro) :
{candidate_lines}

Réponds en JSON strict : {{"item_numbers": ["221"], "confident": true}}
- La plupart des DP/QCM ne testent que 1 à 3 items précis, même quand la liste de candidats est longue.
  NE RECOPIE JAMAIS la liste de candidats entière ou quasi entière : ce serait un signe que tu n'as pas
  vraiment discriminé. Ne liste un item que si l'énoncé/le titre pointe vers lui spécifiquement.
- Exception légitime : un titre explicitement transverse ("SQI", "Série de Questions Isolées", "TCS"
  couvrant toute la matière) peut justifier une liste plus longue — mais seulement dans ce cas précis.
- Si aucun candidat ne correspond avec une certitude raisonnable, réponds {{"item_numbers": [], "confident": false}} plutôt que de deviner.
"""


def classify_exam_items(
    title: str, matiere: str, context_text: str = "", force_model: AIModel | None = None
) -> ItemClassification:
    """Classe une annale/DP parmi les items EDN candidats de sa matière qualifiée.

    Ne retourne jamais un numéro que le modèle n'a pas explicitement reçu comme
    candidat — garde-fou contre l'invention d'un item hors référentiel.

    `force_model` : voir `classify_item` — utilisé pour une passe de correction
    ciblée avec le modèle Flash sur les cas où flash-lite a sur-classifié.
    """
    candidates = candidate_items_for_college(matiere)
    candidate_numbers = {str(c["item"]) for c in candidates}
    prompt = _build_prompt(title, matiere, context_text, candidates)

    try:
        response = classify_item(prompt, force_model=force_model)
        payload = json.loads(response.text)
    except Exception as exc:
        logger.warning(f"classify_exam_items({title!r}) échoué : {exc}")
        return ItemClassification(item_numbers=(), confident=False)

    raw_numbers = payload.get("item_numbers") or []
    kept = [str(n).strip() for n in raw_numbers if str(n).strip() in candidate_numbers]
    confident = bool(payload.get("confident")) and bool(kept)
    return ItemClassification(item_numbers=tuple(kept), confident=confident)
