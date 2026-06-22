"""
ExternatService — Synapse Phase G
------------------------------------
Fournit :
  - get_active_stage()        : stage en cours ou None
  - apply_stage_boost(tasks)  : boost léger sur les tâches du collège du stage
  - get_stage_courses(stage)  : cours liés au collège du stage
  - get_stage_lacunes(stage)  : lacunes liées au collège du stage

Règle fondamentale :
  Le boost ne peut PAS écraser un retard critique.
  → on ne booste que les tâches avec days_overdue ≤ 3.
  → valeur du boost : STAGE_BOOST = 5.0 (inférieur à l'impact d'un J30 en retard).
"""
from __future__ import annotations

from typing import Optional, TYPE_CHECKING

from loguru import logger

from backend.core.externat import store as _store
from backend.core.externat.models import Stage

if TYPE_CHECKING:
    from backend.core.reviews.models import ReviewTask


# ── Constante de boost ────────────────────────────────────────────────────────

STAGE_BOOST = 5.0        # points ajoutés au priority_score
BOOST_MAX_OVERDUE = 3    # jours de retard max pour appliquer le boost


class ExternatService:
    """
    Service pour le mode externat.
    Lecture seule du store — les mutations passent directement par externat.store.
    """

    # ── Stage actif ───────────────────────────────────────────────────────────

    def get_active_stage(self) -> Optional[Stage]:
        """
        Retourne le stage actuellement en cours (dates + is_active).
        Retourne None si aucun stage n'est configuré ou en cours.
        """
        return _store.get_active_stage()

    # ── Boost priorité ────────────────────────────────────────────────────────

    def apply_stage_boost(
        self,
        tasks: list["ReviewTask"],
        stage: Optional[Stage] = None,
    ) -> list["ReviewTask"]:
        """
        Ajoute STAGE_BOOST au priority_score des tâches dont le collège
        correspond au stage actif, SAUF les tâches très en retard
        (déjà propulsées au top par leur score naturel).

        La liste est re-triée par priority_score décroissant.
        """
        if stage is None:
            stage = self.get_active_stage()

        if not stage or not stage.college_notion:
            return tasks

        college = stage.college_notion
        boosted: list["ReviewTask"] = []

        for t in tasks:
            if college in (t.college or []) and t.days_overdue <= BOOST_MAX_OVERDUE:
                # Pydantic BaseModel → copy avec update
                t = t.copy(update={"priority_score": t.priority_score + STAGE_BOOST})
                logger.debug(
                    f"Stage boost +{STAGE_BOOST} → {t.course_title} ({t.review_type})"
                )
            boosted.append(t)

        boosted.sort(key=lambda x: -x.priority_score)
        return boosted

    # ── Cours du stage ────────────────────────────────────────────────────────

    def get_stage_courses(self, stage: Stage) -> list:
        """
        Retourne les cours de data_store appartenant au collège du stage.
        Triés par : date_1ere_lecture desc (les plus récents d'abord).
        """
        from backend.state.store import data_store

        if not stage.college_notion:
            return []

        courses = [
            c for c in data_store.cours
            if stage.college_notion in (c.college or [])
        ]
        # Trier : cours les plus récemment lus d'abord, non lus à la fin
        def _sort_key(c):
            d = getattr(c, "date_1ere_lecture", None)
            return d.isoformat() if d else ""

        courses.sort(key=_sort_key, reverse=True)
        return courses

    # ── Lacunes du stage ──────────────────────────────────────────────────────

    def get_stage_lacunes(self, stage: Stage) -> list:
        """
        Retourne les lacunes actives dont le cours appartient au collège du stage.
        """
        from backend.core.reviews.local_store import get_all_weak_points_table

        if not stage.college_notion:
            return []

        stage_courses = {c.id for c in self.get_stage_courses(stage)}
        all_lacunes = get_all_weak_points_table(status_filter=None)

        return [
            lc for lc in all_lacunes
            if lc["course_id"] in stage_courses
            and (lc["status"] or "").lower() not in ("résolue",)
        ]

    # ── QCM du stage ─────────────────────────────────────────────────────────

    def get_stage_qcm(self, stage: Stage) -> list:
        """
        Retourne les résultats QCM récents liés aux cours du stage.
        """
        from backend.core.reviews.local_store import _conn

        if not stage.college_notion:
            return []

        stage_course_ids = {c.id for c in self.get_stage_courses(stage)}
        if not stage_course_ids:
            return []

        placeholders = ",".join("?" * len(stage_course_ids))
        with _conn() as con:
            rows = con.execute(
                f"""
                SELECT * FROM qcm_sessions
                WHERE course_id IN ({placeholders})
                ORDER BY session_date DESC
                LIMIT 50
                """,
                list(stage_course_ids),
            ).fetchall()
        return rows


# ── Singleton ─────────────────────────────────────────────────────────────────

externat_service = ExternatService()
