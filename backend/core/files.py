import asyncio
import os
import unicodedata
import re
import difflib
from typing import List
from backend.config.settings import settings
from backend.core.reviews import local_store
from loguru import logger

try:
    from fuzzywuzzy import fuzz as _fuzz
    _HAS_FUZZ = True
except ImportError:
    _fuzz = None
    _HAS_FUZZ = False

def normalize_text(text: str) -> str:
    if not text:
        return ""
    text = text.lower()
    text = text.replace("’", "'")
    # Strip accents / diacritics
    text = "".join(
        c for c in unicodedata.normalize('NFD', text)
        if unicodedata.category(c) != 'Mn'
    )
    # Replace separators with space
    text = re.sub(r'[(),;!?._\-]', ' ', text)
    return " ".join(text.split())

STOPWORDS = {'en', 'de', 'le', 'la', 'et', 'du', 'un', 'une', 'des', 'pour', 'chez', 'au', 'aux', 'dans', 'sur', 'par', 'avec', 'sans', 'sous', 'les'}

def fuzzy_word_in_text(qw: str, text_words: List[str]) -> float:
    for fw in text_words:
        if qw == fw:
            return 1.0
        # Plural / singular matching in French (simple heuristics)
        if (qw.endswith('s') and qw[:-1] == fw) or (fw.endswith('s') and fw[:-1] == qw):
            return 0.9
        if (qw.endswith('x') and qw[:-1] + 'l' == fw) or (fw.endswith('x') and fw[:-1] + 'l' == qw):
            return 0.9 # e.g. cerebraux <-> cerebral
        if len(qw) >= 4 and qw in fw:
            return 0.7
    return 0.0

class FileService:
    def __init__(self):
        self.root_dir = settings.medicine_dir
        # Cache keyed by path: { '/path/to/dir': ['file1.pdf', ...] }
        self.pdf_caches: dict[str, List[str]] = {}

    def _walk_sync(self, target_dir: str) -> List[str]:
        """Synchronous os.walk — appelé via asyncio.to_thread pour ne pas bloquer l'event loop."""
        found = []
        for root, _dirs, files in os.walk(target_dir):
            for f in files:
                if f.lower().endswith(".pdf"):
                    found.append(os.path.join(root, f))
        return found

    async def refresh_cache_async(self, search_path: str = None):
        """Async version: délègue le os.walk à un thread pour ne pas bloquer."""
        target_dir = search_path if search_path else self.root_dir
        if not target_dir:
            logger.warning("Refresh Cache: No target directory provided/configured.")
            return
        if not os.path.exists(target_dir):
            logger.warning(f"Refresh Cache: Directory not found: {target_dir}")
            return

        logger.info(f"Refreshing PDF cache (async) from {target_dir}...")
        try:
            found_files = await asyncio.to_thread(self._walk_sync, target_dir)
            self.pdf_caches[target_dir] = found_files
            logger.success(f"PDF Cache for '{target_dir}' refreshed: {len(found_files)} files found.")
        except Exception as e:
            logger.error(f"Error during PDF walk in {target_dir}: {e}")

    def refresh_cache(self, search_path: str = None):
        """Sync fallback — utilise asyncio.to_thread si possible, sinon walk direct."""
        target_dir = search_path if search_path else self.root_dir
        if not target_dir:
            logger.warning("Refresh Cache: No target directory provided/configured.")
            return
        if not os.path.exists(target_dir):
            logger.warning(f"Refresh Cache: Directory not found: {target_dir}")
            return

        logger.info(f"Refreshing PDF cache from {target_dir}...")
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # On est dans un contexte async : planifier sans bloquer
                asyncio.create_task(self.refresh_cache_async(search_path))
            else:
                found_files = self._walk_sync(target_dir)
                self.pdf_caches[target_dir] = found_files
                logger.success(f"PDF Cache for '{target_dir}' refreshed: {len(found_files)} files found.")
        except Exception as e:
            logger.error(f"Error during PDF walk in {target_dir}: {e}")

    def find_pdf(self, query: str, limit: int = 20, search_path: str = None, item_number: str = None, min_score: float = 0.0) -> List[str]:
        """Search for PDF files in the configured directory matching the query with fuzzy scoring."""
        
        target_dir = search_path if search_path else self.root_dir
        
        if not target_dir:
             logger.warning("Find PDF: No target directory configured.")
             return []

        # Populate cache for this specific path if missing
        if target_dir not in self.pdf_caches:
            self.refresh_cache(search_path)
            
        # Get files from the specific cache bucket (or empty list if failed)
        current_cache = self.pdf_caches.get(target_dir, [])
        
        if not current_cache:
            return []
            
        scored_matches = []
        
        for file_path in current_cache:
            filename = os.path.basename(file_path)
            
            # 1. Normalize
            filename_base = os.path.splitext(filename)[0]
            filename_norm = normalize_text(filename_base)
            query_norm = normalize_text(query)
            
            score = 0.0
            
            # 2. Extract digits
            filename_digits = re.findall(r'\b\d+\b', filename_base)
            query_digits = re.findall(r'\b\d+\b', query)
            
            # Target item number
            target_num = None
            if item_number:
                target_num = normalize_text(str(item_number)).strip()
            elif query_digits:
                target_num = query_digits[0]
                
            if target_num:
                if target_num in filename_digits:
                    score += 150.0  # High match for item number
                    if filename_norm.startswith(target_num):
                        score += 50.0 # Extra bonus if starts with item number
                elif target_num in filename_norm:
                    score += 80.0
                    
            # 3. Full substring match
            if query_norm in filename_norm:
                score += 50.0
            elif filename_norm in query_norm:
                score += 30.0
                
            # 4. Individual word matching
            query_words = [w for w in query_norm.split() if w not in STOPWORDS and len(w) > 1]
            filename_words = filename_norm.split()
            
            if query_words:
                matched_words_score = 0.0
                exact_matches = 0
                for qw in query_words:
                    ratio = fuzzy_word_in_text(qw, filename_words)
                    if ratio > 0:
                        matched_words_score += ratio * 25.0
                        if ratio == 1.0:
                            exact_matches += 1
                            
                # All words match bonus
                if exact_matches == len(query_words):
                    score += 40.0
                elif matched_words_score > 0:
                    score += matched_words_score
                    
            # 5. Sequence similarity (Fuzzy closeness)
            ratio = difflib.SequenceMatcher(None, query_norm, filename_norm).ratio()
            score += ratio * 20.0

            # 6. fuzzywuzzy: token_set_ratio (handles word order / partial match)
            if _HAS_FUZZ:
                ts = _fuzz.token_set_ratio(query_norm, filename_norm)
                score += (ts / 100.0) * 40.0
                pr = _fuzz.partial_ratio(query_norm, filename_norm)
                score += (pr / 100.0) * 15.0

            effective_min = max(min_score, 5.0)
            if score > effective_min:
                scored_matches.append((score, file_path))
        
        # Sort: Score DESC, then Length ASC (shorter is usually better match), then Name ASC
        scored_matches.sort(key=lambda x: (-x[0], len(os.path.basename(x[1])), os.path.basename(x[1])))
        
        logger.info(f"Fuzzy search for '{query}' (Item: {item_number}) found {len(scored_matches)} matches in {target_dir}.")
        return [m[1] for m in scored_matches[:limit]]

    async def auto_detect_pdf(self, course, context: str = "college") -> "str | None":
        """
        Détecte automatiquement le PDF local le plus probable pour un cours.

        Logique :
          1. Guard : si l'URL PDF Notion est déjà renseignée → None (rien à faire)
          2. Cache SQLite : si un chemin valide est en cache → retourner directement
          3. Construction du search_path selon le contexte
          4. Peuplement du cache FileService si nécessaire
          5. Recherche floue avec seuil de score ≥ 50
          6. Persistence SQLite et retour du chemin trouvé

        Paramètres :
            course  : objet Cours Notion avec .id, .url_pdf, .url_pdf_ue,
                      .college, .title, .item_number
            context : 'college' (collège EDN) ou 'ue' (poly de fac)

        Retourne :
            str  : chemin absolu du PDF détecté
            None : aucun PDF détecté avec confiance suffisante
        """
        # ── 1. Guard : URL Notion déjà renseignée ────────────────────────────
        if context == "college":
            if getattr(course, "url_pdf", None):
                return None
        else:
            if getattr(course, "url_pdf_ue", None):
                return None

        # ── 2. Cache SQLite ──────────────────────────────────────────────────
        cached = local_store.get_pdf_cache(course.id, context)
        if cached is not None and os.path.isfile(cached):
            return cached

        # ── 3. Construction du search_path ───────────────────────────────────
        if context == "college":
            # Import lazy pour éviter les imports circulaires
            from backend.core.obsidian.service import COLLEGE_MAPPING
            college_name = course.college[0] if course.college else ""
            college_folder = COLLEGE_MAPPING.get(college_name, college_name)
            search_path = os.path.join(settings.medicine_dir, "Collèges", college_folder)
        else:
            search_path = settings.fac_dir or settings.medicine_dir

        if not search_path or not os.path.exists(search_path):
            return None

        # ── 4. Peuplement du cache FileService ───────────────────────────────
        if search_path not in self.pdf_caches:
            await self.refresh_cache_async(search_path)

        # ── 5. Recherche floue avec seuil de score ───────────────────────────
        results = self.find_pdf(
            course.title or "",
            search_path=search_path,
            item_number=str(course.item_number) if course.item_number else None,
            limit=1,
            min_score=50.0,
        )

        if not results:
            return None

        # ── 6. Persistence SQLite et retour ──────────────────────────────────
        local_store.set_pdf_cache(course.id, context, results[0])
        return results[0]


file_service = FileService()
