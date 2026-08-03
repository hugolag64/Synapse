"""
ReviewService — Synapse
-----------------------
Génère les ReviewTask virtuelles à partir de data_store.cours,
enrichies par l'historique SQLite local (local_store).

Architecture :
    data_store.cours          →  _build_tasks(context)  →  List[ReviewTask]
                                         ↓
                               local_store.get_all_history()
                                         ↓
                               apply_history()          →  statuts done/postponed/ignored
                                         ↓
                    get_urgent / get_today / get_bonus   →  Dashboard
"""

from datetime import date, timedelta
from typing import List, Optional
from loguru import logger

from backend.core.reviews.models import ReviewTask, ReviewContext
from backend.core.reviews.local_store import (
    make_task_id, get_all_history, get_sessions_by_course, get_postpone_counts,
    get_qcm_done_course_ids, get_sm2_effective_date, get_all_review_data,
    get_all_sm2_effective_dates,
)
from backend.core.reviews.mastery import get_course_mastery, CourseProgressSnapshot


# ── Constantes ────────────────────────────────────────────────────────────────

REVIEW_OFFSETS: dict[str, int] = {
    "J3":  3,
    "J7":  7,
    "J14": 14,
    "J30": 30,
}

# Horizon futur maximal affiché (évite de noyer le dashboard de tâches lointaines)
FUTURE_HORIZON_DAYS = 30

# Statuts SQLite qui masquent une tâche du dashboard
_HIDDEN_STATUSES = {"done", "ignored", "cancelled"}


class ReviewService:
    """
    Génère et classe les ReviewTask virtuelles.

    Principe :
      1. Pour chaque cours, générer les tâches J3/J7/J14/J30 (college ET/OU ue).
      2. Utiliser les dates Notion (Lecture J3 collège…) si disponibles,
         sinon fallback = date_1ere_lecture + offset.
      3. Enrichir avec l'historique SQLite : masquer les done/ignored,
         déplacer les postponed à leur nouvelle date effective.
      4. Trier par priority_score décroissant.

    Cache : les résultats sont mémoïsés par (context, date du jour).
    Appeler invalidate_cache() après toute modification de cours ou action de révision.
    """

    def __init__(self):
        # {(context, date_iso): List[ReviewTask]}
        self._cache: dict[tuple[str, str], List[ReviewTask]] = {}
        # Mastery cache — invalidé chaque nouveau jour
        self._mastery_cache: dict[str, object] = {}
        self._mastery_cache_date: Optional[date] = None

    def invalidate_cache(self) -> None:
        """Vide le cache des ReviewTask et le cache mastery."""
        self._cache.clear()
        self._mastery_cache.clear()
        self._mastery_cache_date = None

    # ── API publique principale ───────────────────────────────────────────────

    def generate_reviews(
        self,
        context: ReviewContext = "college",
        history: Optional[dict] = None,
        sessions_map: Optional[dict] = None,
        postpone_map: Optional[dict] = None,
    ) -> List[ReviewTask]:
        """
        Génère toutes les tâches J3/J7/J14/J30 pour un contexte donné.

        Paramètres :
            context      : 'college' ou 'ue'
            history      : {task_id: Row} depuis get_all_history()
            sessions_map : {course_id: [rows]} depuis get_sessions_by_course()
            postpone_map : {course_id: int}   depuis get_postpone_counts()
        """
        from backend.state.store import data_store

        today = date.today()
        cache_key = (context, today.isoformat())

        # Retourner le cache si aucune donnée externe n'est passée (rendu UI standard)
        explicit_data = history is not None or sessions_map is not None or postpone_map is not None
        if not explicit_data and cache_key in self._cache:
            logger.debug(f"ReviewService [{context}]: cache hit.")
            return list(self._cache[cache_key])

        history      = history      or {}
        sessions_map = sessions_map or get_sessions_by_course()
        postpone_map = postpone_map or get_postpone_counts()
        qcm_done_set = get_qcm_done_course_ids()

        # F2 — Batch SM-2 : charge TOUTES les dates en une seule requête
        sm2_map = get_all_sm2_effective_dates()

        # F4 — Stage actif pour le boost de priorité
        active_stage = getattr(data_store, "active_stage", None)
        # F1 — Graphe sémantique
        semantic_graph = getattr(data_store, "semantic_graph", {})

        tasks: List[ReviewTask] = []
        cours_snapshot = list(data_store.cours)  # snapshot pour éviter les mutations concurrentes

        for c in cours_snapshot:
            date_ref = (
                c.date_1ere_lecture if context == "college" else c.date_1ere_lecture_ue
            )
            if not date_ref:
                continue

            mastery = self._get_mastery_cached(
                c,
                context,
                sessions_map.get(c.id, []),
                postpone_map.get(c.id, 0),
                (c.id in qcm_done_set),
            )

            # Ne pas générer de ReviewTask pour un cours non commencé (règle forte)
            if mastery.score is None:
                continue

            for review_type, offset in REVIEW_OFFSETS.items():
                # F2 — SM-2 : lookup dict au lieu d'une requête par cours
                _notion_d = self._get_notion_date(c, context, review_type)
                _sm2_d    = sm2_map.get((c.id, context, review_type)) if not _notion_d else None
                theoretical = _notion_d or _sm2_d or (date_ref + timedelta(days=offset))
                _date_src   = "notion" if _notion_d else ("sm2" if _sm2_d else "fixe")

                task_id = make_task_id(c.id, context, review_type, theoretical)

                row = history.get(task_id)
                status = row["status"] if row else "todo"

                if status in _HIDDEN_STATUSES:
                    continue

                if status == "postponed" and row and row["postponed_to"]:
                    effective = date.fromisoformat(row["postponed_to"])
                    postponed_count = row["postponed_count"] or 0
                else:
                    effective = theoretical
                    postponed_count = 0

                days_overdue = (today - effective).days

                if days_overdue < -FUTURE_HORIZON_DAYS:
                    continue

                score = self._calculate_priority(
                    c, effective, today, review_type, postponed_count, mastery,
                    active_stage=active_stage,
                    semantic_graph=semantic_graph,
                )

                tasks.append(ReviewTask(
                    id=task_id,
                    course_id=c.id,
                    course_title=c.title,
                    item_number=c.item_number or None,
                    college=list(c.college),
                    context=context,
                    url_pdf=c.url_pdf,
                    url_pdf_ue=c.url_pdf_ue,
                    agregation_fiche_edn=c.agregation_fiche_edn,
                    theoretical_due_date=theoretical,
                    due_date=effective,
                    review_type=review_type,
                    priority_score=score,
                    status=status,
                    nb_lectures=c.nb_lectures if context == "college" else c.nb_lectures_ue,
                    anki=getattr(c, "anki", False),
                    qcm_done=getattr(c, "qcm_done", False),
                    course_status=getattr(c, "course_status", "À lire"),
                    days_overdue=max(days_overdue, 0),
                    postponed_count=postponed_count,
                    mastery_score=mastery.score,
                    mastery_level=mastery.level,
                    mastery_reasons=mastery.reasons,
                    date_source=_date_src,
                ))

        # F1 — Boost graphe sémantique : +10 * max_weight si un voisin est critique
        if semantic_graph:
            mastery_map = {t.course_id: t.mastery_level for t in tasks}
            for task in tasks:
                neighbors = semantic_graph.get(task.course_id, [])
                critique_neighbors = [
                    n for n in neighbors
                    if mastery_map.get(n.target_id) == "critique"
                ]
                if critique_neighbors:
                    max_w = max(n.weight for n in critique_neighbors)
                    task.priority_score = round(task.priority_score + 10 * max_w, 1)

        tasks.sort(key=lambda t: -t.priority_score)
        logger.debug(f"ReviewService [{context}]: {len(tasks)} tâches générées.")

        # Mettre en cache uniquement si le calcul était "complet" (pas de données externes)
        if not explicit_data:
            self._cache[cache_key] = list(tasks)

        return tasks

    def get_unstarted_courses(self, context: ReviewContext = "college") -> List[CourseProgressSnapshot]:
        """
        Retourne la liste des cours qui sont soit 'à préparer' soit 'à lire',
        en utilisant le nouveau moteur Mastery.
        """
        from backend.state.store import data_store
        
        qcm_done_set = get_qcm_done_course_ids()
        unstarted = []
        
        for c in data_store.cours:
            mastery = get_course_mastery(
                c,
                context=context,
                qcm_done_local=(c.id in qcm_done_set)
            )
            if mastery.score is None:
                unstarted.append(mastery)
                
        return unstarted

    def generate_all_reviews(self, history: Optional[dict] = None) -> List[ReviewTask]:
        """
        Génère les tâches pour les DEUX contextes (college + ue).
        Dé-duplique par task_id (un cours peut avoir les deux).
        """
        if history is None:
            history, sessions_map, postpone_map, _ = get_all_review_data()
        else:
            sessions_map = get_sessions_by_course()
            postpone_map = get_postpone_counts()
        college = self.generate_reviews("college", history, sessions_map, postpone_map)
        ue      = self.generate_reviews("ue",      history, sessions_map, postpone_map)

        # Fusion sans doublon
        seen = set()
        merged = []
        for t in college + ue:
            if t.id not in seen:
                seen.add(t.id)
                merged.append(t)

        merged.sort(key=lambda t: -t.priority_score)
        return merged

    # ── Mastery cache ─────────────────────────────────────────────────────────

    def _get_mastery_cached(
        self, course, context: str, sessions: list, postpone_count: int, qcm_done: bool
    ) -> "CourseProgressSnapshot":
        today = date.today()
        if self._mastery_cache_date != today:
            self._mastery_cache.clear()
            self._mastery_cache_date = today

        key = f"{course.id}_{context}"
        if key not in self._mastery_cache:
            self._mastery_cache[key] = get_course_mastery(
                course, context, sessions, postpone_count, qcm_done
            )
        return self._mastery_cache[key]

    # ── Filtres ───────────────────────────────────────────────────────────────

    def get_urgent_tasks(self, all_tasks: List[ReviewTask]) -> List[ReviewTask]:
        """Tâches en retard (due_date < aujourd'hui)."""
        today = date.today()
        return [t for t in all_tasks if t.due_date < today]

    def get_urgent_course_ids(
        self,
        context: ReviewContext = "college",
        history: Optional[dict] = None,
    ) -> set[str]:
        """
        Retourne les course_id ayant au moins une révision J3/J7/J14/J30
        en retard et non traitée (ni done, ni reportée dans le futur, ni ignorée).
        """
        history = history if history is not None else get_all_history()
        tasks = self.generate_reviews(context, history=history)
        return {t.course_id for t in self.get_urgent_tasks(tasks)}

    def get_today_tasks(self, all_tasks: List[ReviewTask]) -> List[ReviewTask]:
        """Tâches prévues exactement aujourd'hui."""
        today = date.today()
        return [t for t in all_tasks if t.due_date == today]

    def get_upcoming_tasks(self, all_tasks: List[ReviewTask], days: int = 7) -> List[ReviewTask]:
        """Tâches dans les N prochains jours (hors aujourd'hui)."""
        today = date.today()
        horizon = today + timedelta(days=days)
        return [t for t in all_tasks if today < t.due_date <= horizon]

    def get_bonus_tasks(
        self,
        history: Optional[dict] = None,
        context: ReviewContext = "college",
    ) -> List[ReviewTask]:
        """
        Actions rapides : cours jamais lus, Fiche EDN absente, QCM non fait.
        Limité à 12 éléments.
        """
        from backend.state.store import data_store

        history = history or {}
        today = date.today()
        bonus: List[ReviewTask] = []

        for c in data_store.cours:
            task_id = make_task_id(c.id, context, "bonus", today)
            row = history.get(task_id)
            if row and row["status"] in _HIDDEN_STATUSES:
                continue

            nb = c.nb_lectures if context == "college" else c.nb_lectures_ue
            reasons = []
            score = 0.0

            if not c.agregation_fiche_edn:
                reasons.append("EDN manquante")
                score += 2.0
            if not getattr(c, "qcm_done", False):
                score += 1.0

            if not reasons:
                continue

            bonus.append(ReviewTask(
                id=task_id,
                course_id=c.id,
                course_title=c.title,
                item_number=c.item_number or None,
                college=list(c.college),
                context=context,
                url_pdf=c.url_pdf,
                url_pdf_ue=c.url_pdf_ue,
                agregation_fiche_edn=c.agregation_fiche_edn,
                theoretical_due_date=today,
                due_date=today,
                review_type="bonus",
                priority_score=score,
                status="todo",
                nb_lectures=nb,
                anki=getattr(c, "anki", False),
                qcm_done=getattr(c, "qcm_done", False),
                course_status=getattr(c, "course_status", "À lire"),
                days_overdue=0,
            ))

        bonus.sort(key=lambda t: -t.priority_score)
        return bonus[:12]

    # ── Helpers internes ──────────────────────────────────────────────────────

    def _get_notion_date(self, c, context: str, review_type: str):
        """
        Retourne la date Notion stockée (Lecture JX collège / Lecture JX UE)
        si elle existe, None sinon.
        """
        if context == "college":
            mapping = {
                "J3":  c.lecture_j3_college,
                "J7":  c.lecture_j7_college,
                "J14": c.lecture_j14_college,
                "J30": c.lecture_j30_college,
            }
        else:
            mapping = {
                "J3":  c.lecture_j3_ue,
                "J7":  c.lecture_j7_ue,
                "J14": c.lecture_j14_ue,
                "J30": c.lecture_j30_ue,
            }
        return mapping.get(review_type)

    def _calculate_priority(
        self,
        c,
        due_date: date,
        today: date,
        review_type: str,
        postponed_count: int = 0,
        mastery: Optional[CourseProgressSnapshot] = None,
        active_stage=None,
        semantic_graph: Optional[dict] = None,
    ) -> float:
        """
        Score de priorité (plus élevé = plus urgent).

          +5  par jour de retard (plafonné à 60)
          +10 si retard ≥ 2 jours
          +15 si J30 en retard
          +5  si 0 lecture
          +2  si fiche EDN absente
          +1  si QCM non fait
          +3  par report
          -5  si futur
          bonus maîtrise : critique +25 · fragile +15 · correct +5 · solide -10
          F4 ×1.5 si stage actif + même collège · ×1.2 si voisin same_college
        """
        days_overdue = (today - due_date).days
        score = 0.0

        if days_overdue > 0:
            score += min(days_overdue * 5, 60)
            if days_overdue >= 2:
                score += 10
            if review_type == "J30":
                score += 15
        else:
            score -= 5

        if c.nb_lectures == 0:
            score += 5
        if not c.agregation_fiche_edn:
            score += 2
        if not getattr(c, "qcm_done", False):
            score += 1

        score += postponed_count * 3

        if mastery:
            mastery_bonus = {
                "critique":        25,
                "fragile":         15,
                "en construction": 10,
                "à consolider":     5,
                "à entraîner":      0,
                "maîtrisé":       -10,
            }
            score += mastery_bonus.get(mastery.level, 0)
            
            # Boost "Sprint Rang A" : priorité absolue sur le socle indispensable non sécurisé
            if mastery.score_rang_a is not None and mastery.score_rang_a < 75:
                score += 35.0

        # F4 — Stage-Aware Boost
        if active_stage:
            if active_stage.college in (c.college or []):
                score *= active_stage.boost_factor
            elif semantic_graph:
                neighbors = semantic_graph.get(c.id, [])
                if any(n.edge_type == "same_college" for n in neighbors):
                    score *= 1.2

        return round(score, 1)


# ── Singleton ─────────────────────────────────────────────────────────────────
review_service = ReviewService()
