import datetime


def test_mastery_snapshots_persist_mastery_and_retention_separately(tmp_path, monkeypatch):
    from backend.core.reviews import local_store
    from backend.core.analytics import weekly_report

    monkeypatch.setattr(local_store, "DB_PATH", tmp_path / "weekly.db")
    monkeypatch.setattr(local_store, "_DB", None)
    local_store.init_db()
    monkeypatch.setattr(weekly_report, "_current_week_iso", lambda: "2026-W32")

    try:
        assert weekly_report.save_mastery_snapshots([
            {
                "course_id": "course-1",
                "mastery_score": 65,
                "retention_score": 42,
                "mastery_level": "à consolider",
            }
        ]) == 1

        with local_store._conn() as con:
            row = con.execute(
                "SELECT mastery_score, retention_score, calculation_version "
                "FROM mastery_snapshots WHERE course_id = ?",
                ("course-1",),
            ).fetchone()

        assert tuple(row) == (65, 42, "v2")
    finally:
        if local_store._DB is not None:
            local_store._DB.close()
        monkeypatch.setattr(local_store, "_DB", None)
