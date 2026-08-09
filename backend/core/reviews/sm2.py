"""
SM-2 modifié pour Synapse.

Différences vs SM-2 classique :
  - Grade 1..5 (confidence UI) converti en 0..4 (SM-2 grade)
  - critical_trap : intervalle max de 7 jours même en cas de réussite
  - recurrent_trap : ef_penalty -0.15 supplémentaire
"""
from __future__ import annotations

SM2_MIN_EF: float = 1.3
SM2_INIT_EF: float = 2.5


def compute_next_interval(
    current_interval_days: int,
    confidence: int,           # 1..5 (grade utilisateur Synapse)
    easiness_factor: float = SM2_INIT_EF,
    repetition: int = 0,
    critical_trap: bool = False,   # weak_point.severity >= 4
    recurrent_trap: bool = False,  # weak_points.recurrence_count > 1
) -> tuple[int, float]:
    """
    Calcule le prochain intervalle SM-2 et le nouvel easiness factor.

    Retourne (next_interval_days, new_ef).
    """
    grade = max(0, min(4, confidence - 1))   # 1..5 → 0..4

    if recurrent_trap:
        easiness_factor = max(SM2_MIN_EF, easiness_factor - 0.15)

    if grade < 2:   # confidence 1 ou 2 — raté; 3 est une réussite faible
        new_ef = max(SM2_MIN_EF, easiness_factor - 0.2)
        next_interval = 1 if critical_trap else 3
        return next_interval, round(new_ef, 4)

    # Réussi — formule SM-2 standard
    new_ef = max(SM2_MIN_EF, easiness_factor + 0.1 - (4 - grade) * 0.08)

    if critical_trap:
        next_interval = int(min(round(current_interval_days * new_ef), 7))
    elif repetition == 0:
        next_interval = 3
    elif repetition == 1:
        next_interval = 7
    else:
        next_interval = round(current_interval_days * new_ef)

    return int(max(1, next_interval)), round(new_ef, 4)
