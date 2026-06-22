"""
Fiche Viewer — Synapse F-UI
-----------------------------
Composant double-niveau pour visualiser un cours :
  - Gauche (70 %) : PDF en iframe + onglets (Cours / Arbre décisionnel)
  - Droite (30 %) : Sidebar pièges EDN + lacunes actives

Usage :
    from frontend.components.fiche_viewer import render_fiche_viewer

    # Dans un contexte NiceGUI :
    render_fiche_viewer(
        course=course,
        traps=traps,          # list[DetectedTrap] depuis trap_detector
        weak_points=wps,      # list[dict] depuis local_store
    )

Si traps est vide et weak_points est vide, la fonction ne rend rien.
"""
from __future__ import annotations

from nicegui import ui

from backend.core.notion.models import Cours


def render_fiche_viewer(
    course: Cours,
    traps: list,
    weak_points: list,
    height: str = "600px",
) -> None:
    """
    Affiche le viewer double-panneau.
    Ne rend rien si aucun piège ni lacune.
    """
    trap_edn = [
        wp for wp in weak_points
        if (wp.get("category") or "") == "Piège EDN"
    ] if weak_points else []

    all_traps = list(traps or []) + trap_edn
    active_lacunes = [
        wp for wp in (weak_points or [])
        if (wp.get("category") or "") != "Piège EDN"
        and (wp.get("status") or "") not in ("résolue",)
    ]

    if not all_traps and not active_lacunes:
        return

    with ui.splitter(value=70).classes("fiche-viewer").style(
        f"min-height: {height}"
    ) as splitter:

        # ── Panneau gauche : cours ────────────────────────────────────────────
        with splitter.before:
            with ui.tabs().classes("tabs-primary").props("dense") as tabs:
                tab_cours = ui.tab("COURS")
                tab_arbre = ui.tab("ARBRE DÉCISIONNEL")

            with ui.tab_panels(tabs, value=tab_cours).classes(
                "w-full"
            ).style(f"height: calc({height} - 48px)"):

                with ui.tab_panel(tab_cours).classes("p-0 h-full"):
                    pdf_url = course.url_pdf or course.url_pdf_ue
                    if pdf_url:
                        ui.element("iframe").props(
                            f'src="/pdf/{course.id}" '
                            f'width="100%" '
                            f'style="height:100%;border:none;min-height:520px"'
                        ).classes("w-full h-full")
                    else:
                        with ui.column().classes(
                            "w-full h-full items-center justify-center gap-3 text-slate-400 p-8"
                        ):
                            ui.icon("picture_as_pdf", size="xl").classes("opacity-30")
                            ui.label("Aucun PDF lié à ce cours").classes(
                                "text-sm font-medium"
                            )
                            if course.url_pdf:
                                ui.button(
                                    "Ouvrir PDF",
                                    icon="open_in_new",
                                    on_click=lambda: ui.navigate.to(
                                        f"/pdf/{course.id}", new_tab=True
                                    ),
                                ).props("unelevated rounded size=sm color=red")

                with ui.tab_panel(tab_arbre).classes("p-4 h-full overflow-y-auto"):
                    _render_decision_tree_placeholder(course)

        # ── Panneau droit : pièges ────────────────────────────────────────────
        with splitter.after:
            with ui.column().classes("trap-sidebar w-full h-full overflow-y-auto").style(
                f"height: {height}"
            ):
                _render_trap_sidebar(all_traps, active_lacunes)


# ── Sidebar pièges ─────────────────────────────────────────────────────────────

def _render_trap_sidebar(traps: list, lacunes: list) -> None:
    """Affiche la sidebar : pièges EDN + lacunes actives."""

    # Pièges EDN
    if traps:
        ui.label(f"⚠ PIÈGES EDN ({len(traps)})").classes("sidebar-header danger")

        for trap in traps:
            # Support DetectedTrap dataclass et dict
            if isinstance(trap, dict):
                text     = (trap.get("detail") or "").strip()
                severity = trap.get("severity", 4)
            else:
                text     = getattr(trap, "text", "").strip()
                severity = getattr(trap, "severity", 4)

            if not text:
                continue

            _sev_color = {5: "#FF3B30", 4: "#FF453A", 3: "#FF9500"}.get(severity, "#FF9500")
            with ui.card().classes("trap-card w-full").style(
                f"border-left-color: {_sev_color}"
            ):
                with ui.row().classes("items-start gap-2 w-full"):
                    ui.badge(str(severity), color="red" if severity >= 4 else "orange").classes(
                        "text-[11px] shrink-0 mt-0.5"
                    )
                    ui.label(text[:200] + ("…" if len(text) > 200 else "")).classes(
                        "trap-text flex-1 min-w-0"
                    )

    # Lacunes actives (non-piège)
    if lacunes:
        if traps:
            ui.separator().classes("my-2")
        ui.label(f"LACUNES ({len(lacunes)})").classes("sidebar-header warning")

        for wp in lacunes[:8]:
            detail   = (wp.get("detail") or "").strip()
            cat      = (wp.get("category") or "").strip()
            severity = wp.get("severity", 2)
            sev_col  = "red" if severity >= 4 else "orange" if severity == 3 else "slate"

            with ui.element("div").classes(
                "w-full px-2 py-2 rounded border border-orange-100 dark:border-orange-900/30 "
                "bg-orange-50 dark:bg-orange-900/10"
            ):
                with ui.row().classes("items-start gap-2 w-full"):
                    ui.badge(str(severity), color=sev_col).classes("text-[11px] shrink-0 mt-0.5")
                    with ui.column().classes("gap-0 min-w-0"):
                        ui.label(
                            detail[:100] + ("…" if len(detail) > 100 else "")
                        ).classes("lacune-text")
                        if cat:
                            ui.label(cat).classes(
                                "text-[11px] text-orange-500 font-semibold mt-0.5"
                            )


# ── Arbre décisionnel placeholder ─────────────────────────────────────────────

def _render_decision_tree_placeholder(course: Cours) -> None:
    """Placeholder pour l'arbre décisionnel (à enrichir par cours)."""
    with ui.column().classes("w-full items-center gap-4 py-8 text-slate-400"):
        ui.icon("account_tree", size="xl").classes("opacity-30")
        ui.label("Arbre décisionnel").classes("text-sm font-semibold")
        ui.label(
            "L'arbre décisionnel pour ce cours n'est pas encore disponible."
        ).classes("text-xs text-center max-w-xs")
        if course.agregation_fiche_edn:
            ui.button(
                "Voir la Fiche EDN",
                icon="auto_stories",
                on_click=lambda u=course.agregation_fiche_edn: ui.navigate.to(u, new_tab=True),
            ).props("outline rounded size=sm color=teal").classes("mt-2")


# ── Composant autonome "Pièges" (card insertable) ─────────────────────────────

def render_traps_card(course: Cours, traps: list, weak_points: list) -> None:
    """
    Version card compacte du viewer pièges, sans le PDF.
    Idéal pour l'intégrer dans course_detail.py sans splitter.
    """
    trap_edn = [
        wp for wp in (weak_points or [])
        if (wp.get("category") or "") == "Piège EDN"
    ]
    all_traps = list(traps or []) + trap_edn

    if not all_traps:
        return

    with ui.card().classes(
        "w-full p-4 rounded-2xl shadow-sm border border-red-100 dark:border-red-900/30"
    ):
        with ui.row().classes("items-center gap-2 mb-3"):
            ui.icon("warning", size="xs").classes("text-red-500")
            ui.label(f"PIÈGES EDN ({len(all_traps)})").classes(
                "text-[11px] font-bold tracking-widest text-red-500 uppercase"
            )

        with ui.column().classes("gap-2 w-full"):
            for trap in all_traps[:6]:
                if isinstance(trap, dict):
                    text     = (trap.get("detail") or "").strip()
                    severity = trap.get("severity", 4)
                else:
                    text     = getattr(trap, "text", "").strip()
                    severity = getattr(trap, "severity", 4)

                if not text:
                    continue

                sev_col = "red" if severity >= 4 else "orange"
                with ui.element("div").classes(
                    "w-full p-2.5 rounded-lg border border-red-100 dark:border-red-900/30 "
                    "bg-red-50 dark:bg-red-900/10"
                ).style("border-left: 3px solid var(--color-trap, #FF453A)"):
                    with ui.row().classes("items-start gap-2 w-full"):
                        ui.badge(str(severity), color=sev_col).classes(
                            "text-[11px] shrink-0 mt-0.5"
                        )
                        ui.label(
                            text[:120] + ("…" if len(text) > 120 else "")
                        ).classes("text-xs text-slate-800 dark:text-slate-100 leading-snug flex-1")

        if len(all_traps) > 6:
            ui.label(f"+{len(all_traps) - 6} autres pièges non affichés").classes(
                "text-[11px] text-red-400 mt-2 text-right w-full"
            )
