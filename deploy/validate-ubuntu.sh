#!/usr/bin/env bash
set -Eeuo pipefail

host_port="${SYNAPSE_HOST_PORT:-8888}"
base_url="http://127.0.0.1:${host_port}"

echo "== compose =="
docker compose ps

echo "== liveness =="
curl --fail --silent --show-error "${base_url}/api/healthz"
echo

echo "== integration visibility (read-only) =="
docker compose exec -T synapse python - <<'PY'
from pathlib import Path

from backend.config.settings import settings
from backend.core.anki.client import AnkiClient

print(f"notion_configured={bool(settings.notion.token and settings.notion.cours_db_id)}")
vault = Path(settings.obsidian_vault_path)
print(f"obsidian_path={vault}")
print(f"obsidian_exists={vault.is_dir()}")
if vault.is_dir():
    print(f"obsidian_markdown_count={sum(1 for _ in vault.rglob('*.md'))}")
status = AnkiClient().ping()
print(f"anki_connected={status.connected}")
if status.reason:
    print(f"anki_reason={status.reason}")
PY
