from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEPLOY = ROOT / "deploy"


def test_encrypted_backup_requires_two_destinations_and_key_permissions():
    script = (DEPLOY / "synapse-backup.sh").read_text(encoding="utf-8")

    assert "SYNAPSE_BACKUP_PRIMARY_DIR" in script
    assert "SYNAPSE_BACKUP_SECONDARY_DIR" in script
    assert "SYNAPSE_BACKUP_PASSPHRASE_FILE" in script
    assert "SYNAPSE_BACKUP_ALLOW_SAME_VOLUME" in script
    assert "stat -c '%a'" in script
    assert "openssl enc -aes-256-cbc -pbkdf2" in script
    assert "flock -n 9" in script
    assert "cp --reflink=auto" in script


def test_restore_test_checks_checksum_and_sqlite_integrity():
    script = (DEPLOY / "synapse-restore-test.sh").read_text(encoding="utf-8")

    assert "sha256sum -c" in script
    assert "openssl enc -d -aes-256-cbc -pbkdf2" in script
    assert "PRAGMA integrity_check" in script
    assert ".synapse-restorable.db" in script


def test_systemd_runs_backup_daily_and_restore_test_monthly():
    backup_timer = (DEPLOY / "synapse-backup.timer").read_text(encoding="utf-8")
    restore_timer = (DEPLOY / "synapse-restore-test.timer").read_text(encoding="utf-8")

    assert "OnCalendar=*-*-* 03:30:00" in backup_timer
    assert "Persistent=true" in backup_timer
    assert "OnCalendar=Sun *-*-01..07 05:00:00" in restore_timer
