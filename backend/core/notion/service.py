from typing import List, Optional, Dict
from backend.core.notion.client import notion_client
from backend.core.notion.models import Cours, DailyFollowUp, NotionProperty
from backend.core.notion.payloads import checkbox, number, notion_date, url_prop, relation
from backend.config.settings import settings, NOTION_PROPS as P
from loguru import logger
from datetime import date
import asyncio

_today_task_lock: asyncio.Lock | None = None


def _get_today_task_lock() -> asyncio.Lock:
    global _today_task_lock
    if _today_task_lock is None:
        _today_task_lock = asyncio.Lock()
    return _today_task_lock


def _parse_item_page(page: dict) -> int | None:
    """Extrait le numéro d'item depuis une page Notion (multi-format, idempotent)."""
    props = page.get("properties", {})

    # 1. Propriété Number "ITEMS"
    p = props.get("ITEMS", {})
    if "number" in p and p["number"] is not None:
        try:
            return int(float(p["number"]))
        except (ValueError, TypeError):
            pass

    # 2. Propriété Title "Numéro de l'ITEM"
    p = props.get("Numéro de l'ITEM", {})
    if "title" in p and p["title"]:
        try:
            return int(float(p["title"][0]["plain_text"].replace(",", ".")))
        except (KeyError, IndexError, ValueError):
            pass

    # 3. Fallback propriété "ITEM" (number, rich_text ou title)
    p = props.get("ITEM", {})
    if "number" in p and p["number"] is not None:
        try:
            return int(float(p["number"]))
        except (ValueError, TypeError):
            pass
    if "rich_text" in p and p["rich_text"]:
        try:
            return int(float(p["rich_text"][0]["plain_text"].replace(",", ".")))
        except (KeyError, IndexError, ValueError):
            pass
    if "title" in p and p["title"]:
        try:
            return int(float(p["title"][0]["plain_text"].replace(",", ".")))
        except (KeyError, IndexError, ValueError):
            pass

    return None

class NotionService:
    
    async def get_all_ues_map(self) -> dict:
        """Récupère la base UE et crée un dictionnaire {id: {'nom': str, 'semestre': str}}."""
        if not settings.notion.ue_db_id:
            return {}
        logger.info("Fetching UEs map...")
        try:
            results = await notion_client.query_database(settings.notion.ue_db_id)
            ues_map = {}
            for page in results:
                props = page.get("properties", {})
                ues_map[page["id"]] = {
                    "nom": NotionProperty.extract_title(props.get("UE")),
                    "semestre": NotionProperty.extract_select(props.get("Semestre")),
                }
            logger.success(f"Loaded {len(ues_map)} UEs")
            return ues_map
        except Exception as e:
            logger.error(f"Failed to fetch UEs map: {e}")
            return {}

    async def get_all_cours(self) -> List[Cours]:
        """Fetch all Cours from the Cours Database."""
        logger.info("Fetching Cours...")
        results = await notion_client.query_database(settings.notion.cours_db_id)
        
        if not results:
             logger.warning(f"No results found for database {settings.notion.cours_db_id}")

        cours_list = []
        for page in results:
            try:
                cours_list.append(Cours.from_notion(page))
            except Exception as e:
                logger.warning(f"Failed to parse Cours page {page['id']}: {e}")
        
        logger.success(f"Successfully parsed {len(cours_list)} Cours")
        return cours_list

    async def get_updated_cours(self, since: str) -> List[Cours]:
        """Fetch Cours modified since the given ISO timestamp (delta sync)."""
        logger.info(f"Fetching Cours updated since {since}...")
        filter_params = {
            "timestamp": "last_edited_time",
            "last_edited_time": {"after": since},
        }
        results = await notion_client.query_database(
            settings.notion.cours_db_id, filter_params=filter_params
        )
        cours_list = []
        for page in results:
            try:
                cours_list.append(Cours.from_notion(page))
            except Exception as e:
                logger.warning(f"Failed to parse updated Cours page {page['id']}: {e}")
        logger.success(f"Found {len(cours_list)} updated Cours")
        return cours_list

    async def get_daily_tasks(self, since: str = None) -> List[DailyFollowUp]:
        """Fetch daily follow-up tasks."""
        # Optional: could add filter for date >= since if needed, but for now we might fetch "Active" tasks
        # Or fetch recent ones.
        # User requirement: "Archive everything < today". So we need to fetch tasks < today with Status != Terminé.
        
        # 1. Fetch tasks that are NOT "Terminé" (or everything and filter in python)
        # To avoid pagination limits, better to filter. 
        # But for maintenance, let's fetch everything that is "À faire" or "En cours"
        
        filter_params = {
            "or": [
                {"property": "Status", "status": {"equals": "À faire"}},
                {"property": "Status", "status": {"equals": "En cours"}}
            ]
        }
        
        # Also need to check if pages for Today/Tomorrow exist. 
        # So maybe we just fetch everything relevant?
        # Let's fetch "À faire" or "En cours" first for archiving.
        # And we need to check existence of specific dates.
        
        results = await notion_client.query_database(settings.notion.daily_db_id, filter_params=filter_params)
        tasks = []
        for page in results:
             tasks.append(DailyFollowUp.from_notion(page))
             
        # We also need to find if specific dates exist, even if they are "Terminé" (to avoid recreating them)
        # So we should probably query by Date range? Or just query everything Recent?
        # Let's query everything created/updated recently or with Date >= Today
        
        return tasks

    async def get_all_daily_tasks_for_check(self) -> List[DailyFollowUp]:
        """Fetch all tasks to check for existence of specific dates."""
        # Simple strategy: Fetch all recent tasks (last 30 days?) or just all if DB is small.
        # Let's fetch all for now, assuming 1 page per day, it's 365 pages/year. manageable.
        results = await notion_client.query_database(settings.notion.daily_db_id)
        if results:
            logger.info(f"DEBUG PROPERTIES: {list(results[0]['properties'].keys())}")
        return [DailyFollowUp.from_notion(p) for p in results]

    async def create_daily_task(self, date_obj: date, title: str, status: str = "À faire") -> bool:
        """Create a new Daily Follow-up page."""
        try:
             # Basic properties
             props = {
                 "Name": {"title": [{"text": {"content": title}}]}, # Title property is "Name"
                 "Date": {"date": {"start": date_obj.isoformat()}},
                 "Status": {"status": {"name": status}}
             }
             
             # Retrieve actual schema to only include existing checkbox properties
             db_schema = await notion_client.retrieve_database(settings.notion.daily_db_id)
             db_props = db_schema.get("properties", {})
             checkboxes = [
                 "🧠 Révision matin",
                 "🧠 Révision après-midi",
                 "✅ QCM",
                 "🥗 Alimentation saine",
                 "💧 Hydratation",
                 "👊 Sport",
                 "🧘 Mobilité",
                 "😴 Sommeil de qualité",
                 "📅 Planification rapide du lendemain",
                 "📅 Planification lendemain",
                 "📚 Lecture"
             ]
             missing = []
             for cb in checkboxes:
                 if cb in db_props:
                     props[cb] = {"checkbox": False}
                 else:
                     missing.append(cb)
             if missing:
                 logger.warning(f"Skipped unknown checkbox properties: {missing}")
                 
             # Default Content (Template mimicking)
             children = [
                {
                    "object": "block",
                    "type": "heading_1",
                    "heading_1": {
                        "rich_text": [{"type": "text", "text": {"content": "📚 Cours révisés"}}]
                    }
                },
                {
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {
                        "rich_text": [] # Empty block for spacing (saut de ligne)
                    }
                },
                {
                    "object": "block",
                    "type": "divider",
                    "divider": {}
                },
                {
                    "object": "block",
                    "type": "heading_2",
                    "heading_2": {
                        "rich_text": [{"type": "text", "text": {"content": "📝 Notes personnelles"}}]
                    }
                },
                {
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {
                        "rich_text": [] 
                    }
                }
             ]

             await notion_client.create_page(settings.notion.daily_db_id, props, children=children)
             logger.success(f"Created daily task: {title}")
             return True
        except Exception as e:
            # Log the full exception to help debug property name errors
            logger.error(f"Failed to create daily task {title}: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False

    async def update_task_status(self, page_id: str, status: str):
        """Update the status of a daily task."""
        try:
            await notion_client.update_page(page_id, {"Status": {"status": {"name": status}}})
            logger.info(f"Updated task {page_id} status to {status}")
            return True
        except Exception as e:
            logger.error(f"Failed to update task {page_id}: {e}")
            return False

    async def update_task_title(self, page_id: str, new_title: str):
        """Update the title of a daily task."""
        try:
            # Title property is "Name" as discovered
            await notion_client.update_page(page_id, {"Name": {"title": [{"text": {"content": new_title}}]}})
            logger.info(f"Updated task {page_id} title to {new_title}")
            return True
        except Exception as e:
            logger.error(f"Failed to update task title {page_id}: {e}")
            return False

    async def get_daily_task_by_date(self, date_obj: date) -> Optional[DailyFollowUp]:
        """Get the daily task for a specific date, including dynamic checkboxes from page content."""
        date_str = date_obj.isoformat()
        filter_params = {"property": "Date", "date": {"equals": date_str}}
        
        try:
            results = await notion_client.query_database(settings.notion.daily_db_id, filter_params=filter_params)
            if results:
                task = DailyFollowUp.from_notion(results[0])
                
                # Fetch children blocks to find dynamic tasks
                try:
                    response = await notion_client.retrieve_block_children(task.id)
                    blocks = response.get("results", [])
                    
                    for block in blocks:
                        if block.get("type") == "to_do":
                            todo = block["to_do"]
                            rich_text = todo.get("rich_text", [])
                            if rich_text:
                                content = rich_text[0].get("text", {}).get("content", "")
                                
                                # Filter out system managed tasks
                                if content.startswith("Révisé : ") or content.startswith("Manuel : "):
                                    continue
                                    
                                # This is a user custom task
                                task.dynamic_checkboxes[block["id"]] = {
                                    "text": content,
                                    "checked": todo.get("checked", False)
                                }
                except Exception as e:
                    logger.warning(f"Failed to fetch dynamic tasks for {date_str}: {e}")
                
                return task
            return None
        except Exception as e:
            logger.error(f"Failed to get daily task for {date_str}: {e}")
            return None

    def _get_formatted_date_title(self, date_obj: date) -> str:
        """Helper to formatting date title consistently (French months)."""
        months = [
            "janvier", "février", "mars", "avril", "mai", "juin",
            "juillet", "août", "septembre", "octobre", "novembre", "décembre"
        ]
        month_name = months[date_obj.month - 1]
        return f"{date_obj.day:02d} {month_name} {date_obj.year}"

    async def get_today_task(self) -> Optional[DailyFollowUp]:
        """Get the daily task for today. Create it if missing (guarded against concurrent creation)."""
        today = date.today()

        async with _get_today_task_lock():
            task = await self.get_daily_task_by_date(today)
            if not task:
                logger.info(f"Today's task ({today}) not found. Creating it now...")
                title = self._get_formatted_date_title(today)
                success = await self.create_daily_task(today, title, status="En cours")
                if success:
                    task = await self.get_daily_task_by_date(today)

        if task and task.status == "À faire":
            task.status = "En cours"

            async def _update_status_safe(page_id: str) -> None:
                try:
                    await self.update_task_status(page_id, "En cours")
                except Exception as exc:
                    logger.warning(f"Impossible de passer la tâche {page_id} en 'En cours' : {exc}")

            asyncio.create_task(_update_status_safe(task.id))

        return task

    async def toggle_daily_checkbox(self, page_id: str, property_name: str, value: bool) -> bool:
        """Toggle a STATIC checkbox property on a daily task page."""
        try:
            await notion_client.update_page(page_id, {property_name: {"checkbox": value}})
            logger.debug(f"Updated property {property_name} to {value} for page {page_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to toggle property checkbox {property_name}: {e}")
            return False

    async def toggle_dynamic_task(self, block_id: str, value: bool) -> bool:
        """Toggle a DYNAMIC checkbox block."""
        try:
            await notion_client.update_block(block_id=block_id, to_do={"checked": value})
            logger.debug(f"Updated dynamic block {block_id} to {value}")
            return True
        except Exception as e:
            logger.error(f"Failed to toggle dynamic task {block_id}: {e}")
            return False

    async def add_dynamic_task(self, page_id: str, text: str) -> bool:
        """Add a new dynamic task (checkbox block) to the page."""
        try:
            children = [
                {
                    "object": "block",
                    "type": "to_do",
                    "to_do": {
                        "rich_text": [{"type": "text", "text": {"content": text}}],
                        "checked": False
                    }
                }
            ]
            await notion_client.append_block_children(page_id, children)
            logger.success(f"Added dynamic task '{text}' to page {page_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to add dynamic task: {e}")
            return False

    async def add_daily_comment(self, page_id: str, text: str) -> bool:
        """Append a comment (paragraph block) to the page."""
        try:
            children = [
                {
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {
                        "rich_text": [{"type": "text", "text": {"content": text}}]
                    }
                }
            ]
            await notion_client.append_block_children(page_id, children)
            logger.success(f"Added comment to page {page_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to add comment: {e}")
            return False

    async def update_course(self, course_id: str, properties: dict):
        """Update a Course page in Notion."""
        try:
            await notion_client.update_page(page_id=course_id, properties=properties)
            logger.success(f"Updated course {course_id} with properties: {properties.keys()}")
            return True
        except Exception as e:
            logger.error(f"Failed to update course {course_id}: {e}")
            return False

    async def create_course_college(self, title: str, college: str, item_number: str):
        """Create a new Course in Notion linked to a College."""
        try:
            properties = {
                "Cours": {"title": [{"text": {"content": title}}]},
                "Collège": {"multi_select": [{"name": college}]},
            }
            
            # Handle Item Number if provided
            if item_number:
                # Try to convert to float/int if strictly number property, 
                # but models.py says: 
                # item_number=str(NotionProperty.extract_number(props.get("ITEM")))
                # So it's a Number property in Notion.
                try:
                    val = float(item_number.replace(',', '.'))
                    properties["ITEM"] = {"number": val}
                except ValueError:
                    # If not a valid number, we can't set it if it's a Number property type
                    logger.warning(f"Invalid item number '{item_number}', skipping.")
            
            response = await notion_client.create_page(
                parent_db_id=settings.notion.cours_db_id,
                properties=properties
            )
            logger.success(f"Created college course '{title}' (id: {response['id']})")
            return True
        except Exception as e:
            logger.error(f"Failed to create college course '{title}': {e}")
            return False

    async def get_all_items_map(self) -> dict:
        """Fetch all items and return a map { item_number (int): page_id }."""
        logger.info("Fetching all Items for cache...")
        results = await notion_client.query_database(settings.notion.item_db_id)
        items_map = {}
        for page in results:
            try:
                item_num = _parse_item_page(page)
                if item_num is not None:
                    items_map[item_num] = page["id"]
            except Exception as e:
                logger.warning(f"Failed to parse Item page {page.get('id')}: {e}")
        logger.success(f"Cached {len(items_map)} items.")
        return items_map

    async def get_updated_items_map(self, since: str) -> dict:
        """Fetch items updated since the given ISO timestamp."""
        logger.info(f"Fetching Items updated since {since}...")
        filter_params = {
            "timestamp": "last_edited_time",
            "last_edited_time": {"after": since},
        }
        results = await notion_client.query_database(settings.notion.item_db_id, filter_params=filter_params)
        items_map = {}
        for page in results:
            try:
                item_num = _parse_item_page(page)
                if item_num is not None:
                    items_map[item_num] = page["id"]
            except Exception as e:
                logger.warning(f"Failed to parse updated Item page {page.get('id')}: {e}")
        logger.success(f"Found {len(items_map)} updated items.")
        return items_map

    async def link_item_by_number(self, course_id: str, item_number: float):
        """Find Item page by number and link it to the Course."""
        try:
            # Legacy method kept for single usage if needed, but updated to use text filter
            # ... (previous implementation)
            # Actually, let's keep it compatible or redirect to cache if available?
            # ideally background task uses map directly. 
            # We keep this for manual single actions if any.
             
            filter_params = {
                "property": "ITEM", 
                "rich_text": {
                    "equals": str(int(item_number)) if item_number.is_integer() else str(item_number)
                }
            }
            
            results = await notion_client.query_database(settings.notion.item_db_id, filter_params=filter_params)
            
            target_item_id = None
            if results:
                 target_item_id = results[0]['id']
            else:
                 logger.warning(f"Item number {item_number} not found in Items DB.")
                 return False

            if target_item_id:
                return await self.update_course(course_id, {
                    P.ITEM_LIE: relation([target_item_id])
                })
                
        except Exception as e:
            logger.error(f"Failed to auto-link item {item_number}: {e}")
            return False

    async def start_course_tracking(
        self,
        course_id: str,
        context: str,
        first_read_date: date,
    ) -> bool:
        """
        Démarre ou redémarre le suivi d'un cours.

        Écrit dans Notion :
        - rappel_done = True
        - date_1ere_lecture = first_read_date
        - J3 / J7 / J14 / J30 recalculés

        Fonctionne pour context='college' et context='ue'.
        Ne touche pas à Google Calendar (géré côté UI).
        Le payload est calculé par tracking_service (source unique de vérité).
        """
        from backend.core.tracking.service import tracking_service
        try:
            updates = tracking_service.build_tracking_payload(context, first_read_date)
            ok = await self.update_course(course_id, updates)
            if ok:
                logger.success(
                    f"Suivi démarré ({context}) pour {course_id} "
                    f"à partir du {first_read_date.isoformat()}"
                )
            return ok
        except Exception as e:
            logger.error(f"start_course_tracking failed for {course_id}: {e}")
            return False

    async def increment_lecture_college(self, course_id: str, current_val: int) -> bool:
        """Increment the 'Nombre lecture college' counter (vue Collège)."""
        try:
            new_val = current_val + 1
            return await self.update_course(course_id, {P.NB_LECTURES_COLLEGE: number(new_val)})
        except Exception as e:
            logger.error(f"Failed to increment lecture count for {course_id}: {e}")
            return False

    async def increment_lecture_ue(self, course_id: str, current_val: int) -> bool:
        """Increment the 'Nombre lecture' counter (vue Semestre/UE)."""
        try:
            new_val = current_val + 1
            return await self.update_course(course_id, {P.NB_LECTURES_UE: number(new_val)})
        except Exception as e:
            logger.error(f"Failed to increment UE lecture count for {course_id}: {e}")
            return False

    async def add_course_to_daily_reviewed(self, page_id: str, course_title: str) -> bool:
        """Add the course to the 'Cours révisés' section (appended to page)."""
        try:
            children = [
                {
                    "object": "block",
                    "type": "to_do",
                    "to_do": {
                        "rich_text": [{"type": "text", "text": {"content": f"Révisé : {course_title}"}}],
                        "checked": True
                    }
                }
            ]
            await notion_client.append_block_children(page_id, children)
            logger.success(f"Added '{course_title}' to daily page {page_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to add course to daily page: {e}")
            return False

    async def get_daily_course_status(self, page_id: str) -> tuple[List[str], List[str]]:
        """Retrieve both reviewed courses and manual revision courses from the daily page blocks in one call."""
        reviewed_titles = []
        manual_titles = []
        try:
            response = await notion_client.retrieve_block_children(page_id)
            blocks = response.get("results", [])
            
            for block in blocks:
                if block.get("type") == "to_do":
                    todo = block["to_do"]
                    rich_text = todo.get("rich_text", [])
                    if rich_text:
                        content = rich_text[0].get("text", {}).get("content", "")
                        
                        # Check for "Révisé"
                        if todo.get("checked") and content.startswith("Révisé : "):
                            title = content.replace("Révisé : ", "").strip()
                            reviewed_titles.append(title)
                            
                        # Check for "Manuel" (Unchecked)
                        elif not todo.get("checked") and content.startswith("Manuel : "):
                            title = content.replace("Manuel : ", "").strip()
                            manual_titles.append(title)
                            
        except Exception as e:
            logger.error(f"Failed to fetch daily course status for page {page_id}: {e}")
            
        return reviewed_titles, manual_titles

    async def add_course_to_daily_manual(self, page_id: str, course_title: str) -> bool:
        """Add a manual revision course to the daily page (unchecked to_do)."""
        try:
            children = [
                {
                    "object": "block",
                    "type": "to_do",
                    "to_do": {
                        "rich_text": [{"type": "text", "text": {"content": f"Manuel : {course_title}"}}],
                        "checked": False 
                    }
                }
            ]
            await notion_client.append_block_children(page_id, children)
            logger.success(f"Added manual revision '{course_title}' to page {page_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to add manual revision to page: {e}")
            return False

    async def get_daily_reviewed_courses(self, page_id: str) -> List[str]:
        """Retrieve list of course titles already marked as reviewed (Backward compatibility)."""
        r, _ = await self.get_daily_course_status(page_id)
        return r

    async def get_daily_manual_revision_courses(self, page_id: str) -> List[str]:
        """Retrieve list of courses manually added for revision (Backward compatibility)."""
        _, m = await self.get_daily_course_status(page_id)
        return m

    async def mark_manual_revision_done(self, page_id: str, course_title: str) -> bool:
        """Mark a manual revision item as done (checked) and update text to 'Révisé : ...'."""
        # This is tricky because we need the Block ID.
        # So we iterate to find it.
        try:
            response = await notion_client.retrieve_block_children(page_id)
            blocks = response.get("results", [])
            
            target_block_id = None
            for block in blocks:
                if block.get("type") == "to_do":
                    todo = block["to_do"]
                    rich_text = todo.get("rich_text", [])
                    if rich_text:
                        content = rich_text[0].get("text", {}).get("content", "")
                        if content == f"Manuel : {course_title}":
                             target_block_id = block["id"]
                             break
            
            if target_block_id:
                await notion_client.update_block(
                    block_id=target_block_id,
                    to_do={
                        "checked": True,
                        "rich_text": [{"text": {"content": f"Révisé : {course_title}"}}],
                    },
                )
                logger.success(f"Marked manual revision '{course_title}' as done.")
                return True
            else:
                logger.warning(f"Could not find manual revision block for '{course_title}'")
                # Fallback: just add a new "Révisé" block?
                return await self.add_course_to_daily_reviewed(page_id, course_title)

        except Exception as e:
            logger.error(f"Failed to mark manual revision done: {e}")
            return False

    async def find_course_by_title(self, title: str) -> Optional[Cours]:
        """Find a course by its exact title."""
        try:
            filter_params = {
                "property": "Cours",
                "title": {
                    "equals": title
                }
            }
            results = await notion_client.query_database(settings.notion.cours_db_id, filter_params=filter_params)
            if results:
                return Cours.from_notion(results[0])
            return None
        except Exception as e:
            logger.error(f"Failed to find course by title '{title}': {e}")
            return None

    async def get_streak_counts(self) -> int:
        """Calculate the current streak of completed daily tasks."""
        try:
            # Query all daily tasks sorted by date descending
            sorts = [{"property": "Date", "direction": "descending"}]
            # We fetch a reasonable amount, e.g., last 100 days
            results = await notion_client.query_database(settings.notion.daily_db_id, sorts=sorts, page_size=100)
            
            today = date.today()
            today_str = today.isoformat()

            tasks_map = {
                t.date.isoformat(): t
                for t in (DailyFollowUp.from_notion(p) for p in results)
                if t.date
            }

            current_streak = 0
            check_date = today

            if today_str in tasks_map and tasks_map[today_str].status == "Terminé":
                current_streak += 1

            from datetime import timedelta
            check_date -= timedelta(days=1)

            while current_streak <= 365:
                d_str = check_date.isoformat()
                if d_str not in tasks_map or tasks_map[d_str].status != "Terminé":
                    break
                current_streak += 1
                check_date -= timedelta(days=1)

            return current_streak

        except Exception as e:
            logger.error(f"Failed to calculate streak: {e}")
            return 0

notion_service = NotionService()
