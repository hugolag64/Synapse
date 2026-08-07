"""Prépa hub: compact shortcuts for external preparation platforms."""

from __future__ import annotations

import asyncio
from collections import defaultdict
from pathlib import Path

from nicegui import ui

from backend.core.prep.catalog import list_prep_providers, list_prep_shortcuts, record_prep_access
from frontend.cockpit_shell import cockpit_frame

_CSS = """
.prep-wrap { max-width:980px; width:100%; }
.prep-title { font-size:20px; font-weight:600; color:var(--text); letter-spacing:-.01em; }
.prep-subtitle { color:var(--text-muted); font-size:12.5px; margin-top:4px; }
.prep-provider { border:1px solid var(--border); border-radius:8px; padding:14px 16px; background:var(--bg-alt); }
.prep-provider-name { font-size:14px; font-weight:600; color:var(--text); }
.prep-provider-meta { font-size:11.5px; color:var(--text-muted); }
.prep-section-title { font-size:11px; text-transform:uppercase; letter-spacing:.05em; color:var(--text-dim); font-weight:600; }
.prep-shortcut { border:1px solid var(--border); border-radius:8px; padding:13px 14px; background:var(--bg-alt); transition:border-color .12s, background .12s; }
.prep-shortcut:hover { border-color:var(--accent); background:var(--surface); }
.prep-shortcut-title { color:var(--text); font-size:13px; font-weight:600; }
.prep-shortcut-desc { color:var(--text-muted); font-size:11.5px; margin-top:3px; }
.prep-category { color:var(--text-muted); font-size:11px; text-transform:uppercase; letter-spacing:.04em; }
"""


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

    with cockpit_frame("Prépa"):
        with ui.column().classes("prep-wrap gap-0"):
            with ui.row().classes("w-full items-start justify-between gap-4 pb-5 border-b"):
                with ui.column().classes("gap-0"):
                    ui.label("Prépa").classes("prep-title")
                    ui.label("Tes plateformes et raccourcis de préparation, au même endroit.").classes("prep-subtitle")
                ui.button("Importer les EDN", icon="download", on_click=_run_ednpro_import).props(
                    "unelevated size=sm"
                ).style("background:var(--accent);color:var(--accent-text);border-radius:6px;font-size:12px;font-weight:600")

            with ui.column().classes("w-full gap-4 pt-6"):
                ui.label("Plateformes").classes("prep-section-title")
                for section in view["provider_sections"]:
                    with ui.element("section").classes("prep-provider w-full"):
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
                            with ui.column().classes("w-full gap-3 mt-4"):
                                for group in section["categories"]:
                                    ui.label(group["category"]).classes("prep-category")
                                    with ui.row().classes("w-full gap-2 flex-wrap"):
                                        for shortcut in group["shortcuts"]:
                                            with ui.link(target=shortcut["url"], new_tab=True).classes(
                                                "prep-shortcut flex-1 min-w-[220px] no-underline"
                                            ) as link:
                                                with ui.row().classes("items-start gap-2"):
                                                    ui.icon(shortcut.get("icon", "open_in_new")).classes(
                                                        "text-[var(--accent)] text-lg"
                                                    )
                                                    with ui.column().classes("gap-0"):
                                                        ui.label(shortcut["title"]).classes("prep-shortcut-title")
                                                        ui.label(shortcut.get("description", "")).classes("prep-shortcut-desc")
                                            link.on(
                                                "click",
                                                lambda _event=None, sid=shortcut.get("id"): record_prep_access(sid),
                                            )
