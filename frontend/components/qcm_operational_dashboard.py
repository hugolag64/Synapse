"""Cartes de décision opérationnelle pour le cockpit QCM."""

from __future__ import annotations

from nicegui import ui

from backend.core.qcm.operational_dashboard import get_operational_dashboard


def _card_title(title: str, definition: str) -> None:
    ui.label(title).classes("text-sm font-semibold")
    ui.label(definition).classes("text-xs text-slate-500 min-h-[32px]")


def _empty(message: str) -> None:
    ui.label(message).classes("text-xs text-slate-500 italic")


def render_operational_dashboard(container) -> None:
    """Rend les cinq indicateurs et la décision qu'ils déclenchent."""
    container.clear()
    with container:
        ui.label("INDICATEURS OPÉRATIONNELS").classes("qc-label")
        ui.label(
            "Des signaux pour décider quoi réviser, comment et à quel rythme — sans score fabriqué."
        ).classes("text-xs text-slate-500 mb-3")
        try:
            dashboard = get_operational_dashboard()
        except Exception as exc:  # pragma: no cover - garde de production
            ui.label(f"Indicateurs momentanément indisponibles : {exc}").classes("text-xs text-red-600")
            return

        with ui.element("div").classes("grid grid-cols-1 md:grid-cols-2 xl:grid-cols-5 gap-3"):
            rank_a = dashboard["rank_a"]
            with ui.card().classes("p-3 gap-2 border border-slate-200 dark:border-slate-700"):
                _card_title("Rang A", "Propositions officielles effectivement cochées")
                ui.label(
                    f"{rank_a['percent']} %" if rank_a["percent"] is not None else "Données insuffisantes"
                ).classes("text-xl font-bold")
                if rank_a["items"]:
                    ui.label(" · ".join(f"{row['item_number']} : {row['percent']} %" for row in rank_a["items"][:3])).classes(
                        "text-xs text-slate-600 dark:text-slate-300"
                    )
                else:
                    _empty("Attendre des rangs officiels et des réponses.")
                ui.label("Décision : sécuriser les items les plus faibles.").classes("text-xs text-primary")

            discordance = dashboard["discordance"]
            with ui.card().classes("p-3 gap-2 border border-slate-200 dark:border-slate-700"):
                _card_title("Discordances", "Omission contre excès dans les corrections")
                if discordance["available"]:
                    ui.label(
                        f"Omission {discordance['omission_percent']} % · Excès {discordance['exces_percent']} %"
                    ).classes("text-base font-bold")
                    ui.label(f"Profil dominant : {discordance['dominant']}").classes("text-xs")
                    ui.label(
                        " · ".join(f"{row['item_number']} : {row['dominant']}" for row in discordance["items"][:3])
                    ).classes("text-xs text-slate-600 dark:text-slate-300")
                else:
                    _empty("Pas encore de correction propositionnelle.")
                ui.label("Décision : réviser si omission, ralentir si excès.").classes("text-xs text-primary")

            rhythm = dashboard["rhythm"]
            with ui.card().classes("p-3 gap-2 border border-slate-200 dark:border-slate-700"):
                _card_title("Rythme", "Secondes par question, par format")
                if rhythm["formats"]:
                    for row in rhythm["formats"][:4]:
                        ui.label(
                            f"{row['format'].upper()} · {row['average_seconds']} s / cible {row['target_seconds']} s · {row['status']}"
                        ).classes("text-xs")
                else:
                    _empty("La durée apparaît après les prochaines réponses.")
                ui.label("Décision : entraîner le format qui dépasse sa cible.").classes("text-xs text-primary")

            coverage = dashboard["coverage"]
            with ui.card().classes("p-3 gap-2 border border-slate-200 dark:border-slate-700"):
                _card_title("Couverture × fréquence", "Indispensables EDNpro jamais travaillés")
                ui.label(
                    f"{coverage['uncovered_count']} à ouvrir / {coverage['indispensable_count']} indispensables"
                    if coverage["available"]
                    else "Fréquence EDNpro indisponible"
                ).classes("text-xl font-bold")
                if coverage["items"]:
                    ui.label(" · ".join(f"ITEM {row['item_number']} ({row['question_count']} Q)" for row in coverage["items"][:3])).classes(
                        "text-xs text-slate-600 dark:text-slate-300"
                    )
                else:
                    _empty("Tout est couvert, ou aucune fréquence n'est chargée.")
                ui.label("Décision : commencer par le premier item de la liste.").classes("text-xs text-primary")

            replay = dashboard["replay"]
            with ui.card().classes("p-3 gap-2 border border-slate-200 dark:border-slate-700"):
                _card_title("Courbe de reprise", "Score d'une même session à J+n")
                if replay["chains"]:
                    for chain in replay["chains"][:2]:
                        scores = " → ".join(f"J+{point['day_offset']} {point['score_percent']:g} %" for point in chain["points"])
                        ui.label(f"ITEM {chain['item_number'] or '—'} · {scores}").classes("text-xs")
                else:
                    _empty("Rejouer une session pour mesurer la tenue.")
                ui.label("Décision : rejouer si le score ne tient pas.").classes("text-xs text-primary")
