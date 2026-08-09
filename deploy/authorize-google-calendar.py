"""Authorize Google Calendar locally and save a reusable token for Synapse."""

from __future__ import annotations

import os
from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow


SCOPES = ["https://www.googleapis.com/auth/calendar"]


def main() -> None:
    secrets_dir = Path(os.getenv("GOOGLE_CALENDAR_SECRETS_DIR", "google-secrets"))
    secrets_dir.mkdir(parents=True, exist_ok=True)
    credentials_path = secrets_dir / "credentials.json"
    token_path = secrets_dir / "token.json"

    if not credentials_path.is_file():
        raise SystemExit(
            f"Fichier manquant : {credentials_path}. "
            "Télécharge d'abord le client OAuth Desktop depuis Google Cloud."
        )

    flow = InstalledAppFlow.from_client_secrets_file(str(credentials_path), SCOPES)
    credentials = flow.run_local_server(port=0)
    token_path.write_text(credentials.to_json(), encoding="utf-8")
    print(f"Token Google Calendar enregistré dans {token_path}")


if __name__ == "__main__":
    main()
