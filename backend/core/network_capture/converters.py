"""
network_capture/converters.py
------------------------------
Transforme les réponses JSON brutes de Hypocampus / EDN Pro
en sessions Synapse QCM (format attendu par ai_qcm/service.py).

APRÈS la phase de découverte (capture_qcm.py discover), remplis les
fonctions extract_* en mappant les clés de l'API découverte.
Les marqueurs  # ← À ADAPTER  indiquent les champs à vérifier.
"""
from __future__ import annotations

import re
from datetime import datetime, date
from typing import Any


# ── Détection de plateforme ────────────────────────────────────────────────────

def detect_platform(url: str) -> str:
    url = url.lower()
    if "hypocampus" in url:
        return "Hypocampus"
    if "ednpro" in url or "edn-pro" in url or "edn.fr" in url:
        return "EDNpro"
    return "Inconnu"


# ── Normalisation commune ──────────────────────────────────────────────────────

def _to_date_str(val: Any) -> str:
    """Convertit n'importe quel format de date en YYYY-MM-DD."""
    if not val:
        return datetime.today().strftime("%Y-%m-%d")
    s = str(val)
    # ISO 8601 : 2024-03-15T10:00:00Z
    m = re.search(r"(\d{4}-\d{2}-\d{2})", s)
    if m:
        return m.group(1)
    return datetime.today().strftime("%Y-%m-%d")


def _to_float(val: Any, total: Any = None) -> float | None:
    """Convertit un score brut en pourcentage float."""
    if val is None:
        return None
    try:
        v = float(str(val).replace(",", ".").replace("%", "").strip())
        if total is not None and float(total) > 0:
            return round(v / float(total) * 100, 1)
        if 0 <= v <= 1:
            return round(v * 100, 1)
        return round(v, 1)
    except (ValueError, TypeError):
        return None


def _to_score_raw(correct: Any, total: Any) -> str | None:
    if correct is not None and total is not None:
        return f"{correct}/{total}"
    return None


# ── Extracteur Hypocampus ──────────────────────────────────────────────────────
# Ces mappings sont des SUPPOSITIONS basées sur des conventions REST courantes.
# À corriger après avoir inspecté les dumps dans data/network_capture/

def extract_sessions_hypocampus(data: dict | list) -> list[dict]:
    """
    Transforme la réponse API Hypocampus en liste de sessions Synapse.

    Format réel découvert (GET /api/hypo3/v1/qs/sessions/{id}?pos=1) :
      {
        "id": "MjY4...",
        "title": "111. Dermatoses faciales",
        "parentTitle": "111. Dermatoses faciales",
        "created": "2026-06-21T13:52:13.221Z",
        "complete": true,
        "type": "exam",
        "statistics": {
          "points": 2,
          "answeredPoints": 2,
          "totalPoints": 5
        },
        "lastAnswered": { ... question details ... }
      }

    Accepte une liste de ces objets (sortie du snippet JS SYNAPSE_HYPO:).
    """
    sessions = []
    items = data if isinstance(data, list) else _unwrap(data)

    for item in items:
        if not isinstance(item, dict):
            continue

        # Titre du cours
        course_title = item.get("title") or item.get("parentTitle") or ""

        # Numéro d'item (extrait du titre : "111. Dermatoses..." → "111")
        item_number = ""
        if course_title:
            m = re.match(r"^(\d+)\.", course_title.strip())
            if m:
                item_number = m.group(1)

        # Format 1 : /qs/sessions/{id}?pos=1  → champs dans statistics{}
        # Format 2 : /qs/sessions/latest/all  → champs plats sur l'objet
        stats          = item.get("statistics") or {}
        total_pts      = stats.get("totalPoints")      or item.get("totalPoints")
        answered_pts   = stats.get("answeredPoints")   or item.get("answeredPoints")
        scored_pts     = stats.get("points")           or item.get("points")

        # Score accuracy = points obtenus / points disponibles sur répondues
        # Plus juste pour les sessions incomplètes
        denom = answered_pts if answered_pts else total_pts
        pct   = _to_float(scored_pts, denom)
        raw   = (
            f"{scored_pts}/{answered_pts}" if answered_pts
            else _to_score_raw(scored_pts, total_pts)
        )
        total   = int(total_pts)   if total_pts   is not None else None
        correct = scored_pts       if scored_pts  is not None else None
        wrong   = round((answered_pts - scored_pts), 2) if (answered_pts is not None and scored_pts is not None) else None

        # Date
        date_str = _to_date_str(item.get("created") or item.get("updated"))

        # Type de session
        session_type = (item.get("type") or "QCM").upper()
        if session_type == "EXAM":
            session_type = "QCM"

        sessions.append({
            "course_title":    str(course_title),
            "item_number":     str(item_number),
            "score_raw":       str(raw) if raw else "",
            "score_percent":   pct,
            "total_questions": int(total) if total is not None else None,
            "correct_answers": int(correct) if correct is not None else None,
            "wrong_answers":   int(wrong) if wrong is not None else None,
            "date":            date_str,
            "session_type":    session_type,
            "error_types":     [],
            "weak_points":     [],
            "questions":       [],
            "comments":        "",
        })

    return sessions


# ── Extracteur EDN Pro ─────────────────────────────────────────────────────────

def _classify_question_error(q: dict, session_score_pct: float | None) -> str:
    """
    Classifie une question ratée en un des 4 types Synapse.

    Règles :
    - QROC         → connaissance  (réponse ouverte, fallait connaître)
    - QRE vide     → connaissance
    - QRE raté     → raisonnement
    - QCM off-by-1 + score ≥ 60 % → inattention
    - QCM excès ≥ 2 > omissions   → stratégie EDN  (coché trop)
    - QCM omissions > excès        → connaissance
    - sinon                        → raisonnement
    """
    qtype = (q.get("type") or "qcm").lower()
    props = q.get("propositions") or []

    correct_set  = {p["label"] for p in props if p.get("is_correct") and p.get("label")}
    selected_set = {p["label"] for p in props if p.get("was_selected") and p.get("label")}
    omissions = correct_set  - selected_set
    excesses  = selected_set - correct_set

    if qtype == "qroc":
        return "connaissance"

    if qtype == "qre":
        return "connaissance" if not selected_set else "raisonnement"

    # QCM
    n_omit, n_exc = len(omissions), len(excesses)
    if (n_omit + n_exc) == 1 and (session_score_pct is not None and session_score_pct >= 60):
        return "inattention"
    if n_exc >= 2 and n_exc > n_omit:
        return "stratégie EDN"
    if n_omit > n_exc:
        return "connaissance"
    return "raisonnement"


def _classify_session_errors(questions: list[dict], session_score_pct: float | None) -> list[str]:
    """Retourne la liste dédupliquée et triée des error_types pour une session."""
    types: set[str] = set()
    for q in questions:
        if not q.get("user_verified") or q.get("user_correct"):
            continue
        types.add(_classify_question_error(q, session_score_pct))
    return sorted(types)


def _parse_answer_states(answer_states: dict) -> tuple[int, int]:
    """
    Extrait (correct, wrong) depuis answer_states de training_sessions.
    Structure : {question_uuid: {correct: bool, verified: bool, ...}}
    """
    if not isinstance(answer_states, dict):
        return 0, 0
    verified = [v for v in answer_states.values()
                if isinstance(v, dict) and v.get("verified")]
    correct = sum(1 for v in verified if v.get("correct"))
    wrong   = len(verified) - correct
    return correct, wrong


def _build_weak_points_from_questions(questions: list[dict], item_number: str, course_title: str) -> list[dict]:
    """
    Génère des weak_points pour chaque question répondue incorrectement.
    Chaque weak_point contient le texte de la question + les propositions correctes.
    """
    weak_points = []
    category = f"Item {item_number}" if item_number else course_title

    for q in questions:
        if not q.get("user_verified") or q.get("user_correct"):
            continue  # Saute les non-répondues et les correctes

        question_text = (q.get("question_text") or "").strip()
        if not question_text:
            continue

        props = q.get("propositions") or []
        correct_labels = sorted([p["label"] for p in props if p.get("is_correct") and p.get("label")])
        selected_labels = sorted([p["label"] for p in props if p.get("was_selected") and p.get("label")])

        # Texte court de la question (150 chars max)
        detail = question_text[:150]
        if len(question_text) > 150:
            detail += "…"

        suffix_parts = []
        if correct_labels:
            suffix_parts.append(f"Correct: {', '.join(correct_labels)}")
        if selected_labels:
            suffix_parts.append(f"Choisi: {', '.join(selected_labels)}")
        if suffix_parts:
            detail += " | " + " — ".join(suffix_parts)

        weak_points.append({
            "category": category,
            "detail":   detail,
            "severity": 2,
        })

    return weak_points


def extract_sessions_ednpro(data: dict | list) -> list[dict]:
    """
    Transforme la réponse API EDN Pro (Supabase/PostgREST) en sessions Synapse.

    Supabase retourne toujours une liste d'objets directement.
    Les champs _course_name, _item_number et _questions sont ajoutés par
    SupabaseFetcher.fetch_training_sessions().
    """
    sessions = []
    items = data if isinstance(data, list) else _unwrap(data)

    for item in items:
        if not isinstance(item, dict):
            continue

        # Filtre : sessions complétées seulement
        if item.get("completed") is False:
            continue

        # ── Champs enrichis (ajoutés par fetch_training_sessions) ──────────
        course_title = item.get("_course_name") or ""
        item_number  = item.get("_item_number") or ""

        # Fallback : label de la session (ex: "Session matière (5 obj.)")
        if not course_title:
            course_title = item.get("label") or item.get("course_title") or item.get("name") or ""

        # ── Score depuis training_sessions ──────────────────────────────────
        total   = item.get("total_questions")
        correct = item.get("score")  # = nb réponses correctes dans training_sessions
        wrong   = None

        # Affinage via answer_states si disponible
        ans = item.get("answer_states")
        if isinstance(ans, dict) and ans:
            c2, w2 = _parse_answer_states(ans)
            if c2 or w2:
                correct = c2
                wrong   = w2
                if total is None:
                    total = c2 + w2

        pct = _to_float(correct, total)
        raw = _to_score_raw(correct, total)

        # ── Dates ────────────────────────────────────────────────────────────
        completed_at = item.get("completed_at") or item.get("started_at") or item.get("created_at")

        # ── Type de session ──────────────────────────────────────────────────
        # Extrait depuis resume_path types=qcm%2Cqre%2Cqroc
        import re as _re
        resume = item.get("resume_path") or ""
        types_match = _re.search(r"types=([^&]+)", resume)
        if types_match:
            types_str = types_match.group(1).replace("%2C", ",").upper()
            session_type = types_str.split(",")[0]  # premier type
        else:
            session_type = "QCM"

        sessions.append({
            "course_title":    str(course_title),
            "item_number":     str(item_number),
            "score_raw":       str(raw) if raw else "",
            "score_percent":   pct,
            "total_questions": int(total) if total is not None else None,
            "correct_answers": int(correct) if correct is not None else None,
            "wrong_answers":   int(wrong) if wrong is not None else None,
            "date":            _to_date_str(completed_at),
            "session_type":    session_type,
            "error_types":     [],
            "weak_points":     [],
            "questions":       [],
            "comments":        "",
        })

    return sessions


# ── Dispatch principal ─────────────────────────────────────────────────────────

def extract_sessions(platform: str, data: dict | list) -> list[dict]:
    if platform == "Hypocampus":
        return extract_sessions_hypocampus(data)
    if platform in ("EDNpro", "EDN Pro"):
        return extract_sessions_ednpro(data)
    raise ValueError(f"Plateforme non supportée : {platform}")


# ── Utilitaire ─────────────────────────────────────────────────────────────────

def _unwrap(data: dict | list) -> list:
    """Extrait la liste d'items depuis dict ou list."""
    if isinstance(data, list):
        return data
    # Cherche la première valeur qui est une liste (sessions/results/data/items...)
    for key in ("sessions", "results", "data", "items", "quizzes", "history",
                "quiz_sessions", "quiz-sessions"):
        if key in data and isinstance(data[key], list):
            return data[key]
    # Si le dict est un seul objet, le traite comme une liste à un élément
    return [data]
