#!/usr/bin/env bash
set -Eeuo pipefail

umask 077

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
STACK_DIR="${SYNAPSE_COMPOSE_DIR:-$(cd -- "${SCRIPT_DIR}/.." && pwd)}"
SERVICE="${SYNAPSE_BACKUP_SERVICE:-synapse}"
PRIMARY_DIR="${SYNAPSE_BACKUP_PRIMARY_DIR:-/srv/backups/synapse}"
SECONDARY_DIR="${SYNAPSE_BACKUP_SECONDARY_DIR:-/srv/backups/synapse-secondary}"
PASSPHRASE_FILE="${SYNAPSE_BACKUP_PASSPHRASE_FILE:-/etc/synapse/backup.pass}"
RETENTION="${SYNAPSE_BACKUP_RETENTION:-14}"
LOCK_FILE="${SYNAPSE_BACKUP_LOCK_FILE:-/run/lock/synapse-backup.lock}"

die() {
  echo "synapse-backup: $*" >&2
  exit 1
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || die "commande requise absente : $1"
}

require_command docker
require_command openssl
require_command sha256sum
require_command flock
require_command findmnt

[[ "$RETENTION" =~ ^[1-9][0-9]*$ ]] || die "rétention invalide : $RETENTION"
[[ -f "$PASSPHRASE_FILE" ]] || die "fichier de clé absent : $PASSPHRASE_FILE"

pass_mode="$(stat -c '%a' "$PASSPHRASE_FILE")"
[[ "$pass_mode" == "600" || "$pass_mode" == "400" ]] || die "droits de clé trop ouverts ($pass_mode), attendu 600 ou 400"

mkdir -p "$PRIMARY_DIR" "$SECONDARY_DIR"
chmod 700 "$PRIMARY_DIR" "$SECONDARY_DIR"

primary_device="$(findmnt -no SOURCE --target "$PRIMARY_DIR" 2>/dev/null || true)"
secondary_device="$(findmnt -no SOURCE --target "$SECONDARY_DIR" 2>/dev/null || true)"
if [[ "${SYNAPSE_BACKUP_ALLOW_SAME_VOLUME:-0}" != "1" && -n "$primary_device" && "$primary_device" == "$secondary_device" ]]; then
  die "les deux destinations sont sur le même volume ($primary_device)"
fi

exec 9>"$LOCK_FILE"
flock -n 9 || die "une sauvegarde est déjà en cours"

stamp="$(date -u +%Y%m%dT%H%M%SZ)"
artifact_name="synapse-${stamp}.tar.gz.enc"
primary_artifact="${PRIMARY_DIR}/${artifact_name}"
secondary_artifact="${SECONDARY_DIR}/${artifact_name}"
primary_tmp="${primary_artifact}.tmp.$$"
secondary_tmp="${secondary_artifact}.tmp.$$"
snapshot_path="/app/data/.synapse-restorable.db"

cleanup() {
  rm -f -- "$primary_tmp" "$secondary_tmp" "${primary_tmp}.sha256"
  docker compose -f "$STACK_DIR/docker-compose.yml" exec -T "$SERVICE" \
    python -c "from pathlib import Path; Path('$snapshot_path').unlink(missing_ok=True)" >/dev/null 2>&1 || true
}
trap cleanup EXIT

cd "$STACK_DIR"

docker compose exec -T "$SERVICE" python - <<'PY'
from pathlib import Path

from backend.core.reviews.local_store import backup_database

staging = Path("/app/data/.synapse-backup-staging")
staging.mkdir(parents=True, exist_ok=True)
snapshot = backup_database(backup_dir=staging, keep=1)
if snapshot is None:
    raise SystemExit("création du snapshot SQLite impossible")
target = Path("/app/data/.synapse-restorable.db")
target.unlink(missing_ok=True)
snapshot.replace(target)
print(target)
PY

docker compose exec -T "$SERVICE" tar \
  --exclude='./backups/*' \
  --exclude='./.synapse-backup-staging/*' \
  --sort=name --owner=0 --group=0 --numeric-owner \
  -czf - -C /app/data . \
  | openssl enc -aes-256-cbc -pbkdf2 -iter 600000 -salt -md sha256 \
      -pass "file:${PASSPHRASE_FILE}" > "$primary_tmp"

sha256sum "$primary_tmp" > "${primary_tmp}.sha256"
mv -- "$primary_tmp" "$primary_artifact"
mv -- "${primary_tmp}.sha256" "${primary_artifact}.sha256"

cp --reflink=auto -- "$primary_artifact" "$secondary_tmp"
cp --reflink=auto -- "${primary_artifact}.sha256" "${secondary_tmp}.sha256"
mv -- "$secondary_tmp" "$secondary_artifact"
mv -- "${secondary_tmp}.sha256" "${secondary_artifact}.sha256"

mapfile -t artifacts < <(find "$PRIMARY_DIR" -maxdepth 1 -type f -name 'synapse-*.tar.gz.enc' -printf '%T@ %p\n' | sort -nr | tail -n +$((RETENTION + 1)) | cut -d' ' -f2-)
for artifact in "${artifacts[@]}"; do
  rm -f -- "$artifact" "${artifact}.sha256" "$SECONDARY_DIR/$(basename "$artifact")" "$SECONDARY_DIR/$(basename "$artifact").sha256"
done

echo "Sauvegarde chiffrée créée : $primary_artifact"
echo "Copie secondaire créée : $secondary_artifact"
