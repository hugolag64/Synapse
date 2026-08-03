import sqlite3

from backend.core.reviews.local_store import backup_database


def test_backup_database_creates_readable_snapshot(tmp_path):
    source = tmp_path / "synapse_local.db"
    backup_dir = tmp_path / "backups"
    with sqlite3.connect(source) as con:
        con.execute("CREATE TABLE sample (value TEXT NOT NULL)")
        con.execute("INSERT INTO sample VALUES ('safe')")

    backup = backup_database(source_path=source, backup_dir=backup_dir)

    assert backup is not None
    assert backup.exists()
    with sqlite3.connect(backup) as con:
        assert con.execute("SELECT value FROM sample").fetchone()[0] == "safe"
