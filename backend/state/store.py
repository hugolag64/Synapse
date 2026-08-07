import asyncio
import difflib
from typing import List, Dict, Optional
from backend.core.notion.models import Cours
from backend.core.notion.service import notion_service
from backend.core.qcm.items_mapping import item_title
from loguru import logger
from backend.config.settings import set_app_timezone

import json
import os
from datetime import datetime

class DataStore:
    _instance = None
    # Resolve absolute path to project root (3 levels up from backend/state/store.py)
    # backend/state/store.py -> backend/state -> backend -> root
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    CACHE_FILE = os.path.join(BASE_DIR, "data_cache.json")

    def __init__(self):
        self.cours: List[Cours] = []
        self.ues_map: Dict[str, dict] = {}
        self.is_loaded = False
        self.colleges_order: List[str] = []
        self._items_map: Dict[int, str] = {}  # item_number (int) -> page_id
        self.items_last_synced: datetime = None
        
        # Loading State
        self.loading_progress = 0.0
        self.loading_message = "Initialisation..."
        self.is_preloaded = False
        
        self.dashboard_data = {
            'task': None,
            'events': [],
            'streak': {},
            'reviews': [],
            'manual': []
        }

        # IDs des révisions validées — persistés sur disque pour survivre aux redémarrages
        self.done_review_ids: set = set()

        # Anti double-lancement du preload (tabs concurrents)
        self._preloading: bool = False

        # Lock protégeant les mutations de self.cours contre les refreshs concurrents
        self._cours_lock: asyncio.Lock = asyncio.Lock()
        self.cours_last_synced: Optional[datetime] = None

        # F1 — Graphe sémantique inter-fiches (reconstruit au démarrage)
        self.semantic_graph: dict = {}

        # F4 — Stage actif pour le boost priorité (chargé au démarrage)
        self.active_stage: Optional[object] = None  # ActiveStage | None

        # User Preferences (Persistent)
        # Initialize with defaults
        self.preferences = self._get_default_preferences()

    def _get_default_preferences(self):
        return {
            'dark_mode': False,
            'semestre_actuel': 'Semestre 7',
            # Profile 1 (Standard)
            'pomo_1_work': 25,
            'pomo_1_break': 5,
            # Profile 2 (Deep Work)
            'pomo_2_work': 50,
            'pomo_2_break': 10,

            'college_sort': 'newest',
            'agenda_open': True,  # État du panneau Agenda du Jour
            'planning_capacity_minutes': 360,
            'planning_vacation': {'enabled': False},
            'timezone': 'Europe/Paris',
            'edn_target_date': '2026-10-15',
        }

    def _load_preferences(self, raw_preferences) -> None:
        preferences = self._get_default_preferences()
        if isinstance(raw_preferences, dict):
            preferences.update(raw_preferences)
        try:
            preferences['edn_target_date'] = datetime.strptime(
                str(preferences.get('edn_target_date', '2026-10-15')), '%Y-%m-%d'
            ).date().isoformat()
        except (TypeError, ValueError):
            preferences['edn_target_date'] = '2026-10-15'
        self.preferences = preferences
        set_app_timezone(self.preferences.get("timezone"))

    @property
    def items_map(self) -> Dict[int, str]:
        if not hasattr(self, '_items_map'):
            self._items_map = {}
        return self._items_map

    @items_map.setter
    def items_map(self, value: Dict):
        # Normalise toutes les clés en int pour éviter les mismatches float/int/str
        normalized: Dict[int, str] = {}
        for k, v in value.items():
            try:
                normalized[int(float(k))] = v
            except (ValueError, TypeError):
                pass
        self._items_map = normalized
        self._resolve_item_numbers()

    def _resolve_item_numbers(self):
        """Automatically resolve missing item_number using item_lie and items_map."""
        if not hasattr(self, '_items_map') or not self._items_map or not self.cours:
            return
            
        # Build inverted map: normalized page_id -> item_number (as string)
        # Les clés sont normalisées en int par le setter — on peut directement str(int)
        inverted_map = {}
        for item_num, page_id in self._items_map.items():
            if not page_id:
                continue
            normalized_id = page_id.replace("-", "").lower()
            num_str = str(item_num)  # item_num est déjà un int normalisé
            inverted_map[normalized_id] = num_str
            
        resolved_count = 0
        for c in self.cours:
            if not c.item_number and c.item_lie:
                normalized_lie = c.item_lie.replace("-", "").lower()
                if normalized_lie in inverted_map:
                    c.item_number = inverted_map[normalized_lie]
                    resolved_count += 1
                    
        if resolved_count > 0:
            logger.info(f"Resolved {resolved_count} missing item numbers via items_map.")

    @staticmethod
    def _deduplicate_cours(cours: list) -> list:
        """
        Déduplique par (item_number, collège) : si plusieurs cours partagent le même
        numéro d'item ET le même ensemble de collèges, garde celui dont le titre est
        le plus proche du titre EDN canonique. Un même item peut légitimement avoir
        plusieurs cours (un par collège — voir Cours DB : une page = un couple
        (item, collège)) ; ceux-ci ne sont jamais fusionnés entre eux.
        Les cours sans item_number sont conservés sans modification.
        """
        def _norm_item(raw: str) -> str | None:
            try:
                return str(int(float(str(raw).strip())))
            except (ValueError, TypeError):
                return None

        def _title_score(course_title: str, canonical: str) -> float:
            if not canonical:
                return float(len(course_title))  # fallback : titre le plus long
            return difflib.SequenceMatcher(
                None,
                course_title.lower().strip(),
                canonical.lower().strip(),
            ).ratio()

        groups: dict[tuple[str, tuple], list] = {}
        no_item: list = []
        for c in cours:
            n = _norm_item(getattr(c, "item_number", "") or "")
            if n is None:
                no_item.append(c)
            else:
                college_key = tuple(sorted(getattr(c, "college", None) or []))
                groups.setdefault((n, college_key), []).append(c)

        result: list = list(no_item)
        for n, group in groups.items():
            if len(group) == 1:
                result.append(group[0])
                continue
            canonical = item_title(n)
            best = max(group, key=lambda c: _title_score(getattr(c, "title", "") or "", canonical))
            discarded = [getattr(c, "title", "?") for c in group if c is not best]
            logger.info(
                f"Doublon ITEM {n} : conservé '{best.title}', ignoré(s) : {discarded}"
            )
            result.append(best)

        return result

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = DataStore()
        return cls._instance

    def save_to_disk(self):
        """Save current UEs and Cours to a local JSON file."""
        try:
            data = {
                "cours": [c.model_dump() for c in self.cours],
                "ues_map": self.ues_map,
                "colleges_order": self.colleges_order,
                "items_map": self.items_map,
                "preferences": self.preferences,
                "done_review_ids": list(self.done_review_ids),
                "items_last_synced": self.items_last_synced.isoformat() if self.items_last_synced else None,
                "cours_last_synced": self.cours_last_synced.isoformat() if self.cours_last_synced else None,
                "last_updated": datetime.now().isoformat()
            }
            tmp = self.CACHE_FILE + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, default=str)
            os.replace(tmp, self.CACHE_FILE)
            logger.info(f"Data saved to disk: {self.CACHE_FILE}")
            logger.debug(f"Saved colleges_order: {self.colleges_order}")
        except Exception as e:
            logger.error(f"Failed to save data to disk: {e}")

    def run_sqlite_migration(self):
        """
        Migration one-shot : transfère les done_review_ids JSON vers SQLite.
        Appelé au démarrage si des done_ids sont encore dans le cache JSON.
        """
        if not self.done_review_ids:
            return
        try:
            from backend.core.reviews.local_store import migrate_from_done_ids
            courses_map = {c.id: c for c in self.cours}
            migrated = migrate_from_done_ids(self.done_review_ids, courses_map)
            if migrated > 0:
                # Vider les done_ids du cache JSON — SQLite est désormais la source
                self.done_review_ids = set()
                self.save_to_disk()
        except Exception as e:
            logger.warning(f"Migration SQLite échouée (non bloquante): {e}")

    def rebuild_semantic_graph(self) -> None:
        """Reconstruit le graphe sémantique depuis les cours et lacunes actives."""
        try:
            from backend.core.graph.builder import build_semantic_graph
            from backend.core.reviews.local_store import (
                get_active_weak_points, save_graph_to_db, get_qcm_sessions_all,
            )
            wps = get_active_weak_points(limit=10_000)
            qcm = get_qcm_sessions_all(limit=5_000, platform=None, course_id=None)
            self.semantic_graph = build_semantic_graph(self.cours, wps, qcm)
            save_graph_to_db(self.semantic_graph)
        except Exception as exc:
            logger.warning(f"rebuild_semantic_graph échoué (non bloquant): {exc}")

    def reload_active_stage(self) -> None:
        """Charge le stage actif depuis SQLite et le stocke dans active_stage."""
        try:
            from backend.core.externat.store import get_active_stage
            from backend.core.externat.models import ActiveStage
            stage = get_active_stage()
            self.active_stage = ActiveStage.from_stage(stage) if stage and stage.is_current else None
        except Exception as exc:
            logger.warning(f"reload_active_stage échoué (non bloquant): {exc}")

    def set_preference(self, key: str, value):
        """Update a preference and save to disk."""
        if key == "timezone":
            value = set_app_timezone(value).key
        elif key == "edn_target_date":
            value = datetime.strptime(str(value), '%Y-%m-%d').date().isoformat()
        self.preferences[key] = value
        self.save_to_disk()

    def load_from_disk(self, force: bool = False) -> bool:
        """Load UEs and Cours from local JSON file.

        force=True : ignore la limite de 12h (fallback hors-ligne).
        """
        if not os.path.exists(self.CACHE_FILE):
            logger.info("No cache file found.")
            return False

        try:
            with open(self.CACHE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)

            # Les préférences vivent dans le même fichier que le cache cours,
            # mais leur durée de vie est indépendante.
            self._load_preferences(data.get("preferences", {}))

            # Auto-cleaning cache si > 12h (sauf mode force)
            if not force and "last_updated" in data:
                last_updated = datetime.fromisoformat(data["last_updated"])
                if (datetime.now() - last_updated).total_seconds() > 12 * 3600:
                    logger.info("Cache obsolète (>12h), cours ignorés mais préférences conservées.")
                    return False
            
            self.cours = [Cours(**c) for c in data.get("cours", [])]
            self.colleges_order = data.get("colleges_order", [])
            logger.debug(f"Loaded colleges_order from {self.CACHE_FILE}: {self.colleges_order}")
            
            # Reconstruct items_map — le setter normalise les clés en int
            raw_map = data.get("items_map", {})
            self.items_map = raw_map  # le setter gère la normalisation float→int
            
            if data.get("items_last_synced"):
                self.items_last_synced = datetime.fromisoformat(data.get("items_last_synced"))
            if data.get("cours_last_synced"):
                self.cours_last_synced = datetime.fromisoformat(data["cours_last_synced"])

            self.is_loaded = True

            self.done_review_ids = set(data.get("done_review_ids", []))

            self.ues_map = data.get("ues_map", {})
            self._resolve_item_numbers()
            self.cours = self._deduplicate_cours(self.cours)
            logger.success(f"Loaded from disk: {len(self.cours)} Cours, {len(self.items_map)} Items")
            return True
        except Exception as e:
            logger.error(f"Failed to load data from disk: {e}")
            return False
    
    async def preload_all_views(self):
        """Fetch EVERYTHING needed for the app to feel instant."""
        if self._preloading:
            logger.debug("preload_all_views déjà en cours — appel concurrent ignoré.")
            return
        self._preloading = True
        logger.info("Starting Global Preload...")
        
        # Try to load from disk first to get preferences/order
        cache_loaded = self.load_from_disk()
        
        self.is_preloaded = False
        self.loading_progress = 0.1
        self.loading_message = "Récupération des Collèges..."
        
        # Initialize variables to avoid UnboundLocalError in except block
        today_task = None
        events = []
        streak = {}

        try:
            # 1. Core Data (ues, Cours)
            if not cache_loaded:
                await self.refresh()  # charge ues/cours (30%)
            else:
                logger.info("Data loaded from disk, skipping synchronous refresh.")
            self.loading_progress = 0.4

            # PDF Phase A: apply SQLite-cached paths (fast, no disk scan)
            try:
                from backend.core.reviews import local_store as _ls

                def _pdf_phase_a_sync():
                    removed = _ls.cleanup_pdf_cache()
                    return removed, _ls.get_all_pdf_cache()

                # Déchargé du event loop : ~2 requêtes SQLite par cours (jusqu'à
                # ~1400 pour 700 cours) remplacées par 2 requêtes batch, exécutées
                # dans un thread pour ne pas bloquer les autres tâches en cours.
                removed, pdf_cache = await asyncio.to_thread(_pdf_phase_a_sync)
                if removed:
                    logger.info(f"PDF cache: {removed} entrées périmées supprimées")
                for c in self.cours:
                    if not getattr(c, "url_pdf", None):
                        cached = pdf_cache.get((c.id, "college"))
                        if cached and os.path.isfile(cached):
                            c.url_pdf = f"file:///{cached.replace(os.sep, '/')}"
                    if not getattr(c, "url_pdf_ue", None):
                        cached_ue = pdf_cache.get((c.id, "ue"))
                        if cached_ue and os.path.isfile(cached_ue):
                            c.url_pdf_ue = f"file:///{cached_ue.replace(os.sep, '/')}"
            except Exception as _exc:
                logger.warning(f"PDF Phase A échoué (non bloquant): {_exc}")

            # Migration one-shot done_review_ids JSON → SQLite
            self.run_sqlite_migration()

            # F1 + F4 : graphe sémantique et stage actif
            await asyncio.to_thread(self.rebuild_semantic_graph)
            self.reload_active_stage()

            # F-Perf : reconstruire l'index de recherche fuzzy après sync
            try:
                from backend.core.search.service import search_index
                search_index.build(self.cours)
            except Exception as _exc:
                logger.warning(f"search_index.build échoué (non bloquant): {_exc}")

            # F5 — Snapshot mastery hebdomadaire (lundi uniquement, idempotent)
            if datetime.now().weekday() == 0:
                try:
                    from backend.core.analytics.weekly_report import snapshot_courses
                    snapshot_courses(self.cours)
                except Exception as _exc:
                    logger.warning(f"snapshot_courses échoué (non bloquant): {_exc}")

            # 2. Dashboard Data
            self.loading_message = "Préparation du Tableau de Bord..."
            from backend.core.notion.service import notion_service
            from backend.core.google.calendar_service import calendar_service
            
            # Parallel fetch for Dashboard
            # We need: Today Task, Streak, Calendar Events
            # We also need Review Lists which depend on Today Task
            
            # Load tasks and calendar concurrently
            task_future = asyncio.create_task(notion_service.get_today_task())
            # Use get_events_for_day instead of get_upcoming_events
            events_task = asyncio.create_task(calendar_service.get_events_for_day(datetime.now().date()))
            streak_task = asyncio.create_task(notion_service.get_streak_counts())
            
            self.loading_progress = 0.5
            
            # Use return_exceptions=True to allow partial success
            try:
                results = await asyncio.wait_for(
                    asyncio.gather(task_future, events_task, streak_task, return_exceptions=True),
                    timeout=15.0
                )
            except asyncio.TimeoutError:
                logger.error("Preload Dashboard tasks timed out!")
                results = [Exception("Timeout"), [], 0]
            
            # 1. Task
            if isinstance(results[0], Exception):
                logger.error(f"Preload Task Failed: {results[0]}")
            else:
                today_task = results[0]
                
            # 2. Events
            if isinstance(results[1], Exception):
                logger.error(f"Preload Events Failed: {results[1]}")
            else:
                events = results[1]
                
            # 3. Streak
            if isinstance(results[2], Exception):
                logger.error(f"Preload Streak Failed: {results[2]}")
            else:
                streak = results[2]
            
            self.dashboard_data['task'] = today_task
            self.dashboard_data['events'] = events
            self.dashboard_data['streak'] = streak
            
            self.loading_progress = 0.7
            self.loading_message = "Calcul des révisions..."
            
            # B. If Task, pre-fetch reviews
            if today_task:
                try:
                    rev_results = await asyncio.gather(
                        notion_service.get_daily_reviewed_courses(today_task.id),
                        notion_service.get_daily_manual_revision_courses(today_task.id),
                        return_exceptions=True
                    )
                    
                    if isinstance(rev_results[0], Exception):
                        logger.error(f"Preload Reviews Failed: {rev_results[0]}")
                        self.dashboard_data['reviews'] = []
                    else:
                        self.dashboard_data['reviews'] = rev_results[0]
                        
                    if isinstance(rev_results[1], Exception):
                        logger.error(f"Preload Manual Failed: {rev_results[1]}")
                        self.dashboard_data['manual'] = []
                    else:
                        self.dashboard_data['manual'] = rev_results[1]
                        
                except Exception as e:
                     logger.error(f"Error preloading reviews: {e}")
            
            self.loading_progress = 0.9
            self.loading_message = "Finalisation..."
            
            await asyncio.sleep(0.5) # User satisfaction delay :p (and ensuring UI update)
            
            self.preferences.pop("_offline_mode", None)  # connexion OK — effacer le flag
            self.loading_progress = 1.0
            self.loading_message = "Prêt !"
            self.is_preloaded = True

            # Import auto des cours depuis les dossiers items/ sur disque (non bloquant)
            try:
                from backend.core.pdf_import import auto_import_courses_from_pdf_folders
                asyncio.create_task(auto_import_courses_from_pdf_folders(list(self.cours)))
            except Exception as _exc:
                logger.warning(f"PDF import: task non lancée — {_exc}")

            logger.success("Global Preload Completed Successfully.")

        except asyncio.CancelledError:
            logger.warning("Global Preload Cancelled (Browser reloaded).")
            self.loading_progress = 0.0
            self.is_preloaded = False
            self._preloading = False
            raise
        except Exception as e:
            logger.error(f"Global Preload Failed: {e}")

            if not self.is_loaded:
                try:
                    logger.warning("Notion inaccessible — tentative de chargement du cache expiré.")
                    self.load_from_disk(force=True)
                    if self.is_loaded:
                        self.preferences["_offline_mode"] = True
                        logger.warning("Mode hors-ligne activé (cache expiré).")
                except Exception as _stale_exc:
                    logger.warning(f"Cache expiré inaccessible : {_stale_exc}")
            else:
                self.preferences["_offline_mode"] = True

            self.is_preloaded = True
            self.loading_progress = 1.0
            self.loading_message = "Hors-ligne (cache)" if self.preferences.get("_offline_mode") else "Prêt (avec erreurs)"
        finally:
            self._preloading = False

    async def refresh(self):
        """Fetch all data from Notion (parallel)."""
        logger.info("Refreshing DataStore from Notion...")
        new_ues, new_cours = await asyncio.gather(
            notion_service.get_all_ues_map(),
            notion_service.get_all_cours(),
        )
        async with self._cours_lock:
            self.ues_map = new_ues
            self.cours = self._deduplicate_cours(new_cours)
        self.is_loaded = True
        self.cours_last_synced = datetime.now()
        logger.success(f"DataStore loaded: {len(self.cours)} Cours")
        self.save_to_disk()

    async def merge_cours_delta(self, updated: list) -> int:
        """Fusionne une liste de cours mis à jour dans le store, en préservant les enrichissements locaux."""
        if not updated:
            return 0
        async with self._cours_lock:
            existing_map = {c.id: c for c in self.cours}
            for new_c in updated:
                old_c = existing_map.get(new_c.id)
                if old_c is not None:
                    new_c.obsidian_uri = new_c.obsidian_uri or old_c.obsidian_uri
                existing_map[new_c.id] = new_c
            self.cours = self._deduplicate_cours(list(existing_map.values()))
        return len(updated)

    async def remove_cours(self, course_id: str) -> None:
        """Retire un Cours du store local (après suppression Notion) et persiste."""
        async with self._cours_lock:
            self.cours = [c for c in self.cours if c.id != course_id]
        self.save_to_disk()

    # ... getters ...
    
    def update_colleges_order(self, new_order: List[str]):
        """Update and save the custom order for colleges."""
        self.colleges_order = new_order
        self.save_to_disk()

    def get_colleges(self) -> List[str]:
        """Return distinct colleges sorted (using custom order if available)."""
        colleges = set()
        for c in self.cours:
            if c.college:
                colleges.update(c.college)
        
        sorted_colleges = sorted(list(colleges))

        pref_order = self.colleges_order or []

        # 1. Start with items from custom order that exist in current data
        final_order = [c for c in pref_order if c in colleges]
        
        # 2. Append any new/missing items from current data (sorted alphabetically)
        remaining = [c for c in sorted_colleges if c not in final_order]
        final_order.extend(remaining)
        
        return final_order

    def get_cours_for_college(self, college: str) -> List[Cours]:
        """Return courses linked to a specific college."""
        if college == "Tout":
            return [c for c in self.cours if c.college] # Only courses with a college
        return [c for c in self.cours if c.college and college in c.college]
        
    def get_items_for_college(self, college: str) -> List[str]:
        """Return unique item names (cours) for a specific college."""
        import traceback
        try:
            logger.debug(f"[STORE] get_items_for_college appelé pour le collège : {college}")
            cours = self.get_cours_for_college(college)
            logger.debug(f"[STORE] {len(cours)} cours trouvés pour {college}")
            # Using Cours.title as the item name
            items = set(c.title for c in cours if c.title)
            res = sorted(list(items))
            logger.debug(f"[STORE] Retour de {len(res)} items uniques")
            return res
        except Exception as e:
            logger.error(f"[STORE] Erreur dans get_items_for_college : {e}\n{traceback.format_exc()}")
            return []

    def get_semestres(self) -> List[str]:
        semestres = set(c.semestre for c in self.cours if c.semestre)
        return sorted(list(semestres))

    def get_cours_for_semestre(self, semestre: str) -> List[Cours]:
        return [c for c in self.cours if c.semestre == semestre]


data_store = DataStore.get_instance()
