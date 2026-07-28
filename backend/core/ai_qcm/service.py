"""
ai_qcm/service.py — Synapse
----------------------------
Import des fichiers markdown ChatGPT/Gemini dans la base SQLite.

Workflow :
  1. Scanne data/ai_qcm/ pour les fichiers .md à importer
  2. Parse chaque fichier (parser.py)
  3. Mappe course_id depuis DataStore (item_number → titre fuzzy)
  4. Insère dans qcm_sessions + weak_points
  5. Déplace vers data/ai_qcm/imported/

Appelé depuis le bouton "Importer IA" de la page QCM.
"""
from __future__ import annotations

import difflib
import time
from pathlib import Path
from typing import Optional
from loguru import logger

from backend.core.qcm.items_mapping import item_title

from backend.core.ai_qcm.parser import parse_file, ParseError, AIQCMFile
from backend.core.reviews import local_store
from backend.core.qcm.service import QCM_PASS_THRESHOLD
from backend.core.evaluation.models import EvaluationInput
from backend.core.evaluation.service import record_evaluation

_ROOT = Path(__file__).parent.parent.parent.parent
INBOX_DIR    = _ROOT / "data" / "ai_qcm"
IMPORTED_DIR = INBOX_DIR / "imported"


def ensure_dirs() -> None:
    INBOX_DIR.mkdir(parents=True, exist_ok=True)
    IMPORTED_DIR.mkdir(parents=True, exist_ok=True)


# ── Matching course ───────────────────────────────────────────────────────────

def _find_course(item_number: str, course_title: str, courses: list) -> tuple[str, str, str]:
    """
    Retourne (course_id, resolved_title, resolved_item).

    Priorité : item_number exact → titre exact → titre partiel → fuzzy (fuzzywuzzy).
    Si aucun match, retourne ("", course_title, item_number).
    """
    if not courses:
        return "", course_title, item_number

    # 1. Match par item_number — collecte tous les matchs, choisit le plus canonique
    if item_number:
        try:
            clean = str(int(float(item_number.strip())))
        except (ValueError, OverflowError):
            clean = item_number.strip().lstrip("0")

        matches = []
        for c in courses:
            raw_c = str(getattr(c, "item_number", "") or "").strip()
            try:
                c_item = str(int(float(raw_c)))
            except (ValueError, OverflowError):
                c_item = raw_c.lstrip("0")
            if c_item and c_item == clean:
                matches.append(c)

        if matches:
            if len(matches) == 1:
                best = matches[0]
            else:
                canonical = item_title(clean)
                def _score(c: object) -> float:
                    t = (getattr(c, "title", "") or "").lower().strip()
                    if not canonical:
                        return float(len(t))
                    return difflib.SequenceMatcher(None, t, canonical.lower().strip()).ratio()
                best = max(matches, key=_score)
            return best.id, best.title, str(getattr(best, "item_number", "") or "")

    # 2. Match par titre exact
    if course_title:
        q_lower = course_title.lower().strip()
        for c in courses:
            if str(getattr(c, "title", "") or "").lower().strip() == q_lower:
                return c.id, c.title, str(getattr(c, "item_number", "") or "")

        # 3. Match partiel
        for c in courses:
            c_title = str(getattr(c, "title", "") or "").lower().strip()
            if q_lower in c_title or c_title in q_lower:
                return c.id, c.title, str(getattr(c, "item_number", "") or "")

        # 4. Fuzzy
        try:
            from fuzzywuzzy import process as fw
            titles = [str(getattr(c, "title", "") or "") for c in courses]
            best, score = fw.extractOne(course_title, titles)
            if score >= 75:
                c = courses[titles.index(best)]
                return c.id, c.title, str(getattr(c, "item_number", "") or "")
        except Exception:
            pass

    return "", course_title, item_number


# ── Import d'un fichier ───────────────────────────────────────────────────────

def import_file(file_path: Path, courses: Optional[list] = None) -> dict:
    """
    Importe un fichier markdown dans SQLite.

    Retourne {success, file, imported, skipped, failed_count, errors}.
    Les lacunes ne sont JAMAIS créées automatiquement : c'est toujours
    l'utilisateur qui décide via la dialog dans l'UI.
    """
    result: dict = {
        "success":      False,
        "file":         file_path.name,
        "imported":     0,
        "skipped":      0,          # sessions déjà présentes en DB (doublons)
        "failed_count": 0,          # sessions avec score < seuil (info pour l'UI)
        "raw_sessions": [],         # données brutes pour proposition de lacunes
        "errors":       [],
    }

    try:
        qcm_file = parse_file(file_path)
    except ParseError as e:
        result["errors"].append(str(e))
        logger.warning(f"AI QCM parse: {e}")
        return result

    for session in qcm_file.sessions:
        try:
            course_id, resolved_title, resolved_item = _find_course(
                session.item_number, session.course_title, courses or []
            )

            # ── Déduplication : ignorer les sessions déjà en base ────────────
            if local_store.qcm_session_exists(
                platform=qcm_file.platform,
                session_date=qcm_file.date,
                course_title=resolved_title or session.course_title,
                score_percent=session.score_percent,
            ):
                result["skipped"] += 1
                logger.debug(
                    f"AI QCM : doublon ignoré — {session.course_title} "
                    f"({session.score_percent}% · {qcm_file.date})"
                )
                continue

            final_title  = resolved_title or session.course_title
            final_item   = resolved_item or session.item_number

            session_id = record_evaluation(EvaluationInput(
                source="qcm",
                platform=qcm_file.platform,
                session_date=qcm_file.date,
                course_id=course_id,
                course_title=final_title,
                item_number=final_item,
                session_type=qcm_file.session_type,
                score_raw=session.score_raw,
                score_percent=session.score_percent,
                total_questions=session.total_questions,
                correct_answers=session.correct_answers,
                wrong_answers=session.wrong_answers,
                difficulty=session.difficulty,
                error_types=tuple(session.error_types),
                detail=session.comments,
            )).persisted_id
            result["imported"] += 1

            pct = session.score_percent
            if pct is not None and pct < QCM_PASS_THRESHOLD:
                result["failed_count"] += 1

            # Données brutes exposées à l'UI pour proposition de lacunes
            result["raw_sessions"].append({
                "session_id":   session_id,
                "course_id":    course_id,
                "course_title": final_title,
                "item_number":  final_item,
                "weak_points":  session.weak_points,  # list[WeakPointEntry]
                "score_percent": pct,
            })

        except Exception as exc:
            msg = f"Session '{session.course_title}': {exc}"
            result["errors"].append(msg)
            logger.warning(f"AI QCM import: {msg}")

    if result["imported"] > 0 or result["skipped"] > 0:
        if result["imported"] > 0:
            dest = IMPORTED_DIR / file_path.name
            if dest.exists():
                dest = IMPORTED_DIR / f"{file_path.stem}_{int(time.time())}.md"
            file_path.rename(dest)
            result["success"] = True
        elif result["skipped"] > 0:
            # Toutes les sessions étaient des doublons : déplacer quand même
            dest = IMPORTED_DIR / file_path.name
            if dest.exists():
                dest = IMPORTED_DIR / f"{file_path.stem}_{int(time.time())}.md"
            file_path.rename(dest)
            result["success"] = True

        logger.success(
            f"AI QCM : {file_path.name} → "
            f"{result['imported']} importée(s), {result['skipped']} doublon(s) ignoré(s)"
        )

    return result


# ── Import global ─────────────────────────────────────────────────────────────

def import_all(courses: Optional[list] = None) -> dict:
    """
    Importe tous les fichiers .md en attente dans data/ai_qcm/.

    Retourne {files_found, files_imported, total_sessions, total_weak_points, errors}.
    """
    ensure_dirs()
    files = [p for p in sorted(INBOX_DIR.glob("*.md")) if _is_synapse_qcm(p)]

    summary: dict = {
        "files_found":    len(files),
        "files_imported": 0,
        "total_sessions": 0,
        "total_skipped":  0,
        "total_failed":   0,
        "raw_sessions":   [],  # agrégé depuis chaque fichier — pour dialog lacunes
        "errors":         [],
    }

    for f in files:
        res = import_file(f, courses=courses)
        if res["success"]:
            summary["files_imported"] += 1
        summary["total_sessions"] += res["imported"]
        summary["total_skipped"]  += res.get("skipped", 0)
        summary["total_failed"]   += res.get("failed_count", 0)
        summary["raw_sessions"].extend(res.get("raw_sessions", []))
        summary["errors"].extend(res["errors"])

    return summary


def _is_synapse_qcm(path: Path) -> bool:
    """
    Vrai si le fichier commence par un bloc ---json valide.
    Un fichier QCM généré par ChatGPT/Gemini a ---json sur l'une des 3 premières lignes.
    utf-8-sig pour absorber le BOM (\xef\xbb\xbf) qu'ajoutent certains éditeurs/exports.
    """
    try:
        first = path.read_text(encoding="utf-8-sig", errors="ignore")[:200]
        first_lines = first.splitlines()[:5]
        return any(line.strip() == "---json" for line in first_lines)
    except Exception:
        return False


def get_inbox_count() -> int:
    """Nombre de fichiers .md AI-QCM en attente dans data/ai_qcm/."""
    ensure_dirs()
    return sum(1 for p in INBOX_DIR.glob("*.md") if _is_synapse_qcm(p))
