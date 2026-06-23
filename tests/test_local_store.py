"""Tests unitaires — local_store SQLite (ReviewHistory)."""
import pytest
import datetime
import tempfile
import sqlite3
from pathlib import Path
from unittest.mock import patch


# ── Fixture : DB temporaire isolée pour chaque test ──────────────────────────

@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    """Chaque test utilise sa propre DB temporaire."""
    import backend.core.reviews.local_store as ls
    test_db = tmp_path / "test.db"
    monkeypatch.setattr(ls, "DB_PATH", test_db)
    # Reset la connexion module-level pour qu'elle utilise la nouvelle DB
    monkeypatch.setattr(ls, "_DB", None)
    ls.init_db()
    yield
    # Cleanup : fermer la connexion après le test
    if ls._DB is not None:
        ls._DB.close()
    monkeypatch.setattr(ls, "_DB", None)


import backend.core.reviews.local_store as ls


# ── Helpers ───────────────────────────────────────────────────────────────────

def _today() -> datetime.date:
    return datetime.date.today()

def _due(offset: int = 0) -> datetime.date:
    return _today() + datetime.timedelta(days=offset)


# ── Tests make_task_id ────────────────────────────────────────────────────────

class TestMakeTaskId:
    def test_format(self):
        tid = ls.make_task_id("abc-123", "college", "J7", datetime.date(2026, 5, 30))
        assert tid == "abc-123_college_J7_2026-05-30"

    def test_ue_context(self):
        tid = ls.make_task_id("abc-123", "ue", "J14", datetime.date(2026, 6, 1))
        assert "ue" in tid
        assert "J14" in tid

    def test_different_dates_different_ids(self):
        d1 = ls.make_task_id("x", "college", "J7", datetime.date(2026, 5, 1))
        d2 = ls.make_task_id("x", "college", "J7", datetime.date(2026, 6, 1))
        assert d1 != d2

    def test_different_contexts_different_ids(self):
        t1 = ls.make_task_id("x", "college", "J7", _due())
        t2 = ls.make_task_id("x", "ue", "J7", _due())
        assert t1 != t2


# ── Tests mark_done ───────────────────────────────────────────────────────────

class TestMarkDone:
    def test_creates_record(self):
        tid = ls.make_task_id("c1", "college", "J7", _due())
        ls.mark_done(tid, "c1", "college", "J7", _due(), course_title="Cardio")
        row = ls.get_history(tid)
        assert row is not None
        assert row["status"] == "done"

    def test_completed_at_is_datetime_iso(self):
        """completed_at doit être un datetime ISO (contient 'T'), pas juste une date."""
        tid = ls.make_task_id("c1", "college", "J7", _due())
        ls.mark_done(tid, "c1", "college", "J7", _due())
        row = ls.get_history(tid)
        today_str = datetime.date.today().isoformat()
        assert row["completed_at"].startswith(today_str), (
            f"completed_at={row['completed_at']!r} ne commence pas par {today_str}"
        )

    def test_idempotent(self):
        tid = ls.make_task_id("c1", "college", "J7", _due())
        ls.mark_done(tid, "c1", "college", "J7", _due())
        ls.mark_done(tid, "c1", "college", "J7", _due())
        row = ls.get_history(tid)
        assert row["status"] == "done"

    def test_done_appears_in_history(self):
        tid = ls.make_task_id("c1", "college", "J3", _due(-3))
        ls.mark_done(tid, "c1", "college", "J3", _due(-3))
        h = ls.get_all_history()
        assert tid in h


# ── Tests postpone ────────────────────────────────────────────────────────────

class TestPostpone:
    def test_creates_postponed_record(self):
        tid = ls.make_task_id("c1", "college", "J7", _due())
        tomorrow = _due(1)
        ls.postpone(tid, "c1", "college", "J7", _due(), tomorrow)
        row = ls.get_history(tid)
        assert row["status"] == "postponed"
        assert row["postponed_to"] == tomorrow.isoformat()

    def test_effective_due_date_updated(self):
        tid = ls.make_task_id("c1", "college", "J7", _due())
        next_week = _due(7)
        ls.postpone(tid, "c1", "college", "J7", _due(), next_week)
        row = ls.get_history(tid)
        assert row["effective_due_date"] == next_week.isoformat()

    def test_postponed_count_increments(self):
        tid = ls.make_task_id("c1", "college", "J7", _due())
        ls.postpone(tid, "c1", "college", "J7", _due(), _due(1))
        ls.postpone(tid, "c1", "college", "J7", _due(), _due(2))
        row = ls.get_history(tid)
        assert row["postponed_count"] == 2

    def test_theoretical_date_preserved(self):
        theoretical = _due(0)
        tid = ls.make_task_id("c1", "college", "J7", theoretical)
        ls.postpone(tid, "c1", "college", "J7", theoretical, _due(5))
        row = ls.get_history(tid)
        assert row["theoretical_due_date"] == theoretical.isoformat()


# ── Tests ignore ──────────────────────────────────────────────────────────────

class TestIgnore:
    def test_status_ignored(self):
        tid = ls.make_task_id("c1", "college", "J14", _due())
        ls.ignore(tid, "c1", "college", "J14", _due())
        row = ls.get_history(tid)
        assert row["status"] == "ignored"

    def test_ignored_in_all_history(self):
        tid = ls.make_task_id("c2", "ue", "J30", _due(-5))
        ls.ignore(tid, "c2", "ue", "J30", _due(-5))
        h = ls.get_all_history()
        assert tid in h
        assert h[tid]["status"] == "ignored"


# ── Tests postpone_count nettoyé à la validation ──────────────────────────────

class TestMarkDoneAfterPostpone:
    def test_postponed_to_cleared_on_done(self):
        tid = ls.make_task_id("c1", "college", "J7", _due())
        ls.postpone(tid, "c1", "college", "J7", _due(), _due(3))
        ls.mark_done(tid, "c1", "college", "J7", _due())
        row = ls.get_history(tid)
        assert row["status"] == "done"
        assert row["postponed_to"] is None


# ── Tests migrate_study_sessions_v2 ──────────────────────────────────────────

class TestMigrateStudySessions:
    def test_adds_columns_on_existing_db(self):
        """La migration doit fonctionner même si la table existe déjà sans les nouvelles colonnes."""
        ls.migrate_study_sessions_v2()  # idempotent
        with ls._conn() as con:
            cols = {r["name"] for r in con.execute("PRAGMA table_info(study_sessions)").fetchall()}
        for col in ("activity_types", "qcm_result", "weak_category", "weak_detail", "perceived_mastery"):
            assert col in cols, f"Colonne manquante : {col}"

    def test_migration_idempotent(self):
        ls.migrate_study_sessions_v2()
        ls.migrate_study_sessions_v2()  # ne doit pas lever d'exception


# ── Tests add_study_session ───────────────────────────────────────────────────

class TestAddStudySession:
    def test_inserts_row(self):
        ls.add_study_session("c1", course_title="Cardio", context="college")
        sessions = ls.get_sessions_by_course()
        assert "c1" in sessions
        assert len(sessions["c1"]) == 1

    def test_multiple_activity_types_stored_as_json(self):
        import json
        ls.add_study_session(
            "c1",
            activity_types=["révision", "qcm", "anki"],
            duration_minutes=30,
            confidence=4,
            difficulty="moyen",
        )
        sessions = ls.get_sessions_by_course()
        row = sessions["c1"][0]
        types = json.loads(row["activity_types"])
        assert "révision" in types
        assert "qcm" in types
        assert "anki" in types

    def test_session_type_compat(self):
        """session_type doit valoir le premier type de la liste (compat ancien champ)."""
        ls.add_study_session("c1", activity_types=["lecture", "fiche"])
        sessions = ls.get_sessions_by_course()
        assert sessions["c1"][0]["session_type"] == "lecture"

    def test_default_session_type(self):
        ls.add_study_session("c1")
        sessions = ls.get_sessions_by_course()
        assert sessions["c1"][0]["session_type"] == "révision"

    def test_qcm_result_stored(self):
        ls.add_study_session("c1", qcm_result="raté", weak_category="traitement")
        sessions = ls.get_sessions_by_course()
        row = sessions["c1"][0]
        assert row["qcm_result"] == "raté"
        assert row["weak_category"] == "traitement"

    def test_multiple_sessions_per_course(self):
        ls.add_study_session("c1", duration_minutes=10)
        ls.add_study_session("c1", duration_minutes=20)
        ls.add_study_session("c2", duration_minutes=30)
        sessions = ls.get_sessions_by_course()
        assert len(sessions["c1"]) == 2
        assert len(sessions["c2"]) == 1


# ── Tests get_postpone_counts ─────────────────────────────────────────────────

class TestGetPostponeCounts:
    def test_empty_returns_empty(self):
        assert ls.get_postpone_counts() == {}

    def test_counts_total_postponements(self):
        t1 = ls.make_task_id("c1", "college", "J7", _due())
        ls.postpone(t1, "c1", "college", "J7", _due(), _due(1))
        ls.postpone(t1, "c1", "college", "J7", _due(), _due(2))
        t2 = ls.make_task_id("c1", "college", "J14", _due(7))
        ls.postpone(t2, "c1", "college", "J14", _due(7), _due(8))
        counts = ls.get_postpone_counts()
        # t1 a postponed_count=2, t2 a postponed_count=1 → total pour c1 = 3
        assert counts.get("c1", 0) == 3


# ── Tests get_all_history ─────────────────────────────────────────────────────

class TestGetAllHistory:
    def test_empty_db_returns_empty_dict(self):
        assert ls.get_all_history() == {}

    def test_returns_all_records(self):
        for rt in ("J3", "J7", "J14"):
            tid = ls.make_task_id("c1", "college", rt, _due())
            ls.mark_done(tid, "c1", "college", rt, _due())
        h = ls.get_all_history()
        assert len(h) == 3

    def test_keyed_by_task_id(self):
        tid = ls.make_task_id("c99", "college", "J7", _due())
        ls.mark_done(tid, "c99", "college", "J7", _due())
        h = ls.get_all_history()
        assert tid in h
        assert h[tid]["course_id"] == "c99"


# ── Tests PDF cache ──────────────────────────────────────────────────────────

class TestPdfCache:
    def test_get_pdf_cache_empty_returns_none(self):
        """get_pdf_cache retourne None quand pas d'entrée en cache."""
        result = ls.get_pdf_cache("c1", "college")
        assert result is None

    def test_set_and_get_pdf_cache(self):
        """set_pdf_cache suivi de get_pdf_cache retourne le chemin."""
        pdf_path = "/path/to/course.pdf"
        ls.set_pdf_cache("c1", "college", pdf_path)
        result = ls.get_pdf_cache("c1", "college")
        assert result == pdf_path

    def test_pdf_cache_composite_key(self):
        """PDF cache utilise (course_id, context) comme clé composite."""
        path_college = "/path/college.pdf"
        path_ue = "/path/ue.pdf"
        ls.set_pdf_cache("c1", "college", path_college)
        ls.set_pdf_cache("c1", "ue", path_ue)

        assert ls.get_pdf_cache("c1", "college") == path_college
        assert ls.get_pdf_cache("c1", "ue") == path_ue
        assert ls.get_pdf_cache("c2", "college") is None

    def test_set_pdf_cache_idempotent(self):
        """set_pdf_cache peut être appelé plusieurs fois sans créer de doublons."""
        path1 = "/path/v1.pdf"
        path2 = "/path/v2.pdf"

        ls.set_pdf_cache("c1", "college", path1)
        with ls._conn() as con:
            count1 = con.execute(
                "SELECT COUNT(*) FROM pdf_local_cache WHERE course_id=? AND context=?",
                ("c1", "college")
            ).fetchone()[0]
        assert count1 == 1

        # Appel une deuxième fois → doit UPDATE, pas INSERT
        ls.set_pdf_cache("c1", "college", path2)
        with ls._conn() as con:
            count2 = con.execute(
                "SELECT COUNT(*) FROM pdf_local_cache WHERE course_id=? AND context=?",
                ("c1", "college")
            ).fetchone()[0]
            row = con.execute(
                "SELECT pdf_path FROM pdf_local_cache WHERE course_id=? AND context=?",
                ("c1", "college")
            ).fetchone()

        assert count2 == 1, "Le nombre de lignes doit rester 1 (idempotent)"
        assert row["pdf_path"] == path2, "Le chemin doit être mis à jour"

    def test_pdf_cache_detected_at_is_today(self):
        """detected_at doit être la date ISO d'aujourd'hui."""
        today = datetime.date.today().isoformat()
        ls.set_pdf_cache("c1", "college", "/path/pdf.pdf")

        with ls._conn() as con:
            row = con.execute(
                "SELECT detected_at FROM pdf_local_cache WHERE course_id=? AND context=?",
                ("c1", "college")
            ).fetchone()

        assert row["detected_at"] == today

    def test_multiple_courses(self):
        """Plusieurs cours peuvent avoir leurs propres entrées PDF en cache."""
        ls.set_pdf_cache("c1", "college", "/path/c1.pdf")
        ls.set_pdf_cache("c2", "college", "/path/c2.pdf")
        ls.set_pdf_cache("c3", "college", "/path/c3.pdf")

        assert ls.get_pdf_cache("c1", "college") == "/path/c1.pdf"
        assert ls.get_pdf_cache("c2", "college") == "/path/c2.pdf"
        assert ls.get_pdf_cache("c3", "college") == "/path/c3.pdf"

    def test_table_exists_after_init(self):
        """La table pdf_local_cache doit exister après init_db()."""
        with ls._conn() as con:
            tables = con.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='pdf_local_cache'"
            ).fetchall()
        assert len(tables) == 1, "La table pdf_local_cache doit exister"

    def test_cleanup_pdf_cache_existing_files_kept(self):
        """cleanup_pdf_cache doit garder les entrées dont le fichier existe."""
        # Créer des fichiers temporaires
        with tempfile.TemporaryDirectory() as tmpdir:
            pdf_path = Path(tmpdir) / "course.pdf"
            pdf_path.write_text("fake pdf content")

            ls.set_pdf_cache("c1", "college", str(pdf_path))

            # Le fichier existe → ne doit pas être supprimé
            removed = ls.cleanup_pdf_cache()
            assert removed == 0
            assert ls.get_pdf_cache("c1", "college") == str(pdf_path)

    def test_cleanup_pdf_cache_missing_files_deleted(self):
        """cleanup_pdf_cache doit supprimer les entrées dont le fichier n'existe pas."""
        # Chemin inexistant
        fake_path = "/nonexistent/path/to/missing.pdf"
        ls.set_pdf_cache("c1", "college", fake_path)

        # Le fichier n'existe pas → doit être supprimé
        removed = ls.cleanup_pdf_cache()
        assert removed == 1
        assert ls.get_pdf_cache("c1", "college") is None

    def test_cleanup_pdf_cache_empty_table_returns_zero(self):
        """cleanup_pdf_cache retourne 0 si la table est vide."""
        removed = ls.cleanup_pdf_cache()
        assert removed == 0

    def test_cleanup_pdf_cache_mixed_case(self):
        """cleanup_pdf_cache doit garder les valides, supprimer les stale."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Créer un fichier existant
            valid_path = Path(tmpdir) / "valid.pdf"
            valid_path.write_text("valid pdf")

            # Chemin inexistant
            invalid_path = "/nonexistent/invalid.pdf"

            # Entrées dans le cache
            ls.set_pdf_cache("c1", "college", str(valid_path))
            ls.set_pdf_cache("c2", "college", invalid_path)
            ls.set_pdf_cache("c3", "ue", invalid_path)
            ls.set_pdf_cache("c4", "college", str(valid_path))

            # Cleanup
            removed = ls.cleanup_pdf_cache()
            assert removed == 2  # c2 et c3 supprimés

            # Vérifier que c1 et c4 existent toujours
            assert ls.get_pdf_cache("c1", "college") == str(valid_path)
            assert ls.get_pdf_cache("c4", "college") == str(valid_path)

            # Vérifier que c2 et c3 sont supprimés
            assert ls.get_pdf_cache("c2", "college") is None
            assert ls.get_pdf_cache("c3", "ue") is None


# ── Tests Routine ─────────────────────────────────────────────────────────────

class TestRoutineChecks:
    def test_get_routine_items_defaults(self):
        items = ls.get_routine_items()
        assert items == ['Révision', 'QCM', 'Sport', 'Musique', 'Anki']

    def test_get_routine_checks_empty(self):
        checks = ls.get_routine_checks('2026-06-23')
        assert checks == {}

    def test_set_and_get_check_true(self):
        ls.set_routine_check('2026-06-23', 'Sport', True)
        assert ls.get_routine_checks('2026-06-23')['Sport'] is True

    def test_set_check_idempotent_update(self):
        ls.set_routine_check('2026-06-23', 'Anki', True)
        ls.set_routine_check('2026-06-23', 'Anki', False)
        assert ls.get_routine_checks('2026-06-23')['Anki'] is False

    def test_checks_isolated_by_date(self):
        ls.set_routine_check('2026-06-23', 'Sport', True)
        assert 'Sport' not in ls.get_routine_checks('2026-06-24')

    def test_get_routine_items_excludes_inactive(self):
        with ls._conn() as con:
            con.execute("UPDATE routine_items SET active = 0 WHERE name = 'Anki'")
        items = ls.get_routine_items()
        assert 'Anki' not in items


# ── Tests LiSA OIC ────────────────────────────────────────────────────────────

class TestLisaOic:
    def test_get_returns_none_before_fetch(self):
        result = ls.get_lisa_oic("course-abc")
        assert result is None

    def test_upsert_then_get_returns_list(self):
        oics = [
            {"oic_code": "OIC-223-01-A", "intitule": "Connaître le risque",
             "rang": "A", "rubrique": "Définition", "ordre": 1},
            {"oic_code": "OIC-223-03-B", "intitule": "Comprendre la physio",
             "rang": "B", "rubrique": "Physiopathologie", "ordre": 3},
        ]
        ls.upsert_lisa_oic("course-abc", oics)
        result = ls.get_lisa_oic("course-abc")
        assert result is not None
        assert len(result) == 2
        codes = [r["oic_code"] for r in result]
        assert "OIC-223-01-A" in codes
        assert "OIC-223-03-B" in codes

    def test_upsert_empty_list_marks_as_fetched(self):
        ls.upsert_lisa_oic("course-xyz", [])
        result = ls.get_lisa_oic("course-xyz")
        assert result is not None   # fetched, juste vide
        assert result == []

    def test_upsert_preserves_mastered(self):
        oics = [
            {"oic_code": "OIC-223-01-A", "intitule": "Connaître le risque",
             "rang": "A", "rubrique": "Définition", "ordre": 1},
        ]
        ls.upsert_lisa_oic("course-abc", oics)
        rows = ls.get_lisa_oic("course-abc")
        oic_id = rows[0]["id"]
        ls.toggle_lisa_oic_mastery(oic_id)

        # Re-upsert (simule un "Actualiser")
        ls.upsert_lisa_oic("course-abc", oics)
        rows2 = ls.get_lisa_oic("course-abc")
        assert rows2[0]["mastered"] == 1   # conservé

    def test_toggle_mastery(self):
        oics = [{"oic_code": "OIC-1", "intitule": "Test",
                 "rang": "A", "rubrique": "Def", "ordre": 1}]
        ls.upsert_lisa_oic("course-abc", oics)
        rows = ls.get_lisa_oic("course-abc")
        oic_id = rows[0]["id"]

        assert rows[0]["mastered"] == 0
        result = ls.toggle_lisa_oic_mastery(oic_id)
        assert result is True
        rows2 = ls.get_lisa_oic("course-abc")
        assert rows2[0]["mastered"] == 1

        result2 = ls.toggle_lisa_oic_mastery(oic_id)
        assert result2 is False
        rows3 = ls.get_lisa_oic("course-abc")
        assert rows3[0]["mastered"] == 0

    def test_toggle_unknown_id_returns_false(self):
        result = ls.toggle_lisa_oic_mastery(9999)
        assert result is False
