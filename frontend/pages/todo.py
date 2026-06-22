from nicegui import ui
from backend.core.notion.service import notion_service
from backend.core.notion.models import DailyFollowUp, Cours
from backend.core.google.calendar_service import calendar_service
from backend.state.store import data_store
from frontend.theme import frame
import asyncio
import datetime

async def todo_page():
    with frame("Suivi Quotidien"):
        # Tabs - Light style to match other views
        with ui.tabs().classes('w-full text-slate-800 dark:text-slate-100 bg-slate-100 dark:bg-slate-900 border-b border-slate-200 dark:border-slate-800') as tabs:
            tab_daily = ui.tab('Suivi Quotidien')
            tab_review = ui.tab('Cours à réviser')

        # TAB PANELS
        # Widen: remove 'max-w-3xl mx-auto' to allow full width
        with ui.tab_panels(tabs, value=tab_daily).classes('w-full px-4 bg-transparent'):
            
            # --- TAB 1: SUIVI QUOTIDIEN ---
            with ui.tab_panel(tab_daily).classes('p-0 bg-transparent'): 
                
                # Container for the content - full width, very compact gap
                daily_container = ui.column().classes('w-full gap-1')
                
                with daily_container:
                    
                    # --- REUSABLE RENDER FUNCTION ---
                    async def render_day_view(container, date_obj):
                         # 1. Loading UI (Spinner)
                         container.clear()
                         with container:
                             with ui.column().classes('w-full h-64 items-center justify-center'):
                                 ui.spinner('dots', size='xl').classes('text-primary')
                                 ui.label("Chargement du suivi...").classes('text-gray-400 animate-pulse text-lg')
                         
                         # Artificial delay to ensure spinner is seen and UI updates
                         await asyncio.sleep(0.3)
                         
                         # 2. Fetch Data
                         task = await notion_service.get_daily_task_by_date(date_obj)
                         
                         if container.is_deleted: return
                         container.clear()
                         
                         with container:
                             if not task:
                                 with ui.column().classes('w-full items-center justify-center gap-4 py-8'):
                                     ui.icon('event_busy', size='4rem', color='grey-4')
                                     ui.label(f"Pas de fiche pour le {date_obj.strftime('%d/%m/%Y')}").classes('text-2xl text-gray-400')
                                     
                                     async def create_daily_card():
                                         ui.notify("Création en cours...", type='ongoing')
                                         if await notion_service.create_daily_task(date_obj, f"Suivi - {date_obj.strftime('%d/%m/%Y')}"):
                                             ui.notify("Fiche créée !", type='positive')
                                             await render_day_view(container, date_obj)
                                         else:
                                             ui.notify("Erreur lors de la création", type='negative')
                                             
                                     ui.button("Créer la fiche", on_click=create_daily_card).classes('bg-primary text-white text-lg')
                                 return

                             # --- Task Header ---
                             with ui.row().classes('w-full items-center justify-between mb-0'):
                                 ui.label(task.title).classes('text-3xl font-bold text-slate-800 dark:text-slate-100')
                                 with ui.row().classes('items-center gap-2'):
                                     ui.chip(task.status or "À faire", color='primary').classes('text-white text-base font-bold')
                                     ui.label(date_obj.strftime('%d/%m/%Y')).classes('text-gray-400 text-base')

                             # --- Progress Bar ---
                             total = len(task.checkboxes) + len(task.dynamic_checkboxes)
                             done = sum(task.checkboxes.values()) + sum(d['checked'] for d in task.dynamic_checkboxes.values())
                             progress = done / total if total > 0 else 0
                             
                             pb = ui.linear_progress(value=progress, show_value=False).classes('h-3 rounded-full transition-all duration-500 mb-0')
                             lbl = ui.label(f"{int(progress*100)}%").classes('text-base text-gray-500 self-end mb-1')
                             
                             async def refresh_progress():
                                 if container.is_deleted: return
                                 s_check = sum(c.value for c in static_cbs)
                                 d_check = sum(c.value for c in dynamic_cbs)
                                 tot = len(static_cbs) + len(dynamic_cbs)
                                 p = (s_check + d_check) / tot if tot > 0 else 0
                                 pb.set_value(p)
                                 lbl.set_text(f"{int(p*100)}%")
                                 
                                 if p == 1.0:
                                     ui.notify("Objectifs atteints ! 🏆", type='positive')

                             # --- Static Checkboxes ---
                             static_cbs = []
                             # Denser grid: 4 cols on md, 5 on lg to reduce rows. Gap reduced to 2.
                             with ui.element('div').classes('grid grid-cols-2 md:grid-cols-4 lg:grid-cols-5 gap-2 w-full mb-1'):
                                 for key, val in task.checkboxes.items():
                                     async def toggle_static(e, k=key):
                                         await refresh_progress()  # Optimistic: update bar immediately
                                         async def _sync(tid=task.id, kk=k, sender=e.sender, val=e.value):
                                             if not await notion_service.toggle_daily_checkbox(tid, kk, val):
                                                 sender.value = not val
                                                 ui.notify("Erreur de synchronisation", type='negative')
                                         asyncio.create_task(_sync())
                                         
                                     # Bigger text: text-lg, but dense props to reduce height
                                     cb = ui.checkbox(key, value=val, on_change=toggle_static).props('dense').classes('text-lg text-slate-700 dark:text-slate-200')
                                     static_cbs.append(cb)

                             # --- Dynamic Checkboxes ---
                             dynamic_cbs = []
                             if task.dynamic_checkboxes:
                                 ui.label("Tâches Personnalisées").classes('text-base font-bold text-gray-400 uppercase tracking-wider mb-0 mt-1')
                                 # Use same grid for dynamic tasks too to be compact
                                 with ui.element('div').classes('grid grid-cols-2 md:grid-cols-4 lg:grid-cols-5 gap-2 w-full mb-1'):
                                     for b_id, data in task.dynamic_checkboxes.items():
                                         async def toggle_dynamic(e, bid=b_id):
                                             await refresh_progress()  # Optimistic: update bar immediately
                                             async def _sync(bb=bid, sender=e.sender, val=e.value):
                                                 if not await notion_service.toggle_dynamic_task(bb, val):
                                                     sender.value = not val
                                                     ui.notify("Erreur de synchronisation", type='negative')
                                             asyncio.create_task(_sync())
                                             
                                         dcb = ui.checkbox(data['text'], value=data['checked'], on_change=toggle_dynamic).props('dense').classes('text-lg text-slate-700 dark:text-slate-200')
                                         dynamic_cbs.append(dcb)
                                         
                             # --- Add Task Input ---
                             with ui.row().classes('w-full items-center gap-2 mb-1 bg-gray-50 dark:bg-slate-800 p-1 rounded-lg border border-gray-100 dark:border-slate-700'):
                                 new_input = ui.input(placeholder="Ajouter une tâche personnalisée...").props('dense outlined rounded').classes('flex-grow text-base dark:text-slate-100')
                                 async def add_new_task():
                                     val = new_input.value
                                     if not val.strip(): return
                                     new_input.value = ""
                                     if await notion_service.add_dynamic_task(task.id, val):
                                         ui.notify("Tâche ajoutée", type='positive')
                                         await render_day_view(container, date_obj) 
                                 
                                 ui.button(icon='add', on_click=add_new_task).props('round flat dense sm').classes('text-primary')

                             # --- Notes Section ---
                             ui.separator().classes('mb-1')
                             ui.label("📝 Notes & Réflexions").classes('text-xl font-bold text-slate-800 dark:text-slate-100 mb-0')
                             note_input = ui.textarea(placeholder="Comment s'est passée la journée ?").classes('w-full mb-1 text-base dark:text-slate-100').props('outlined rounded rows=3 dense')
                             async def save_note():
                                 val = note_input.value
                                 if not val.strip(): return
                                 note_input.value = ""
                                 ui.notify("Enregistrement...", type='ongoing', spinner=True)
                                 if await notion_service.add_daily_comment(task.id, val):
                                     ui.notify("Note enregistrée", type='positive')
                                 else:
                                     ui.notify("Erreur", type='negative')
                             ui.button("Envoyer la note", on_click=save_note).props('unelevated color=indigo rounded').classes('self-end')

                    # --- Navigation Buttons & Context ---
                    today_date = datetime.date.today()
                    tomorrow_date = today_date + datetime.timedelta(days=1)
                    after_tomorrow_date = today_date + datetime.timedelta(days=2)
                    
                    # Content Area
                    content_area = ui.column().classes('w-full p-4 border rounded-lg border-slate-200 dark:border-slate-800 shadow-sm min-h-[400px]')
                    
                    # Buttons
                    with ui.row().classes('w-full items-center justify-center gap-4 mb-4'):
                        
                        async def switch_view(date_target, btn_ref):
                            # Reset all buttons styles
                            btn_today.props('outline')
                            btn_tomorrow.props('outline')
                            btn_after.props('outline')
                            
                            # Highlight selected
                            btn_ref.props(remove='outline')
                            btn_ref.classes('bg-primary text-white')
                            
                            # Render
                            await render_day_view(content_area, date_target)

                        # We use lambda to capture buttons, but buttons are defined after... so we need to define them first or use `sender`
                        # Let's define buttons and then bind clicks.
                        
                        btn_today = ui.button("Aujourd'hui", on_click=lambda e: switch_view(today_date, e.sender))
                        btn_tomorrow = ui.button("Demain", on_click=lambda e: switch_view(tomorrow_date, e.sender))
                        btn_after = ui.button("Après-demain", on_click=lambda e: switch_view(after_tomorrow_date, e.sender))
                        
                        # Initial Style (active tab is Today)
                        btn_today.classes('bg-primary text-white') # Active
                        btn_tomorrow.props('outline')
                        btn_after.props('outline')

                    # Initial Render
                    ui.timer(0.1, lambda: render_day_view(content_area, today_date), once=True)

            # --- TAB 2: COURS À RÉVISER ---
            with ui.tab_panel(tab_review).classes('p-4 gap-6 bg-transparent'):
                review_content = ui.column().classes('w-full')
                
                async def load_reviews():
                    # Show loading spinner if content is empty
                    if not list(review_content):
                        with review_content:
                            ui.spinner('dots', size='lg').classes('self-center text-primary')

                    today_task = None
                    events = []
                    try:
                        # 1. Parallel Fetch: Today's Task & GCal Events
                        task_future = asyncio.create_task(notion_service.get_today_task())
                        # Use get_events_for_day
                        events_future = asyncio.create_task(calendar_service.get_events_for_day(datetime.date.today()))
                        
                        today_task, events = await asyncio.gather(task_future, events_future)
                    except Exception as e:
                        print(f"Error loading reviews data: {e}")
                        ui.notify(f"Erreur chargement données: {e}", type='negative')
                    
                    # 2. Sequential: Reviewed Courses & Manual Revisions (depends on task)
                    reviewed_titles = []
                    manual_titles = []
                    if today_task:
                        reviewed_titles = await notion_service.get_daily_reviewed_courses(today_task.id)
                        manual_titles = await notion_service.get_daily_manual_revision_courses(today_task.id)

                    if review_content.is_deleted:
                        return

                    # 3. Render
                    review_content.clear()
                    with review_content:
                        ui.label("📅 Cours à réviser aujourd'hui").classes('text-xl font-bold text-slate-800 dark:text-slate-100 mb-4')
                        
                        relevant_courses = []

                        # A. Process GCal Events
                        if events:
                             for evt in events:
                                summary = evt.get('summary', '')
                                # Check for "Collège" only (Manual ones handled via Notion now)
                                # But keep "Révision Manuelle" check just in case legacy events exist
                                if "Collège" in summary or "Révision Manuelle" in summary:
                                    matched_course = None
                                    for c in data_store.cours:
                                        if c.title in summary:
                                            matched_course = c
                                            break
                                    if matched_course:
                                        # Use a flag to know source? Or just append.
                                        relevant_courses.append({'summary': summary, 'course': matched_course, 'type': 'gcal'})

                        # B. Process Manual Revisions from Notion
                        if manual_titles:
                            for title in manual_titles:
                                matched_course = next((c for c in data_store.cours if c.title == title), None)
                                if matched_course:
                                    # Avoid duplicates if it's already in GCal list (unlikely based on new logic but good safety)
                                    if not any(item['course'].id == matched_course.id for item in relevant_courses):
                                         relevant_courses.append({'summary': f"Manuel : {title}", 'course': matched_course, 'type': 'notion_manual'})

                        if not relevant_courses:
                             ui.label("Aucun cours à réviser pour le moment.").classes('text-slate-500 dark:text-slate-400 italic')
                        
                        for item in relevant_courses:
                            summary = item['summary']
                            course = item['course']
                            source_type = item['type']
                            
                            is_reviewed = course.title in reviewed_titles
                            
                            card_classes = 'w-full p-4 border-l-4 mb-2 shadow-sm ' + ('border-green-500 bg-green-50 dark:bg-green-900/20' if is_reviewed else 'border-blue-500')
                            
                            with ui.card().classes(card_classes) as card_ui:
                                with ui.row().classes('w-full items-center justify-between'):
                                    with ui.column().classes('gap-1'):
                                        ui.label(summary).classes('font-bold text-slate-800 dark:text-slate-100' + (' line-through opacity-50' if is_reviewed else ''))
                                        ui.label(f"Lecture actuelle: {course.nb_lectures}").classes('text-xs text-slate-500 dark:text-slate-400')
                                    
                                    if is_reviewed:
                                        ui.icon('check_circle', color='green', size='md')
                                    else:
                                        async def on_check_course(c=course, card_ui=card_ui, src=source_type):
                                            # 0. Immediate Feedback
                                            if card_ui:
                                                card_ui.classes('bg-green-100 scale-95 transition-all duration-500')
                                                
                                            # 1. Update Notion Counter
                                            ui.notify(f"Validation de {c.title}...", type='ongoing')
                                            ok_inc = await notion_service.increment_lecture_college(c.id, c.nb_lectures)
                                            
                                            # 2. Update Daily Page (Add 'Révisé' or Update 'Manuel')
                                            t_task = await notion_service.get_today_task()
                                            ok_daily = False
                                            if t_task:
                                                if src == 'notion_manual':
                                                    # Transform the manual block into 'Révisé'
                                                    ok_daily = await notion_service.mark_manual_revision_done(t_task.id, c.title)
                                                else:
                                                    # Just append 'Révisé'
                                                    ok_daily = await notion_service.add_course_to_daily_reviewed(t_task.id, c.title)
                                            else:
                                                ui.notify("Pas de fiche journalière trouvée !", type='warning')

                                            if ok_inc:
                                                c.nb_lectures += 1
                                            
                                            if card_ui and (ok_inc or ok_daily):
                                                ui.notify("Validé avec succès !", type='positive')
                                                # Animate out
                                                card_ui.style('transform: translateX(100%); opacity: 0; transition: all 0.5s ease-in-out;')
                                                await asyncio.sleep(0.5)
                                                
                                                # Rebuild as "Done"
                                                card_ui.style('transform: none; opacity: 1;')
                                                card_ui.classes(remove='border-blue-500 transition-all scale-95', add='border-green-500 bg-green-50 dark:bg-green-900/20')
                                                card_ui.clear()
                                                with card_ui:
                                                    with ui.row().classes('w-full items-center justify-between'):
                                                        with ui.column().classes('gap-1'):
                                                            ui.label(c.title).classes('font-bold text-slate-800 dark:text-slate-100 line-through opacity-50')
                                                            ui.label(f"Lecture actuelle: {c.nb_lectures}").classes('text-xs text-slate-500 dark:text-slate-400')
                                                        ui.icon('check_circle', color='green', size='md')
                                                
                                        ui.button(icon='check', on_click=lambda c=course, card=card_ui, s=source_type: on_check_course(c, card, s)).props('flat round color=green').tooltip("Marquer comme fait")

                # Defer loading to allow UI to render first (Optimistic UI)
                ui.timer(0.1, load_reviews, once=True)

                # --- MANUAL SCHEDULING ---
                ui.separator().classes('my-6')
                with ui.column().classes('w-full'):
                    ui.label("➕ Programmer une révision").classes('text-lg font-bold text-slate-800 dark:text-slate-100 mb-2')
                    
                    # Course Selector
                    college_courses = [c for c in data_store.cours if c.college]
                    def sort_key(c):
                        if c.item_number:
                            try:
                                return float(c.item_number.replace(',', '.'))
                            except:
                                return 999999
                        return 999999
                    
                    college_courses.sort(key=sort_key)
                    
                    options_dict = {}
                    for c in college_courses:
                        prefix = f"ITEM {c.item_number} - " if c.item_number else ""
                        label = f"{prefix}{c.title}"
                        options_dict[c.id] = label
                    
                    selected_course_id = {'value': None}
                    
                    # 1. Search Row
                    ui.select(options=options_dict, label="Rechercher un cours (ex: ITEM 123...)", with_input=True).bind_value(selected_course_id, 'value').classes('w-full').props('outlined use-input clearable behaviour="menu"')

                    # 2. Date & Action Row
                    with ui.row().classes('w-full items-center justify-between gap-4 mt-2'):
                        
                        # Date Buttons
                        with ui.row().classes('items-center gap-2'):
                            date_choice = {'value': None}
                            def set_date(days, btn):
                                 d = datetime.date.today() + datetime.timedelta(days=days)
                                 date_choice['value'] = d
                                 ui.notify(f"Date sélectionnée : {d.strftime('%d/%m/%Y')}", type='info')

                            ui.button("Aujourd'hui", on_click=lambda e: set_date(0, e.sender)).props('outline small')
                            ui.button("Demain", on_click=lambda e: set_date(1, e.sender)).props('outline small')
                            ui.button("Après-demain", on_click=lambda e: set_date(2, e.sender)).props('outline small')
                        
                        # Action Button
                        async def schedule_revision():
                            if not selected_course_id['value']:
                                ui.notify("Veuillez sélectionner un cours", type='warning')
                                return
                            if not date_choice['value']:
                                ui.notify("Veuillez choisir une date", type='warning')
                                return
                            
                            c = next((x for x in college_courses if x.id == selected_course_id['value']), None)
                            if not c: return
                            
                            target_date = date_choice['value']
                            ui.notify("Programmation...", type='ongoing')
                            
                            # Logic: Add manual entry to Notion Daily Page
                            # 1. Find/Create Daily Page for target date
                            target_task = await notion_service.get_daily_task_by_date(target_date)
                            if not target_task:
                                ui.notify(f"Création de la fiche journalière pour {target_date.strftime('%d/%m')}...", type='info')
                                created = await notion_service.create_daily_task(target_date, f"Suivi - {target_date.strftime('%d/%m/%Y')}")
                                if created:
                                    target_task = await notion_service.get_daily_task_by_date(target_date)
                                else:
                                    ui.notify("Impossible de créer la fiche journalière.", type='negative')
                                    return
                            
                            # 2. Add manual revision block
                            if target_task:
                                res = await notion_service.add_course_to_daily_manual(target_task.id, c.title)
                                if res:
                                     ui.notify("Programmé avec succès (Notion) !", type='positive')
                                     if target_date == datetime.date.today():
                                         await load_reviews()
                                     
                                     selected_course_id['value'] = None
                                     date_choice['value'] = None
                                else:
                                     ui.notify("Erreur lors de l'ajout à Notion", type='negative')
                            else:
                                ui.notify("Erreur technique: Fiche introuvable.", type='negative')

                        ui.button("PROGRAMMER", on_click=schedule_revision).props('unelevated color=indigo rounded').classes('font-bold')
