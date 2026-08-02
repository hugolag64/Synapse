"""
knowledge.models — Synapse
--------------------------
Modèle d'état des connaissances : statut d'un collège, niveau déclaré d'un item,
et mathématiques de la « graine » de maîtrise.

Module pur : aucune I/O, aucune dépendance projet.

Principe : un niveau déclaré n'est pas un score, c'est un a priori qui s'efface.
  - il se dégrade avec le temps écoulé depuis la déclaration (decayed_seed) ;
  - il est dilué par les preuves réelles — sessions, QCM, évals OIC (blend).
"""
from __future__ import annotations

import datetime
from dataclasses import dataclass


# ── Constantes ────────────────────────────────────────────────────────────────

DECLARED_LEVELS: tuple[str, ...] = ("solide", "correct", "flou")
COLLEGE_STATUSES: tuple[str, ...] = ("non_etudie", "en_cours", "valide")

SEED_SCORES: dict[str, int] = {"solide": 70, "correct": 50, "flou": 30}

# Un « solide » atteint le plancher en ~22 mois, un « correct » en ~12 mois :
# l'horizon EDN (~2 ans) est couvert sans que rien ne stagne en haut de l'échelle.
DECAY_PER_30D: float = 2.0
SEED_FLOOR: int = 25

# Une tentative OIC à ce score ou au-dessus vaut réussite (passe mastered = 1).
OIC_SUCCESS_SCORE: int = 70

# Part d'OIC de rang A réussis à partir de laquelle le badge « Rang A ✓ » est acquis.
RANG_A_BADGE_THRESHOLD: float = 0.80


# ── Dataclasses ───────────────────────────────────────────────────────────────

@dataclass
class ItemState:
    course_id: str
    context: str                         # college | ue
    declared_level: str                  # solide | correct | flou
    declared_at: datetime.date
    source: str                          # triage | reprise
    updated_at: str


@dataclass
class SeedSnapshot:
    """Ce que mastery.py a besoin de savoir sur l'état déclaré d'un item."""
    declared_level: str | None
    seed_score: int | None
    n_evidence: int


# ── Mathématiques de la graine ────────────────────────────────────────────────

def decayed_seed(level: str, declared_at: datetime.date, until: datetime.date) -> int:
    """
    Graine dégradée : la valeur nominale du niveau, diminuée de DECAY_PER_30D
    points par tranche de 30 jours écoulés, avec un plancher à SEED_FLOOR.

    `until` est la date d'arrêt de la dégradation : la date de la première preuve
    réelle si elle existe, aujourd'hui sinon (cf. service.get_seed_snapshot).
    """
    base = SEED_SCORES.get(level)
    if base is None:
        raise ValueError(f"Niveau déclaré inconnu : {level!r}")

    elapsed_days = max(0, (until - declared_at).days)   # une date future ne gonfle rien
    decay = DECAY_PER_30D * (elapsed_days / 30.0)
    return max(SEED_FLOOR, int(round(base - decay)))


def blend(seed: int | None, computed: int | None, n_evidence: int) -> int | None:
    """
    Fusionne la graine et le score calculé par mastery.py.

    Le poids de la graine décroît avec le nombre de preuves réelles :
        0 preuve → 100 %, 1 → 50 %, 2 → 33 %, 3 → 25 %.
    La graine est diluée, jamais effacée brutalement.
    """
    if seed is None:
        return computed
    if computed is None:
        return seed

    w = 1.0 / (1.0 + max(0, n_evidence))
    return int(round(w * seed + (1.0 - w) * computed))


def level_from_seed(score: int) -> str:
    """
    Niveau affiché d'un item déclaré mais sans aucune preuve réelle.

    Utilise les noms de PROGRESSION_COLORS existants — on n'introduit pas de
    nouveau niveau dans l'échelle. Les trois crans atterrissent ainsi :
        flou (30) → critique · correct (50) → fragile · solide (70) → à consolider
    """
    if score < 40:
        return "critique"
    if score < 60:
        return "fragile"
    return "à consolider"
