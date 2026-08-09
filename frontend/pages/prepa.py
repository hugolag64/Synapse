"""Prépa hub: compact shortcuts for external preparation platforms."""

from __future__ import annotations

import asyncio
from collections import defaultdict
from pathlib import Path

from nicegui import ui

from datetime import datetime, timezone

from backend.core.prep.catalog import (
    list_prep_providers, list_prep_shortcuts, list_recent_prep_shortcuts, record_prep_access,
)
from frontend.cockpit_shell import cockpit_frame

_CSS = """
.prep-wrap { max-width:none; width:100%; }
.prep-title { font-size:20px; font-weight:600; color:var(--text); letter-spacing:-.01em; }
.prep-subtitle { color:var(--text-muted); font-size:12.5px; margin-top:4px; }
.prep-provider { width:100%; padding:16px 0 8px; border-top:1px solid var(--border); }
.prep-provider.ednpro { border-top:2px solid #5e6ad2; background:linear-gradient(90deg, rgba(94,106,210,.06), transparent 48%); }
.prep-provider.hypocampus { border-top:2px solid #0d9488; background:linear-gradient(90deg, rgba(13,148,136,.06), transparent 48%); }
.prep-provider.edni { border-top:2px solid #d97706; background:linear-gradient(90deg, rgba(217,119,6,.06), transparent 48%); }
@keyframes prepProviderEnter {
  0% { opacity: 0; transform: translateY(8px); }
  100% { opacity: 1; transform: translateY(0); }
}
.prep-provider { animation: prepProviderEnter var(--duration-base) var(--ease-standard) both; }
.prep-provider:nth-of-type(1) { animation-delay: 0ms; }
.prep-provider:nth-of-type(2) { animation-delay: 60ms; }
.prep-provider:nth-of-type(3) { animation-delay: 120ms; }
.prep-provider-name { font-size:14px; font-weight:600; color:var(--text); }
.prep-provider-meta { font-size:11.5px; color:var(--text-muted); }
.prep-section-title { font-size:11px; text-transform:uppercase; letter-spacing:.05em; color:var(--text-dim); font-weight:600; }
.prep-source-head, .prep-source-row { display:grid; grid-template-columns:minmax(180px, .8fr) minmax(240px, 1.5fr) 130px 72px; column-gap:16px; align-items:center; }
.prep-source-head { padding:0 12px 7px; color:var(--text-dim); font-size:9px; font-weight:600; letter-spacing:.05em; text-transform:uppercase; }
.prep-source-row { min-height:48px; padding:8px 12px; border-top:1px solid var(--border); color:var(--text); transition:background .12s, transform .12s, box-shadow .12s; }
.prep-source-row:hover { background:var(--surface); transform:translateY(-2px); box-shadow:var(--shadow-popover); }
.prep-shortcut-title { color:var(--text); font-size:13px; font-weight:600; }
.prep-shortcut-desc { color:var(--text-muted); font-size:11.5px; }
.prep-category { color:var(--text-muted); font-size:11px; text-transform:uppercase; letter-spacing:.04em; }
.prep-recent { display:grid; grid-template-columns:repeat(3, minmax(0, 1fr)); margin-bottom:8px; }
.prep-recent-item { min-width:0; padding:8px 12px; border-bottom:1px solid var(--border); }
.prep-recent-item:hover { background:var(--surface); }
.prep-recent-title { font-size:13px; font-weight:600; color:var(--text); }
.prep-recent-time { font-size:11px; color:var(--text-muted); margin-top:2px; }
@media (max-width:800px) {
  .prep-source-head, .prep-source-row { grid-template-columns:minmax(150px, .8fr) minmax(0, 1.2fr) 100px 64px; column-gap:10px; }
  .prep-recent { grid-template-columns:1fr; }
}
"""


def relative_time_label(last_used: datetime, now: datetime) -> str:
    """Libellé relatif compact pour un horodatage passé (« à l'instant », « il y a 5min »…)."""
    delta_seconds = (now - last_used).total_seconds()
    if delta_seconds < 60:
        return "à l'instant"
    minutes = int(delta_seconds // 60)
    if minutes < 60:
        return f"il y a {minutes}min"
    hours = int(delta_seconds // 3600)
    if hours < 24:
        return f"il y a {hours}h"
    days = int(delta_seconds // 86400)
    if days == 1:
        return "hier"
    return f"il y a {days}j"


_CATEGORY_ORDER = ("accueil", "masterclass", "entrainement", "annales", "iconographie", "lca", "videos")


def build_prepa_view(shortcuts: list[dict], providers: list[dict] | None = None) -> dict:
    provider_catalog = providers or list_prep_providers()
    grouped: dict[str, dict[str, list[dict]]] = defaultdict(lambda: defaultdict(list))
    for row in shortcuts:
        grouped[str(row["provider"])][str(row["category"])].append(row)

    def category_key(category: str) -> tuple[int, str]:
        try:
            return (_CATEGORY_ORDER.index(category), category)
        except ValueError:
            return (len(_CATEGORY_ORDER), category)

    sections = []
    for provider in provider_catalog:
        name = str(provider["name"])
        categories = [
            {
                "category": category,
                "shortcuts": sorted(
                    rows,
                    key=lambda row: (str(row.get("title", "")), int(row.get("id", 0))),
                ),
            }
            for category, rows in sorted(grouped.get(name, {}).items(), key=lambda pair: category_key(pair[0]))
        ]
        sections.append({
            "provider": name,
            "tone": "".join(ch for ch in name.lower() if ch.isalnum()),
            "root_url": provider.get("root_url", ""),
            "enabled": bool(provider.get("enabled")),
            "categories": categories,
        })
    return {"provider_sections": sections}


async def _run_ednpro_import() -> None:
    from scripts.ednpro.collector import collect_ednpro

    ui.notify("Collecte EDNpro lancée — la fenêtre de connexion va s’ouvrir si nécessaire.", type="info", spinner=True, duration=8)
    try:
        manifest = await asyncio.to_thread(
            lambda: asyncio.run(collect_ednpro(start_year=2023, auto_correct=True))
        )
    except Exception as exc:
        ui.notify(f"Import EDNpro interrompu : {exc}", type="negative", duration=10)
        return
    ui.notify(f"Import EDNpro terminé : {manifest}", type="positive", duration=10)


@ui.page("/prepa")
def prepa_page() -> None:
    ui.add_head_html(f"<style>{_CSS}</style>")
    shortcuts = list_prep_shortcuts()
    providers = list_prep_providers()
    view = build_prepa_view(shortcuts, providers)
    recent = list_recent_prep_shortcuts()

    with cockpit_frame("Prépa"):
        with ui.column().classes("prep-wrap gap-0"):
            with ui.row().classes("w-full items-start justify-between gap-4 pb-5 border-b"):
                with ui.column().classes("gap-0"):
                    ui.label("Prépa").classes("prep-title")
                    ui.label("Tes plateformes et raccourcis de préparation, au même endroit.").classes("prep-subtitle")
                ui.button("Importer les EDN", icon="download", on_click=_run_ednpro_import).props(
                    "unelevated size=sm"
                ).style("background:var(--accent);color:var(--accent-text);border-radius:6px;font-size:12px;font-weight:600")

            if recent:
                with ui.column().classes("w-full gap-2 pt-5"):
                    ui.label("Récemment consulté").classes("prep-section-title")
                    with ui.element("div").classes("prep-recent"):
                        for item in recent:
                            last_used = datetime.fromisoformat(item["last_used"])
                            with ui.link(target=item["url"], new_tab=True).classes(
                                "prep-recent-item no-underline"
                            ) as link:
                                ui.label(item["title"]).classes("prep-recent-title")
                                ui.label(
                                    relative_time_label(last_used, datetime.now(timezone.utc))
                                ).classes("prep-recent-time")
                            link.on(
                                "click",
                                lambda _event=None, sid=item.get("id"): record_prep_access(sid),
                            )

            with ui.column().classes("w-full gap-4 pt-6"):
                ui.label("Plateformes").classes("prep-section-title")
                for section in view["provider_sections"]:
                    with ui.element("section").classes(f"prep-provider {section['tone']}"):
                        with ui.row().classes("w-full items-center justify-between gap-3"):
                            with ui.column().classes("gap-0"):
                                ui.label(section["provider"]).classes("prep-provider-name")
                                if section["enabled"] and section["root_url"]:
                                    ui.link("Ouvrir la plateforme", section["root_url"], new_tab=True).classes(
                                        "text-xs text-[var(--accent)] hover:underline mt-1"
                                    )
                                else:
                                    ui.label("Connexion bientôt disponible").classes("prep-provider-meta mt-1")
                            ui.label(
                                f"{sum(len(group['shortcuts']) for group in section['categories'])} raccourci(s)"
                                if section["enabled"] else "Bientôt"
                            ).classes("prep-provider-meta")

                        if not section["categories"]:
                            ui.label("Aucun raccourci configuré pour le moment.").classes("prep-provider-meta mt-4")
                        else:
                            with ui.column().classes("w-full gap-0 mt-4"):
                                with ui.element("div").classes("prep-source-head"):
                                    ui.label("SOURCE")
                                    ui.label("OBJECTIF")
                                    ui.label("DERNIÈRE UTILISATION")
                                    ui.label("OUVRIR")
                                for group in section["categories"]:
                                    ui.label(group["category"]).classes("prep-category")
                                    for shortcut in group["shortcuts"]:
                                        last_used_raw = shortcut.get("last_used")
                                        if last_used_raw:
                                            try:
                                                last_used_label = relative_time_label(
                                                    datetime.fromisoformat(last_used_raw),
                                                    datetime.now(timezone.utc),
                                                )
                                            except (TypeError, ValueError):
                                                last_used_label = "Date indisponible"
                                        else:
                                            last_used_label = "Jamais"
                                        with ui.link(target=shortcut["url"], new_tab=True).classes(
                                            "prep-source-row no-underline"
                                        ) as link:
                                            with ui.row().classes("items-center gap-2 min-w-0"):
                                                ui.icon(shortcut.get("icon", "open_in_new")).classes(
                                                    "text-[var(--accent)] text-lg shrink-0"
                                                )
                                                ui.label(shortcut["title"]).classes("prep-shortcut-title truncate")
                                            ui.label(shortcut.get("description", "")).classes("prep-shortcut-desc truncate")
                                            ui.label(last_used_label).classes("prep-provider-meta")
                                            ui.label("Ouvrir →").classes("text-xs text-[var(--accent)]")
                                        link.on(
                                            "click",
                                            lambda _event=None, sid=shortcut.get("id"): record_prep_access(sid),
                                        )
