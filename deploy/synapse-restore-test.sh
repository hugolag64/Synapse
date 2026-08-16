#!/usr/bin/env bash
set -Eeuo pipefail

umask 077

PRIMARY_DIR="${SYNAPSE_BACKUP_PRIMARY_DIR:-/srv/backups/synapse}"
SECONDARY_DIR="${SYNAPSE_BACKUP_SECONDARY_DIR:-/srv/backups/synapse-secondary}"
PASSPHRASE_FILE="${SYNAPSE_BACKUP_PASSPHRASE_FILE:-/etc/synapse/backup.pass}"
ARTIFACT="${1:-}"

die() {
  echo "synapse-restore-test: $*" >&2
  exit 1
}

for command_name in openssl sha256sum tar sqlite3 mktemp; do
  command -v "$command_name" >/dev/null 2>&1 || die "commande requise absente : $command_name"
done
[[ -f "$PASSPHRASE_FILE" ]] || die "fichier de clé absent : $PASSPHRASE_FILE"

if [[ -z "$ARTIFACT" ]]; then
  ARTIFACT="$(find "$PRIMARY_DIR" "$SECONDARY_DIR" -maxdepth 1 -type f -name 'synapse-*.tar.gz.enc' -printf '%T@ %p\n' 2>/dev/null | sort -nr | head -n 1 | cut -d' ' -f2-)"
fi
[[ -n "$ARTIFACT" && -f "$ARTIFACT" ]] || die "aucune sauvegarde chiffrée trouvée"
[[ -f "${ARTIFACT}.sha256" ]] || die "manifest SHA-256 absent pour $ARTIFACT"

(cd "$(dirname "$ARTIFACT")" && sha256sum -c "$(basename "${ARTIFACT}.sha256")")

temporary_dir="$(mktemp -d -t synapse-restore-test.XXXXXX)"
trap 'rm -rf -- "$temporary_dir"' EXIT

openssl enc -d -aes-256-cbc -pbkdf2 -iter 600000 -md sha256 \
  -pass "file:${PASSPHRASE_FILE}" -in "$ARTIFACT" \
  | tar -xzf - -C "$temporary_dir"

snapshot="$temporary_dir/.synapse-restorable.db"
[[ -f "$snapshot" ]] || die "snapshot SQLite absent de l'archive restaurée"
integrity="$(sqlite3 "$snapshot" 'PRAGMA integrity_check;')"
[[ "$integrity" == "ok" ]] || die "intégrité SQLite invalide : $integrity"

echo "Restauration vérifiée : $ARTIFACT"
echo "SQLite integrity_check : ok"
