"""Tests unitaires — knowledge.models (graine, dégradation, fusion)."""
import datetime

from backend.core.knowledge.models import (
    SEED_SCORES, SEED_FLOOR, DECAY_PER_30D,
    decayed_seed, blend, level_from_seed,
)


def _d(y, m, d) -> datetime.date:
    return datetime.date(y, m, d)


# ── Dégradation ───────────────────────────────────────────────────────────────

def test_seed_le_jour_de_la_declaration_vaut_la_valeur_nominale():
    day = _d(2026, 7, 14)
    assert decayed_seed("solide", day, day) == 70
    assert decayed_seed("correct", day, day) == 50
    assert decayed_seed("flou", day, day) == 30


def test_seed_se_degrade_de_2_points_par_30_jours():
    start = _d(2026, 7, 14)
    assert decayed_seed("solide", start, start + datetime.timedelta(days=30)) == 68
    assert decayed_seed("solide", start, start + datetime.timedelta(days=90)) == 64


def test_seed_ne_descend_jamais_sous_le_plancher():
    start = _d(2020, 1, 1)
    assert decayed_seed("solide", start, _d(2026, 7, 14)) == SEED_FLOOR
    assert decayed_seed("flou", start, _d(2026, 7, 14)) == SEED_FLOOR


def test_seed_ignore_une_date_future_de_declaration():
    """Robustesse : une declared_at dans le futur ne doit pas gonfler la graine."""
    today = _d(2026, 7, 14)
    future = _d(2026, 12, 31)
    assert decayed_seed("correct", future, today) == SEED_SCORES["correct"]


# ── Fusion graine / évidence ──────────────────────────────────────────────────

def test_sans_preuve_la_graine_est_le_score():
    assert blend(seed=70, computed=40, n_evidence=0) == 70


def test_une_preuve_rend_la_graine_secondaire():
    # 0.25 * 70 + 0.75 * 40 = 47.5 → 48 (arrondi)
    assert blend(seed=70, computed=40, n_evidence=1) == 48


def test_trois_preuves_diluent_presque_entierement_la_graine():
    # 1/16 * 70 + 15/16 * 40 = 41.875 → 42 (arrondi)
    assert blend(seed=70, computed=40, n_evidence=3) == 42


def test_sans_graine_le_score_calcule_passe_tel_quel():
    assert blend(seed=None, computed=42, n_evidence=5) == 42


def test_sans_graine_ni_score_calcule_le_resultat_est_none():
    assert blend(seed=None, computed=None, n_evidence=0) is None


def test_graine_seule_sans_score_calcule():
    """Ancien item déclaré, jamais lu : le calculé est None, la graine survit."""
    assert blend(seed=50, computed=None, n_evidence=0) == 50


# ── Niveau depuis la graine ───────────────────────────────────────────────────

def test_level_from_seed_mappe_les_trois_crans():
    assert level_from_seed(SEED_SCORES["flou"]) == "critique"      # 30
    assert level_from_seed(SEED_SCORES["correct"]) == "fragile"    # 50
    assert level_from_seed(SEED_SCORES["solide"]) == "à consolider"  # 70
