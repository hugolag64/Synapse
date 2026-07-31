from nicegui import ui
from frontend.theme import frame
from frontend.components.course_card import CourseCard
from backend.state.store import data_store
from backend.core.notion.service import notion_service
import asyncio
import datetime

@ui.page('/semestres')
@frame('Semestres')
def semestres_page():
    if not data_store.is_loaded:
        ui.label("Chargement des données...").classes("text-slate-500")
        return

    # ── Vue cockpit ───────────────────────────────────────────────────────────
    from frontend.pages.semestres_cockpit import render_semestres_cockpit
    render_semestres_cockpit()
    return

    current_tab = {'value': None}  # semestre actif
    content = ui.column().classes('w-full')

    # --- Helpers ---

    def _refresh_view():
        show_content()

    # Les fonctions open_link_pdf_dialog_ue et set_reminders_ue
    # ont été unifiées dans frontend/components/course_quick_actions.py

    # --- Render ---

    def show_content():
        content.clear()
        try:
            parent_client = ui.context.client
        except Exception:
            parent_client = None

        with content:
            # Construire hiérarchie Semestre -> UE -> Cours
            hierarchy = {}
            for cours in data_store.cours:
                # Ignorer les ressources purement "Collège" qui ne sont pas rattachées à une UE
                if not cours.ue_id:
                    continue
                    
                semestre = cours.semestre if cours.semestre else "Non classé"
                ue_nom = "Sans UE"

                if cours.ue_id and cours.ue_id in data_store.ues_map:
                    ue_data = data_store.ues_map[cours.ue_id]
                    ue_nom = ue_data.get("nom") or "Sans UE"
                    if semestre == "Non classé" and ue_data.get("semestre"):
                        semestre = ue_data.get("semestre")

                hierarchy.setdefault(semestre, {}).setdefault(ue_nom, []).append(cours)

            if not hierarchy:
                with ui.column().classes('w-full items-center mt-12 gap-4'):
                    ui.icon('school', size='4rem', color='slate-300')
                    ui.label("Aucun cours trouvé.").classes("italic text-slate-500 text-lg")
                return

            sorted_semestres = sorted(hierarchy.keys())

            # Si aucun onglet actif, prendre le premier
            if not current_tab['value'] or current_tab['value'] not in hierarchy:
                current_tab['value'] = sorted_semestres[0]

            # En-tête
            with ui.row().classes('w-full justify-between items-end mb-2'):
                ui.label('Semestres').classes('text-2xl font-bold text-slate-800 dark:text-slate-100')
                refresh_btn_sem = ui.button(icon='refresh').props('flat round dense').tooltip('Synchroniser Notion')

                async def refresh_data():
                    refresh_btn_sem.props(add='loading')
                    try:
                        await data_store.refresh()
                        show_content()
                        ui.notify("Données à jour ✓", type='positive', timeout=1500)
                    except Exception as e:
                        ui.notify(f"Erreur sync : {e}", type='negative')
                    finally:
                        refresh_btn_sem.props(remove='loading')

                refresh_btn_sem.on_click(refresh_data)

            # Onglets Semestres
            with ui.row().classes('flex flex-wrap gap-2 mb-6'):
                for sem in sorted_semestres:
                    is_active = (sem == current_tab['value'])
                    color_cls = 'bg-indigo-500 text-white border-indigo-600 font-bold' if is_active else 'bg-slate-50 dark:bg-slate-800 text-slate-700 dark:text-slate-300 border-slate-200 dark:border-slate-700 hover:bg-slate-100 dark:hover:bg-slate-700'
                    nb = sum(len(v) for v in hierarchy[sem].values())
                    with ui.card().classes(f'cursor-pointer px-4 py-2 rounded shadow-sm text-sm border transition-colors {color_cls}').on('click', lambda s=sem: (current_tab.update({'value': s}), show_content())):
                        ui.label(f"{sem}  ({nb})")

            # Contenu du semestre actif
            sem_data = hierarchy[current_tab['value']]

            # --- SYSTÈME DE FILTRE PAR UE ---
            ues_du_semestre = list(sem_data.keys())
            if "Sans UE" in ues_du_semestre:
                ues_du_semestre.remove("Sans UE")
                ues_du_semestre.sort()
                ues_du_semestre.append("Sans UE")
            else:
                ues_du_semestre.sort()
            
            options_filtre = ["Toutes les UE"] + ues_du_semestre
            
            with ui.row().classes('w-full items-center mb-6 bg-slate-50 dark:bg-slate-900 p-3 rounded-md border dark:border-slate-800'):
                ui.icon('filter_alt').classes('text-xl text-slate-500')
                ui.label('Filtrer par unité d\'enseignement :').classes('font-medium text-slate-700 dark:text-slate-300')
                filtre_ue = ui.select(
                    options=options_filtre, 
                    value="Toutes les UE"
                ).classes('w-72 bg-white dark:bg-slate-800')

            conteneur_ue = ui.column().classes('w-full gap-6')

            def rafraichir_vue_ue(nom_ue_filtree):
                conteneur_ue.clear()
                with conteneur_ue:
                    for ue_nom in ues_du_semestre:
                        if nom_ue_filtree != "Toutes les UE" and ue_nom != nom_ue_filtree:
                            continue
                            
                        cours_list = sem_data[ue_nom]
                        cours_list.sort(key=lambda x: x.created_time, reverse=True)

                        # Section UE
                        with ui.column().classes('w-full mb-6 gap-3'):
                            # Titre UE
                            with ui.row().classes('w-full items-center gap-3 border-b-2 border-indigo-100 dark:border-indigo-900/50 pb-1'):
                                ui.icon('menu_book', color='indigo').classes('text-xl')
                                ui.label(ue_nom).classes('text-base font-bold text-indigo-600 dark:text-indigo-400 uppercase tracking-wider')
                                ui.badge(str(len(cours_list)), color='indigo').classes('ml-1')

                            # Cartes de cours — Responsive Tailwind Grid
                            with ui.grid().classes('grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 w-full'):
                                for cours in cours_list:
                                    CourseCard(
                                        cours,
                                        context="ue",
                                        refresh_fn=_refresh_view,
                                        client=parent_client,
                                    )

            rafraichir_vue_ue(filtre_ue.value)
            filtre_ue.on_value_change(lambda e: rafraichir_vue_ue(e.value))
    show_content()
