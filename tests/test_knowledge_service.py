"""Tests unitaires — knowledge.service (graine, preuves, couverture OIC)."""
import datetime
import pytest
from types import SimpleNamespace

from backend.core.knowledge.models import SEED_FLOOR, RANG_A_BADGE_THRESHOLD


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    import backend.core.reviews.local_store as ls
    import backend.core.knowledge.store as ks

    test_db = tmp_path / "test.db"
    monkeypatch.setattr(ls, "DB_PATH", test_db)
    monkeypatch.setattr(ls, "_DB", None)
    ls.init_db()
    ks.init_knowledge_tables()
    yield
    if ls._DB is not None:
        ls._DB.close()
    monkeypatch.setattr(ls, "_DB", None)


import backend.core.reviews.local_store as ls
import backend.core.knowledge.store as ks
import backend.core.knowledge.service as ksv


def _declare_at(course_id: str, level: str, days_ago: int) -> None:
    """Déclare un item avec une declared_at rétrodatée."""
    ks.set_item_state(course_id, level)
    past = (datetime.date.today() - datetime.timedelta(days=days_ago)).isoformat()
    with ls._conn() as con:
        con.execute(
            "UPDATE item_state SET declared_at = ? WHERE course_id = ?", (past, course_id)
        )


def _seed_oics(course_id: str, rangs: list[str]) -> list[int]:
    ls.upsert_lisa_oic(course_id, [
        {"oic_code": f"OIC-{i}", "intitule": f"Objectif {i}", "rang": r,
         "rubrique": "Définition", "ordre": i}
        for i, r in enumerate(rangs)
    ])
    return [o["id"] for o in ls.get_lisa_oic(course_id)]


# ── Graine ────────────────────────────────────────────────────────────────────

def test_item_non_declare_na_pas_de_graine():
    snap = ksv.get_seed_snapshot("course-1")
    assert snap.declared_level is None
    assert snap.seed_score is None
    assert snap.n_evidence == 0


def test_item_declare_sans_preuve_a_sa_graine_nominale():
    ks.set_item_state("course-1", "solide")
    snap = ksv.get_seed_snapshot("course-1")
    assert snap.declared_level == "solide"
    assert snap.seed_score == 70
    assert snap.n_evidence == 0


def test_la_graine_se_degrade_avec_le_temps_ecoule():
    _declare_at("course-1", "solide", days_ago=90)
    assert ksv.get_seed_snapshot("course-1").seed_score == 64


def test_la_graine_dun_item_tres_ancien_atteint_le_plancher():
    _declare_at("course-1", "solide", days_ago=365 * 3)
    assert ksv.get_seed_snapshot("course-1").seed_score == SEED_FLOOR


# ── Preuves ───────────────────────────────────────────────────────────────────

def test_une_session_compte_comme_une_preuve():
    ks.set_item_state("course-1", "solide")
    ls.add_study_session(course_id="course-1", activity_types=["révision"])
    assert ksv.get_seed_snapshot("course-1").n_evidence == 1


def test_la_degradation_gele_a_la_date_de_la_premiere_preuve():
    """Une preuve réelle arrête l'horloge : au-delà, c'est l'évidence qui pilote."""
    _declare_at("course-1", "solide", days_ago=90)
    ls.add_study_session(course_id="course-1", activity_types=["révision"])

    snap = ksv.get_seed_snapshot("course-1")
    # La session est d'aujourd'hui → until = aujourd'hui → 90 j de dégradation.
    # Le test vérifie surtout que first_evidence_date est bien pris en compte.
    assert ksv.first_evidence_date("course-1") == datetime.date.today()
    assert snap.seed_score == 64


def test_une_tentative_oic_compte_comme_une_preuve():
    ks.set_item_state("course-1", "solide")
    oic_ids = _seed_oics("course-1", ["A"])
    ls.save_oic_attempt(oic_ids[0], 40, "[]")
    assert ksv.get_seed_snapshot("course-1").n_evidence == 1


def test_les_aliases_partagent_les_preuves_et_anki(monkeypatch):
    """Une preuve portée par une fiche sœur doit diluer la même graine."""
    from types import SimpleNamespace
    from backend.state.store import data_store

    first = SimpleNamespace(id="course-1", item_number="357")
    second = SimpleNamespace(id="course-2", item_number="357")
    monkeypatch.setattr(data_store, "cours", [first, second])
    data_store._alias_map = None
    data_store._alias_signature = -1
    ks.set_item_state("course-1", "solide")
    ls.add_study_session(course_id="course-2", activity_types=["révision"])
    ls.record_anki_review(
        card_id=1, note_id=2, item_numbers=("357",), rating="good",
        reviewed_at=datetime.datetime.now(datetime.timezone.utc), interval=3,
        source_review_id="review-1",
    )

    assert ksv.count_evidence("course-1") == 2
    assert ksv.count_evidence("course-2") == 2
    assert ksv.get_seed_snapshot("course-1").n_evidence == 2


# ── Couverture OIC ────────────────────────────────────────────────────────────

def test_couverture_oic_vide_pour_un_cours_sans_oic():
    cov = ksv.oic_coverage("course-1")
    assert cov["rang_a_total"] == 0
    assert cov["rang_a_pct"] == 0.0
    assert ksv.has_rang_a_badge("course-1") is False


def test_couverture_rang_a_compte_les_oic_reussis():
    oic_ids = _seed_oics("course-1", ["A", "A", "A", "A", "B"])
    for oid in oic_ids[:4]:
        ls.save_oic_attempt(oid, 90, "[]")   # 4 rang A réussis sur 4

    cov = ksv.oic_coverage("course-1")
    assert cov["rang_a_total"] == 4
    assert cov["rang_a_ok"] == 4
    assert cov["rang_a_pct"] == 1.0
    assert cov["rang_b_total"] == 1
    assert cov["rang_b_ok"] == 0


def test_le_badge_rang_a_se_declenche_au_seuil():
    oic_ids = _seed_oics("course-1", ["A"] * 5)
    for oid in oic_ids[:4]:
        ls.save_oic_attempt(oid, 90, "[]")   # 4/5 = 80 %

    assert ksv.oic_coverage("course-1")["rang_a_pct"] >= RANG_A_BADGE_THRESHOLD
    assert ksv.has_rang_a_badge("course-1") is True


def test_oic_coverage_accepts_all_sibling_fiche_ids():
    _seed_oics("course-1", ["A"])
    _seed_oics("course-2", ["A"])

    cov = ksv.oic_coverage(["course-1", "course-2"])

    assert cov["rang_a_total"] == 2


def test_le_badge_rang_a_ne_se_declenche_pas_sous_le_seuil():
    oic_ids = _seed_oics("course-1", ["A"] * 5)
    for oid in oic_ids[:3]:
        ls.save_oic_attempt(oid, 90, "[]")   # 3/5 = 60 %
    assert ksv.has_rang_a_badge("course-1") is False


def test_le_rang_b_ne_declenche_jamais_le_badge():
    oic_ids = _seed_oics("course-1", ["B", "B", "B"])
    for oid in oic_ids:
        ls.save_oic_attempt(oid, 100, "[]")
    assert ksv.has_rang_a_badge("course-1") is False


# ── Triage ────────────────────────────────────────────────────────────────────

def test_un_item_dun_college_valide_non_declare_est_a_situer():
    ks.set_college_status("Cardiovasculaire ❤️", "valide")
    assert ksv.is_to_situate("course-1", ["Cardiovasculaire ❤️"]) is True


def test_un_item_declare_nest_plus_a_situer():
    ks.set_college_status("Cardiovasculaire ❤️", "valide")
    ks.set_item_state("course-1", "correct")
    assert ksv.is_to_situate("course-1", ["Cardiovasculaire ❤️"]) is False


def test_un_item_dun_college_non_valide_nest_pas_a_situer():
    assert ksv.is_to_situate("course-1", ["Cardiovasculaire ❤️"]) is False


def test_declare_college_items_declares_only_the_undeclared():
    """Valider un collège n'écrivait jamais `item_state` : aucun de ses items
    ne devenait éligible au score ni à la consolidation automatique."""
    ks.set_item_state("course-2", "solide")

    declared = ksv.declare_college_items(["course-1", "course-2", "course-3"], level="correct")

    assert declared == 2
    assert ks.get_item_state("course-1").declared_level == "correct"
    assert ks.get_item_state("course-2").declared_level == "solide"  # inchangé
    assert ks.get_item_state("course-3").declared_level == "correct"


def test_declare_college_items_is_idempotent():
    ksv.declare_college_items(["course-1"], level="correct")

    assert ksv.declare_college_items(["course-1"], level="correct") == 0


def test_avancement_du_triage():
    ks.set_item_state("course-1", "solide")
    ks.set_item_state("course-2", "flou")
    situes, total = ksv.college_triage_progress(
        "Cardiovasculaire ❤️", ["course-1", "course-2", "course-3"]
    )
    assert (situes, total) == (2, 3)


def test_historically_completed_requires_validated_college_and_item_state():
    ks.set_college_status("Cardiovasculaire ❤️", "valide")
    ks.set_college_status("Dermatologie 🧴", "en_cours")
    ks.set_item_state("course-1", "correct")

    courses = [
        SimpleNamespace(id="course-1", college=["Cardiovasculaire ❤️"]),
        SimpleNamespace(id="course-2", college=["Cardiovasculaire ❤️"]),
        SimpleNamespace(id="course-3", college=["Dermatologie 🧴"]),
    ]

    assert ksv.get_historically_completed_course_ids(courses) == {"course-1"}
