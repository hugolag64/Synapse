"""backend/core/uness/exam_simulator.py — Moteur d'Épreuves Blancs UNESS & DP (0 API call)

Charge les Dossiers Progressifs (DP) et KFP archivés localement (archives UNESS + imports IA),
gère la séquence d'examen avec règle d'anti-retour et effectue la notation officielle EDN.
"""

from __future__ import annotations

import json
import random
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from loguru import logger
from backend.core.uness.import_service import ARCHIVE_DIR
from backend.core.uness.models import UnessExam, UnessQuestion

# Dossier d'importation des DP générés par IA
AI_IMPORTS_DIR = ARCHIVE_DIR / "imports_ia"


@dataclass
class QuestionAttempt:
    question_id: str
    user_choices: Dict[str, bool]  # e.g. {"a": True, "b": False, ...}
    correct_choices: Dict[str, bool]
    score_edn: float  # 1.0, 0.5, 0.2, 0.0
    errors_count: int
    is_validated: bool = False


@dataclass
class ExamSession:
    session_id: str
    subject: str
    title: str
    dps: List[Dict[str, Any]]  # Fichiers JSON DP d'examens complets
    current_dp_index: int = 0
    current_question_index: int = 0
    attempts: Dict[str, QuestionAttempt] = field(default_factory=dict)
    is_finished: bool = False
    start_time_iso: str = ""
    end_time_iso: Optional[str] = None


def count_mismatches(user_choices: Dict[str, bool], correct_choices: Dict[str, bool]) -> int:
    """Calcule le nombre de discordances (oublis + faux positifs) entre l'utilisateur et la vérité terrain."""
    mismatches = 0
    all_keys = set(user_choices.keys()).union(set(correct_choices.keys()))
    for key in all_keys:
        u = user_choices.get(key, False)
        c = correct_choices.get(key, False)
        if u != c:
            mismatches += 1
    return mismatches


def compute_edn_score(user_choices: Dict[str, bool], propositions: List[Dict[str, Any]]) -> tuple[float, int]:
    """Calcule le score EDN officiel pour une question à choix multiples.

    Barème EDN :
    - 0 erreur : 1.0 pt
    - 1 erreur : 0.5 pt
    - 2 erreurs : 0.2 pt
    - >= 3 erreurs : 0.0 pt
    - Annulation (0.0 pt) si oubli ou erreur sur une proposition vitale / Rang A critique
    """
    correct_choices = {
        p.get("id", "").lower(): bool(p.get("reponse_uness", p.get("verdict_ia", False)))
        for p in propositions
    }

    # Normalisation des choix utilisateur
    user_map = {k.lower(): bool(v) for k, v in user_choices.items()}

    mismatches = count_mismatches(user_map, correct_choices)

    # Vérification annulation Rang A si configuré
    has_rang_a_fatal = False
    for p in propositions:
        pid = p.get("id", "").lower()
        is_rang_a = p.get("rank") == "A" or p.get("rang") == "A"
        u_val = user_map.get(pid, False)
        c_val = correct_choices.get(pid, False)
        # Oubli d'un vrai Rang A indispensable
        if is_rang_a and c_val is True and u_val is False:
            has_rang_a_fatal = True
            break

    if has_rang_a_fatal:
        return 0.0, mismatches

    if mismatches == 0:
        return 1.0, 0
    elif mismatches == 1:
        return 0.5, 1
    elif mismatches == 2:
        return 0.2, 2
    else:
        return 0.0, mismatches


def list_available_subjects() -> List[str]:
    """Liste toutes les spécialités disponibles dans les archives JSON."""
    subjects = set()
    
    # 1. Scanner les archives officielles UNESS
    if ARCHIVE_DIR.exists():
        for json_path in ARCHIVE_DIR.rglob("*.json"):
            try:
                with open(json_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    subj = data.get("metadata", {}).get("subject")
                    if subj:
                        subjects.add(subj.upper())
            except Exception:
                continue

    # 2. Scanner les imports IA
    if AI_IMPORTS_DIR.exists():
        for json_path in AI_IMPORTS_DIR.rglob("*.json"):
            try:
                with open(json_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    subj = data.get("metadata", {}).get("subject")
                    if subj:
                        subjects.add(subj.upper())
            except Exception:
                continue

    return sorted(list(subjects)) if subjects else ["CARDIOVASCULAIRE", "NEUROLOGIE", "PNEUMOLOGIE", "HÉMATOLOGIE"]


def load_dps_by_subject(subject: Optional[str] = None, max_dps: int = 3) -> List[Dict[str, Any]]:
    """Charge les DP / KFP correspondant à la spécialité demandée (fichiers JSON + SQLite locale)."""
    candidates = []
    
    # 1. Charger depuis la BDD locale (cas importés via le bouton d'importation QCM)
    try:
        from backend.core.reviews.local_store import get_imported_practice_cases
        db_cases = get_imported_practice_cases(limit=100)
        for case in db_cases:
            # Transformer le format SQLite vers le format DP canonique d'examen
            questions = []
            for idx, q in enumerate(case.get("questions", []), start=1):
                props = []
                choices = q.get("choices", [])
                ans_str = str(q.get("answer", "")).upper()
                for c_idx, choice_txt in enumerate(choices):
                    cid = chr(97 + c_idx)  # 'a', 'b', 'c'...
                    # Nettoyage des résidus d'identifiants techniques UNESS (ex: Q16816178:2_ANSWER0.)
                    clean_txt = re.sub(r"^\s*Q\d+:\d+_(?:ANSWER|CHOICE)\d+\.\s*", "", str(choice_txt), flags=re.IGNORECASE).strip()
                    is_correct = cid.upper() in ans_str or clean_txt.startswith(cid.upper())
                    props.append({
                        "id": cid,
                        "texte": clean_txt,
                        "reponse_uness": is_correct,
                        "rank": "A",
                        "explication_ia": q.get("explanation", "")
                    })
                questions.append({
                    "id": f"q{idx}",
                    "type_question": case.get("kind", "DP").upper(),
                    "enonce": q.get("prompt", ""),
                    "propositions": props
                })
            
            stem_text = str(case.get("stem", "")).strip()
            # Ne retenir en BDD SQLite QUE les cas avec un vrai énoncé clinique de DP (pas de simple QCM)
            if len(stem_text) < 50 or "QCM généré" in stem_text:
                continue

            if questions:
                item_nums = case.get("item_numbers", [])
                item_str = item_nums[0] if item_nums else "Transverse"
                dp_data = {
                    "title": case.get("title", "DP Importé"),
                    "dp_context": {"enonce_general": stem_text},
                    "metadata": {
                        "subject": subject or "CARDIOVASCULAIRE",
                        "item_number": item_str,
                        "exam_type": "entraînement"
                    },
                    "questions": questions
                }
                candidates.append(dp_data)
    except Exception as e:
        logger.debug(f"Erreur lors du chargement des cas SQLite: {e}")

    # 2. Charger depuis les archives JSON sur disque
    search_dirs = [ARCHIVE_DIR]
    if AI_IMPORTS_DIR.exists():
        search_dirs.append(AI_IMPORTS_DIR)

    for base_dir in search_dirs:
        if not base_dir.exists():
            continue
        for json_path in base_dir.rglob("*.json"):
            try:
                with open(json_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        items = data
                    elif isinstance(data, dict):
                        items = [data]
                    else:
                        continue

                    for item in items:
                        if not isinstance(item, dict) or not item.get("questions"):
                            continue
                        kind = str(item.get("kind", "") or item.get("type_question", "") or item.get("type", "")).upper()
                        stem = str(item.get("dp_context", {}).get("enonce_general", "") or item.get("stem", "")).strip()
                        is_real_dp = "DP" in kind or "KFP" in kind or len(stem) > 60 or len(item.get("questions", [])) >= 2
                        if not is_real_dp:
                            continue

                        data_subj = str(item.get("metadata", {}).get("subject", "")).upper()
                        if subject is None or not subject or subject.upper() in data_subj or data_subj in subject.upper():
                            candidates.append(item)
            except Exception as e:
                logger.debug(f"Impossible de lire {json_path}: {e}")
                continue

    if not candidates:
        logger.warning(f"Aucun DP trouvé pour la spécialité {subject}, chargement de tous les DP disponibles.")
        # Fallback sur n'importe quel DP
        for base_dir in search_dirs:
            if not base_dir.exists():
                continue
            for json_path in base_dir.rglob("*.json"):
                try:
                    with open(json_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        if data.get("questions"):
                            candidates.append(data)
                except Exception:
                    continue

    # Fonction de nettoyage universelle des propositions et énoncés (ex: Q9148958:2_CHOICE0)
    def _clean_item(item_data: Dict[str, Any]) -> Dict[str, Any]:
        for q in item_data.get("questions", []):
            for p in q.get("propositions", []):
                if "texte" in p:
                    p["texte"] = re.sub(r"^\s*Q\d+:\d+_(?:ANSWER|CHOICE)\d+[\.\s]*", "", str(p["texte"]), flags=re.IGNORECASE).strip()
        return item_data

    cleaned_candidates = [_clean_item(c) for c in candidates]
    random.shuffle(cleaned_candidates)
    return cleaned_candidates[:max_dps]
