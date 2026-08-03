"""frontend/components/import_dp_dialog.py — Modale d'import de DP/KFP IA (ChatGPT / Gemini).

Permet d'importer directement un fichier JSON ou de coller un bloc JSON de DP généré par IA,
puis de le sauvegarder localement dans la banque UNESS d'archives sans aucun appel API.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Callable, Optional

from nicegui import ui
from loguru import logger

from backend.core.uness.exam_simulator import AI_IMPORTS_DIR


def open_import_dp_dialog(on_success: Optional[Callable[[], None]] = None) -> None:
    """Ouvre la boîte de dialogue d'importation de DP/KFP au format JSON."""
    dialog = ui.dialog()
    
    with dialog, ui.card().classes("w-[650px] max-w-full p-6 bg-slate-900 text-slate-100 rounded-xl border border-slate-700 shadow-2xl"):
        ui.label("📥 Importer un DP / KFP (ChatGPT / Gemini)").classes("text-xl font-bold text-sky-400 mb-2")
        ui.label(
            "Collez le code JSON généré par l'IA ou sélectionnez le fichier .json. "
            "Il sera immédiatement ajouté à votre banque locale pour les examens blancs."
        ).classes("text-xs text-slate-400 mb-4")

        json_area = ui.textarea(
            label="Bloc JSON du DP",
            placeholder='{"schema_version": 1, "title": "DP Cardio...", "dp_context": {...}, "questions": [...]}'
        ).classes("w-full h-64 font-mono text-xs bg-slate-950 text-emerald-400 border border-slate-800 rounded p-2")

        status_label = ui.label("").classes("text-xs mt-2 font-semibold")

        def _do_import():
            raw_text = json_area.value.strip()
            if not raw_text:
                status_label.set_text("⚠️ Veuillez coller un contenu JSON valide.")
                status_label.classes(replace="text-amber-400")
                return

            try:
                # Nettoyage éventuel des balises markdown ```json
                if raw_text.startswith("```"):
                    lines = raw_text.splitlines()
                    if lines[0].startswith("```"):
                        lines = lines[1:]
                    if lines and lines[-1].startswith("```"):
                        lines = lines[:-1]
                    raw_text = "\n".join(lines).strip()

                data = json.loads(raw_text)

                # Validation basique du schéma DP
                if "questions" not in data or not isinstance(data["questions"], list):
                    status_label.set_text("❌ Format invalide : la clé 'questions' est manquante ou vide.")
                    status_label.classes(replace="text-rose-400")
                    return

                if "dp_context" not in data:
                    data["dp_context"] = {"enonce_general": "Énoncé non spécifié."}

                # Extraction metadata / sujet
                subject = str(data.get("metadata", {}).get("subject", "TRANSVERSE")).strip().upper()
                title = str(data.get("title", "DP_Import_IA")).strip()
                
                # Assurer le dossier de destination
                target_dir = AI_IMPORTS_DIR / subject
                target_dir.mkdir(parents=True, exist_ok=True)

                # Nom du fichier sécurisé
                safe_title = "".join(c if c.isalnum() else "_" for c in title).lower()
                target_file = target_dir / f"{safe_title}.json"

                with open(target_file, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)

                status_label.set_text(f"✅ DP importé avec succès dans '{subject}' ({len(data['questions'])} questions) !")
                status_label.classes(replace="text-emerald-400")
                ui.notify(f"Import réussi : {title}", type="positive")

                if on_success:
                    on_success()

                ui.timer(1.5, dialog.close, once=True)

            except Exception as e:
                logger.error(f"Erreur d'importation JSON DP: {e}")
                status_label.set_text(f"❌ Erreur JSON syntaxique : {str(e)}")
                status_label.classes(replace="text-rose-400")

        with ui.row().classes("w-full justify-between items-center mt-4"):
            ui.button("Annuler", on_click=dialog.close).props("flat color=grey text-color=white")
            ui.button(" Valider & Importer", on_click=_do_import).props("unelevated color=primary icon=download")

    dialog.open()
