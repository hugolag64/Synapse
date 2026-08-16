"""settings_cockpit.py — Vue « Paramètres » cockpit (refonte, session 15).

Vue principale de l'écran Paramètres.
settings.py). Liste de connexions (Notion/Obsidian/Google Calendar = vert
connecté ; EDNpro/Hypocampus = ambre, saisie manuelle) + bascule
d'apparence clair/sombre. Le classic (Pomodoro, durées, objectif
quotidien, mode examen, LiSA/UNESS, AnythingLLM, agendas Calendar,
correspondances Obsidian, import PDF, santé du système…) reste
réduit aux connexions et à l'apparence.

Pas de capture fournie pour cet écran (absente de `screenshots/`) — mise
en page déduite du seul texte README §13.

Écarts assumés (voir Journal du CLAUDE.md de la refonte) :
  • statuts dérivés de vérifications synchrones bon marché (présence de
    fichiers/config), pas d'appel réseau live — `_check_notion` du classic
    ping l'API Notion à chaque affichage, ce qui ne convient pas à un écran
    cockpit censé s'afficher instantanément comme les autres ;
  • Notion : `settings.notion.token` est un champ Pydantic obligatoire
    (l'app ne démarre pas sans) → toujours « Connecté » ; pas un vrai
    ping live, juste un reflet du fait que l'app tourne ;
  • Obsidian / Google Calendar : mêmes vérifications que
    `frontend/pages/health.py::_check_obsidian/_check_google_calendar`
    (chemin vault configuré ; `credentials.json` + `token.json` présents),
    rejouées ici en synchrone plutôt que d'importer ces fonctions
    couplées au rendu Tailwind du classic ;
  • aucune action de connexion/déconnexion ici (le README ne décrit qu'une
    liste, pas des boutons) — configurer réellement Notion/Obsidian/
    Calendar reste classic-only.
"""
from __future__ import annotations

import os
import asyncio
import sys
from datetime import date
from pathlib import Path

from nicegui import ui

from backend.state.store import data_store
from backend.config.settings import settings
from backend.core.uness import import_service
from backend.core.lisa import item_service
from frontend.components.uness_diagnostic_panel import render as render_uness_diagnostics
from frontend.components.dp_coverage_panel import render as render_dp_coverage
from frontend.components.uness_rank_admin import render_uness_rank_admin
from frontend.components.calendar_sources_panel import render as render_calendar_sources
from frontend.pages.catalog_admin import render_catalog_admin

def toggle_dark_mode(value: bool | None = None) -> bool:
    dark = ui.dark_mode()
    if value is None:
        dark.toggle()
    elif value:
        dark.enable()
    else:
        dark.disable()
    resolved = bool(dark.value)
    # La coquille relit cette préférence à chaque rendu de page : sans
    # persistance, le thème est réinitialisé à la navigation suivante.
    data_store.set_preference("dark_mode", resolved)
    return resolved

def _validate_uness_annale_url(url: str) -> str:
    from scripts.uness.collector import validate_annale_url

    return validate_annale_url(url)


_CSS = """
.se-wrap { max-width:none; width:100%; align-items:stretch; }
.se-domain-expansion { border:1px solid var(--border); border-radius:10px; background:var(--surface); margin-top:12px; overflow:hidden; }
.se-domain-expansion > .q-expansion-item__container > .q-item { min-height:54px; padding:10px 14px; }
.se-domain-expansion .q-expansion-item__content { padding:0 14px 14px; }
.se-domain-summary { color:var(--text-muted); font-size:11.5px; margin-top:2px; }
.se-topbar { padding:4px 0 18px; }
.se-title { font-size:20px; font-weight:600; color:var(--text); letter-spacing:-0.01em; }
.se-subtitle { font-size:12.5px; color:var(--text-muted); margin-top:4px; }
.se-label { font-size:10px; text-transform:uppercase; letter-spacing:.04em; color:var(--text-dim); font-weight:600; margin:20px 0 8px; }
.se-domain { padding:10px 12px 8px; border-left:3px solid var(--accent); background:var(--surface); border-radius:var(--radius-sm); }
.se-list { border:1px solid var(--border); border-radius:8px; overflow:hidden; }
.se-row { display:flex; align-items:center; gap:10px; height:44px; padding:0 14px; border-bottom:1px solid var(--border); }
.se-row:last-child { border-bottom:none; }
.se-dot { width:7px; height:7px; border-radius:50%; flex:0 0 7px; }
.se-name { font-size:13px; color:var(--text); flex:1 1 auto; }
.se-status { font-size:12px; color:var(--text-muted); flex:0 0 auto; }
.se-appearance-row { display:flex; align-items:center; justify-content:space-between; gap:12px;
  border:1px solid var(--border); border-radius:8px; padding:12px 14px; }
.se-appearance-label { font-size:13px; color:var(--text); }
.se-appearance-sub { font-size:11.5px; color:var(--text-muted); margin-top:2px; }
.se-timezone-row { display:flex; align-items:center; justify-content:space-between; gap:12px;
  border:1px solid var(--border); border-radius:8px; padding:10px 14px; margin-top:8px; }
.se-planning-actions { display:flex; align-items:center; justify-content:space-between; gap:10px; margin-top:8px; }
.se-planning-status { color:var(--text-muted); font-size:11.5px; }
.se-switch { width:36px; height:20px; border-radius:10px; background:var(--surface-hover); position:relative;
  cursor:pointer; flex:0 0 auto; transition: background var(--duration-base) var(--ease-standard); }
.se-switch.on { background:var(--accent); }
.se-switch-knob { position:absolute; top:2px; left:2px; width:16px; height:16px; border-radius:50%; background:var(--bg);
  transition: left var(--duration-base) var(--ease-standard); box-shadow:0 1px 2px rgba(0,0,0,0.2); }
.se-switch.on .se-switch-knob { left:18px; }
.se-diag-expansion { border:1px solid var(--border); border-radius:10px; background:var(--surface); margin-top:12px; overflow:hidden; }
.se-tele-kpis { display:flex; align-items:center; justify-content:space-between; gap:12px;
  border:1px solid var(--border); border-radius:8px; background:var(--bg-alt); padding:12px 14px; }
.se-tele-value { font-size:20px; font-weight:700; color:var(--success-text); }
.se-tele-strong { font-size:13px; font-weight:600; color:var(--text); }
.se-tele-muted { font-size:11px; color:var(--text-muted); }
.se-tele-section-title { font-size:10px; text-transform:uppercase; letter-spacing:.04em;
  color:var(--text-muted); font-weight:600; margin:14px 0 6px; }
.se-tele-list { display:flex; flex-direction:column; gap:2px; max-height:190px; overflow-y:auto;
  border:1px solid var(--border); border-radius:8px; background:var(--bg-alt); padding:8px 10px; }
.se-tele-row { display:flex; align-items:center; justify-content:space-between; gap:10px;
  font-size:11.5px; padding:5px 0; border-bottom:1px solid var(--border); }
.se-tele-row:last-child { border-bottom:none; }
.se-tele-name { font-weight:600; color:var(--text); min-width:0; overflow:hidden;
  text-overflow:ellipsis; white-space:nowrap; flex:1 1 auto; }
.se-tele-cost { font-family:var(--font-mono); font-weight:700; color:var(--success-text); flex:0 0 auto; }
.se-tele-ok { font-family:var(--font-mono); font-weight:700; color:var(--success-text); flex:0 0 auto; }
.se-tele-err { font-family:var(--font-mono); font-weight:700; color:var(--danger-text); flex:0 0 auto; }
.se-uness-card { border:1px solid var(--border); border-radius:8px; padding:14px; }
.se-uness-status { font-size:11.5px; color:var(--text-muted); margin-top:6px; }
.se-diag-annale { border:1px solid var(--border); border-radius:8px; padding:12px 14px; margin-bottom:8px; }
.se-diag-head { display:flex; align-items:center; justify-content:space-between; gap:8px; }
.se-diag-title { font-size:13px; font-weight:600; color:var(--text); }
.se-diag-ratio { font-size:12px; font-weight:600; }
.se-diag-ratio.full { color:var(--success-text); }
.se-diag-ratio.partial { color:var(--warning-text); }
.se-diag-quiz-row { display:flex; align-items:center; justify-content:space-between; gap:8px; padding:4px 0; font-size:12.5px; }
.se-diag-quiz-detail { color:var(--text-muted); font-size:11.5px; }
@media (max-width: 820px) {
  .se-domain-expansion > .q-expansion-item__container > .q-item { padding:9px 10px; }
  .se-domain-expansion .q-expansion-item__content { padding:0 10px 10px; }
}
"""


def _connection_rows() -> list[tuple[str, bool | None, str]]:
    notion_ok = bool(settings.notion.token)
    obsidian_ok = bool(settings.obsidian_vault_path)
    from backend.core.google.calendar_service import calendar_service

    calendar_ok = os.path.isfile(calendar_service.credentials_path) and os.path.isfile(calendar_service.token_path)

    return [
        ("Notion", notion_ok, "Connecté" if notion_ok else "Non configuré"),
        ("Obsidian", obsidian_ok, "Connecté" if obsidian_ok else "Non configuré"),
        ("Google Calendar", calendar_ok, "Connecté" if calendar_ok else "Non configuré"),
        ("EDNpro", None, "Automatisation à connecter"),
        ("Hypocampus", None, "Automatisation à connecter"),
    ]


_SETTINGS_DOMAIN_GROUP = "settings-domains"


def _settings_domain(title: str, description: str, icon: str):
    expansion = ui.expansion(title, icon=icon, value=False)
    expansion.props(f"group={_SETTINGS_DOMAIN_GROUP}")
    expansion.classes("se-domain-expansion w-full")
    with expansion:
        ui.label(description).classes("se-domain-summary")
    return expansion


def render_settings_cockpit() -> None:
    ui.add_head_html(f"<style>{_CSS}</style>", shared=True)

    with ui.column().classes("se-wrap gap-0"):
        with ui.element("div").classes("se-topbar"):
            ui.label("Paramètres").classes("se-title")
            ui.label("Connexions · apparence").classes("se-subtitle")

        with _settings_domain("CONNEXIONS", "Fournisseurs et calendriers", "link") as connections:
            with connections:
                with ui.element("div").classes("se-list"):
                    for name, ok, status_label in _connection_rows():
                        color = (
                            "var(--success)" if ok is True
                            else "var(--warning)" if ok is None
                            else "var(--text-dim)"
                        )
                        with ui.element("div").classes("se-row"):
                            ui.element("span").classes("se-dot").style(f"background:{color}")
                            ui.label(name).classes("se-name")
                            ui.label(status_label).classes("se-status")

                render_calendar_sources(ui.column().classes("w-full"))

        with _settings_domain("APPARENCE ET ACCESSIBILITÉ", "Thème et préférences d'affichage", "palette") as appearance:
            with appearance:
                with ui.element("div").classes("se-appearance-row"):
                    with ui.column().classes("gap-0"):
                        ui.label("Mode sombre").classes("se-appearance-label")
                        ui.label("Basculer entre thème clair et sombre").classes("se-appearance-sub")

                    is_dark = bool(data_store.preferences.get("dark_mode", False))
                    switch = ui.element("div").classes("se-switch on" if is_dark else "se-switch")
                    with switch:
                        ui.element("div").classes("se-switch-knob")

                    def _toggle(sw=switch):
                        new_val = not bool(data_store.preferences.get("dark_mode", False))
                        toggle_dark_mode(new_val)
                        if new_val:
                            sw.classes(add="on")
                        else:
                            sw.classes(remove="on")

                    switch.on("click", _toggle)

                with ui.element("div").classes("se-timezone-row"):
                    with ui.column().classes("gap-0"):
                        ui.label("Fuseau horaire métier").classes("se-appearance-label")
                        ui.label("Utilisé pour les dates du planning et des sessions").classes("se-appearance-sub")
                    timezone_select = ui.select(
                        options={"Europe/Paris": "Europe/Paris", "Indian/Reunion": "Indian/Reunion"},
                        value=data_store.preferences.get("timezone", "Europe/Paris"),
                    ).props("outlined dense options-dense")

                    def _set_timezone(event):
                        data_store.set_preference("timezone", event.value)
                        ui.notify(f"Fuseau horaire : {event.value}", type="positive")

                    timezone_select.on("update:model-value", _set_timezone)

        with _settings_domain("PLANIFICATION EDN", "Dates et Sprint EDN", "event") as planning:
            with planning:
                with ui.element("div").classes("se-timezone-row"):
                    with ui.column().classes("gap-0"):
                        ui.label("Date cible EDN").classes("se-appearance-label")
                        ui.label("Utilisée pour le compte à rebours et les projections").classes("se-appearance-sub")
                    target_date = ui.input(
                        label="Date",
                        value=data_store.preferences.get("edn_target_date", "2026-10-15"),
                    ).props("outlined dense type=date")

                with ui.element("div").classes("se-timezone-row"):
                    with ui.column().classes("gap-0"):
                        ui.label("Date de reprise").classes("se-appearance-label")
                        ui.label("Les nouvelles actions commencent à partir de cette date").classes("se-appearance-sub")
                    resume_date = ui.input(
                        label="Date",
                        value=data_store.preferences.get("study_resume_date", "2026-08-20"),
                    ).props("outlined dense type=date")

                planning_status = ui.label().classes("se-planning-status")
                with ui.element("div").classes("se-planning-actions"):
                    ui.button(
                        "Enregistrer la planification",
                        on_click=lambda: _save_planning_preferences(target_date, resume_date, planning_status),
                    ).props("unelevated color=primary")
                    sprint_visible = bool(data_store.preferences.get("edn_sprint_visible", True))
                    visibility_button = ui.button(
                        "Masquer le Sprint" if sprint_visible else "Réafficher le Sprint",
                        on_click=lambda: _toggle_sprint_visibility(visibility_button),
                    ).props("flat dense")

        def _save_planning_preferences(target_input, resume_input, status_label) -> None:
            try:
                target_value = str(target_input.value or "").strip()
                resume_value = str(resume_input.value or "").strip()
                date.fromisoformat(target_value)
                date.fromisoformat(resume_value)
            except ValueError:
                status_label.set_text("Date invalide — aucune modification enregistrée")
                ui.notify("Date de planification invalide", type="negative")
                return

            data_store.set_preferences(
                {
                    "edn_target_date": target_value,
                    "study_resume_date": resume_value,
                    "edn_sprint_visible": bool(data_store.preferences.get("edn_sprint_visible", True)),
                }
            )
            status_label.set_text("Planification enregistrée")
            ui.notify("Planification enregistrée", type="positive")

        def _toggle_sprint_visibility(button) -> None:
            visible = not bool(data_store.preferences.get("edn_sprint_visible", True))
            data_store.set_preference("edn_sprint_visible", visible)
            button.text = "Masquer le Sprint" if visible else "Réafficher le Sprint"
            ui.notify("Sprint affiché" if visible else "Sprint masqué", type="positive")

        with _settings_domain("DONNÉES UNESS", "Import et normalisation", "school"):
            with ui.element("div").classes("se-uness-card"):
                ui.label("Importer une annale UNESS").classes("se-appearance-label")
                ui.label(
                    "Collez une URL d’annale. La collecte locale réutilisera votre session UNESS."
                ).classes("se-appearance-sub")
                url_input = ui.input(
                    label="URL de l’annale",
                    value=data_store.preferences.get("uness_annale_url", ""),
                    placeholder="https://entrainement.uness.fr/annales/course/view.php?id=29135",
                ).props("outlined dense").classes("w-full mt-3")
                status = ui.label(
                    "Aucune URL préparée."
                ).classes("se-uness-status")

                def _prepare_import():
                    try:
                        url = _validate_uness_annale_url(url_input.value)
                    except ValueError as exc:
                        status.set_text(str(exc))
                        status.style("color:var(--danger-text)")
                        ui.notify(str(exc), type="negative")
                        return
                    data_store.set_preference("uness_annale_url", url)
                    data_store.set_preference("uness_import_status", "prepared")
                    status.set_text("URL enregistrée ✓ — prête pour le collecteur local et la normalisation JSON.")
                    status.style("color:var(--success-text)")
                    ui.notify("URL UNESS enregistrée", type="positive", icon="school")

                ui.button(
                    "Préparer l’import",
                    icon="download",
                    on_click=_prepare_import,
                ).props("unelevated color=teal size=sm rounded").classes("mt-3")

                async def _launch_collector():
                    try:
                        url = _validate_uness_annale_url(url_input.value)
                    except ValueError as exc:
                        status.set_text(str(exc))
                        status.style("color:var(--danger-text)")
                        ui.notify(str(exc), type="negative")
                        return
                    data_store.set_preference("uness_annale_url", url)
                    status.set_text("Collecte en cours — Chrome va s’ouvrir…")
                    status.style("color:var(--warning-text)")
                    script = Path("scripts/uness/collector.py").resolve()
                    process = await asyncio.create_subprocess_exec(
                        sys.executable,
                        str(script),
                        url,
                        "--submit",
                        cwd=str(Path.cwd()),
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.STDOUT,
                    )
                    output, _ = await process.communicate()
                    if process.returncode == 0:
                        status.set_text(
                            f"Collecte terminée ✓ — fichier prêt à envoyer dans ChatGPT : {output.decode(errors='replace').strip()}"
                        )
                        status.style("color:var(--success-text)")
                        ui.notify("Collecte UNESS terminée", type="positive", icon="school")
                    else:
                        message = output.decode(errors="replace").strip()[-500:]
                        status.set_text(f"Échec de la collecte : {message}")
                        status.style("color:var(--danger-text)")
                        ui.notify("Échec de la collecte UNESS", type="negative")

                ui.button(
                    "Lancer la collecte et soumettre",
                    icon="play_arrow",
                    on_click=_launch_collector,
                ).props("outline color=teal size=sm rounded").classes("mt-2")

                def _finalize_scan(tags: dict[str, str] | None = None) -> None:
                    result = import_service.import_verified_directory(tags=tags)
                    pending = result["pending_tag"]
                    if pending:
                        _open_tag_dialog(pending)
                        return
                    imported_count = len(result["imported"])
                    error_count = len(result["errors"])
                    status.set_text(
                        f"Scan terminé : {imported_count} importé(s), "
                        f"{len(result['skipped'])} déjà présent(s), {error_count} erreur(s)."
                    )
                    status.style("color:var(--danger-text)" if error_count else "color:var(--success-text)")
                    ui.notify(
                        f"{imported_count} partiel(s) importé(s)" if not error_count else "Import terminé avec des erreurs",
                        type="positive" if not error_count else "warning",
                    )

                def _open_tag_dialog(pending: list[dict]) -> None:
                    chosen: dict[str, str] = {}
                    with ui.dialog() as dialog, ui.card().classes("w-[520px] max-w-[95vw] p-5"):
                        ui.label("Nouvelles annales à qualifier").classes("text-lg font-semibold")
                        ui.label(
                            "Ces partiels n'ont jamais été importés : indique leur type avant de continuer."
                        ).classes("text-xs mb-3").style("color:var(--text-muted)")
                        for group in pending:
                            source_url = group["source_url"]
                            chosen[source_url] = "matiere"
                            with ui.column().classes("w-full gap-1 mb-3"):
                                ui.label(group["titre"] or source_url).classes("font-semibold text-sm")
                                ui.label(
                                    f"{group['matiere'] or '—'} · {group['faculte'] or '—'} · {group['annee'] or '—'} "
                                    f"· {len(group['files'])} fichier(s)"
                                ).classes("text-xs").style("color:var(--text-muted)")
                                ui.select(
                                    import_service.ANNALE_TYPE_LABELS,
                                    value="matiere",
                                    on_change=lambda e, url=source_url: chosen.__setitem__(url, e.value),
                                ).props("outlined dense").classes("w-full")
                        with ui.row().classes("w-full justify-end gap-2 mt-3"):
                            ui.button("Ignorer pour l'instant", on_click=dialog.close).props("flat")
                            ui.button(
                                "Valider",
                                on_click=lambda: (dialog.close(), _finalize_scan(tags=chosen)),
                            ).props("unelevated color=purple")
                    dialog.open()

                def _scan_verified() -> None:
                    try:
                        _finalize_scan()
                    except Exception as e:
                        status.set_text(f"Erreur lors du scan : {str(e)}")
                        status.style("color:var(--danger-text)")
                        ui.notify(f"Erreur du scanner : {str(e)}", type="negative")

                ui.button(
                    "Scanner les JSON vérifiés",
                    icon="fact_check",
                    on_click=_scan_verified,
                ).props("unelevated color=purple size=sm rounded").classes("mt-3")
                ui.label("Échange local : UNESS/à_vérifier → UNESS/vérifiés → UNESS/archives").classes("se-uness-status")

        with _settings_domain("LISA / OIC", "Objectifs de connaissance", "school"):
            with ui.element("div").classes("se-uness-card"):
                ui.label("Objectifs de connaissance (OIC)").classes("se-appearance-label")
                ui.label(
                    "Récupère les OIC LiSA pour tous les items déjà liés à un cours. "
                    "Sans risque à relancer : la maîtrise et le niveau déjà acquis sont "
                    "préservés, seuls les ajouts/retraits LiSA sont pris en compte."
                ).classes("se-appearance-sub")
                oic_status = ui.label("Jamais lancé.").classes("se-uness-status mt-3")
                oic_progress = {"done": 0, "total": 0}
                oic_timer_holder: dict = {}

                def _on_oic_progress(done: int, total: int, item_key: str) -> None:
                    oic_progress["done"] = done
                    oic_progress["total"] = total

                def _tick_oic_progress() -> None:
                    if oic_progress["total"]:
                        oic_status.set_text(f"En cours… {oic_progress['done']}/{oic_progress['total']} items")

                async def _refresh_all_oic(button) -> None:
                    button.props(add="loading")
                    oic_progress.update(done=0, total=0)
                    oic_timer_holder["timer"] = ui.timer(0.5, _tick_oic_progress)
                    try:
                        result = await asyncio.to_thread(
                            item_service.scrape_all_items,
                            list(data_store.cours),
                            _on_oic_progress,
                        )
                        failed = result["items_failed"]
                        oic_status.set_text(
                            f"Terminé : {result['items_ok']}/{result['items_total']} items mis à jour"
                            + (f", {failed} échec(s)" if failed else "")
                        )
                        oic_status.style("color:var(--danger-text)" if failed else "color:var(--success-text)")
                        ui.notify(
                            f"OIC rafraîchis : {result['items_ok']}/{result['items_total']}"
                            + (f" ({failed} échec(s))" if failed else ""),
                            type="warning" if failed else "positive",
                            icon="school",
                        )
                    except Exception as exc:
                        oic_status.set_text(f"Erreur : {exc}")
                        oic_status.style("color:var(--danger-text)")
                        ui.notify(f"Échec du rafraîchissement OIC : {exc}", type="negative")
                    finally:
                        timer = oic_timer_holder.pop("timer", None)
                        if timer:
                            timer.deactivate()
                        button.props(remove="loading")

                oic_button = ui.button(
                    "Rafraîchir tous les OIC (LiSA)",
                    icon="refresh",
                ).props("outline color=violet size=sm rounded").classes("mt-3")
                oic_button.on("click", lambda: asyncio.ensure_future(_refresh_all_oic(oic_button)))

        render_catalog_admin()

        with _settings_domain("DIAGNOSTICS ET TÉLÉMÉTRIE", "Couverture et consommation", "analytics"):
            with ui.expansion("RANGS UNESS — VALIDATION", icon="verified").classes(
                "w-full se-diag-expansion"
            ):
                render_uness_rank_admin(ui.column().classes("w-full p-4"))

            with ui.expansion("COUVERTURE DP PAR ITEM", icon="assignment").classes(
                "w-full se-diag-expansion"
            ):
                render_dp_coverage(ui.column().classes("w-full p-4"))

            with ui.expansion(
                "CONSOMMATION, TÉLÉMÉTRIE & PARTIELS IMPORTÉS", icon="analytics"
            ).classes("w-full se-diag-expansion"):
                from backend.core.reviews.local_store import get_ai_usage_summary
                usage_data = get_ai_usage_summary(limit=50)
                summary = usage_data.get("summary", {})
                recent = usage_data.get("recent_calls", [])

                total_cost = float(summary.get("total_cost_usd", 0.0))
                total_calls = int(summary.get("total_calls", 0))
                total_in = int(summary.get("total_input_tokens", 0))
                total_out = int(summary.get("total_output_tokens", 0))
                total_tok = total_in + total_out

                with ui.column().classes("w-full p-4 gap-4"):
                    # Historique des Partiels importés (Diagnostic UNESS)
                    render_uness_diagnostics(ui.column().classes("w-full mb-2"))

                    # Cartes KPI synthétiques
                    with ui.element("div").classes("se-tele-kpis"):
                        with ui.column().classes("gap-0"):
                            ui.label(f"${total_cost:.4f} USD").classes("se-tele-value")
                            ui.label("Coût IA cumulé").classes("se-tele-muted")
                        with ui.column().classes("gap-0 text-right"):
                            ui.label(f"{total_tok:,} tokens").classes("se-tele-strong")
                            ui.label(f"{total_in:,} entrée · {total_out:,} sortie").classes("se-tele-muted")
                        with ui.column().classes("gap-0 text-right"):
                            ui.label(f"{total_calls} appels").classes("se-tele-strong")
                            ui.label(f"{summary.get('total_errors', 0)} erreur(s)").classes("se-tele-muted")

                    # Détail clair par Partiel / Tâche / Contexte
                    ui.label("Coûts par Partiel & Activité").classes("se-tele-section-title")
                    by_context = usage_data.get("by_context", [])
                    if not by_context:
                        ui.label("Aucune donnée enregistrée.").classes("se-tele-muted")
                    else:
                        with ui.element("div").classes("se-tele-list"):
                            for item in by_context:
                                ctx_name = item.get("context") or item.get("task") or "Génération générale"
                                cost_val = float(item.get("cost", 0.0))
                                tok_val = int(item.get("tokens", 0))
                                calls_val = int(item.get("calls", 0))
                                with ui.element("div").classes("se-tele-row"):
                                    ui.label(str(ctx_name)).classes("se-tele-name")
                                    ui.label(f"{calls_val} appel(s) · {tok_val:,} tok").classes("se-tele-muted")
                                    ui.label(f"${cost_val:.5f}").classes("se-tele-cost")

                    # Journal récent détaillé
                    ui.label("Historique des derniers appels Gemini").classes("se-tele-section-title")
                    if not recent:
                        ui.label("Aucun appel IA enregistré pour le moment.").classes("se-tele-muted")
                    else:
                        with ui.element("div").classes("se-tele-list"):
                            for call in recent:
                                status_class = "se-tele-err" if call.get("error") else "se-tele-ok"
                                status_text = "ERR" if call.get("error") else "OK"
                                c_usd = float(call.get("cost_usd", 0.0))
                                dur = f"{float(call.get('duration_ms', 0)):.0f}ms" if call.get("duration_ms") else "—"
                                ctx_label = str(call.get("context") or call.get("task") or "gemini_generate")
                                with ui.element("div").classes("se-tele-row"):
                                    with ui.row().classes("items-center gap-2 flex-1 min-w-0"):
                                        ui.label(status_text).classes(status_class)
                                        ui.label(ctx_label).classes("se-tele-name")
                                        ui.label(str(call.get("model"))).classes("se-tele-muted")
                                    with ui.row().classes("items-center gap-3 shrink-0"):
                                        ui.label(
                                            f"{call.get('input_tokens', 0) + call.get('output_tokens', 0)} tok"
                                        ).classes("se-tele-muted")
                                        ui.label(dur).classes("se-tele-muted")
                                        ui.label(f"${c_usd:.5f}").classes("se-tele-cost")
