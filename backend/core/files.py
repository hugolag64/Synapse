import asyncio
import os
import unicodedata
import re
import difflib
from typing import List
from backend.config.settings import settings
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

_EMOJI_RE = re.compile(
    "["
    "\U0001F300-\U0001FAFF"
    "\U00002700-\U000027BF"
    "☀-⛿"
    "︀-️"
    "‍‌​"
    "]+",
    re.UNICODE,
)

# Clé   = nom Notion EXACT du collège (avec emoji).
# Valeur = nom du dossier dans <medicine_dir>/Collèges/ (sans emoji).
# Ne renseigner que les cas où le dossier diffère du nom Notion sans emoji.
PDF_COLLEGE_MAPPING: dict[str, str] = {
    "Chirurgie digestive 🧵": "Chirurgie générale viscérale et digestive",
}


def _normalize_college_name(name: str) -> str:
    """Strip emojis et lowercase pour comparer noms de collèges."""
    return " ".join(_EMOJI_RE.sub("", name).split()).lower()


def resolve_college_folder(folder_name: str, notion_college_names: List[str]) -> str | None:
    """
    Résout un nom de dossier local (<medicine_dir>/Collèges/{folder_name}) vers
    le nom Notion exact du collège correspondant, ou None si aucune correspondance
    fiable n'est trouvée (le dossier est alors ignoré plutôt que mal classé).

    Ordre de résolution :
      1. PDF_COLLEGE_MAPPING (override manuel Notion → dossier)
      2. Correspondance exacte après normalisation (emoji/casse/accents ignorés)
      3. Correspondance floue : le nom normalisé de l'un est contenu dans l'autre
    """
    folder_norm = normalize_text(_normalize_college_name(folder_name))

    override_by_folder = {
        normalize_text(_normalize_college_name(v)): k
        for k, v in PDF_COLLEGE_MAPPING.items()
    }
    if folder_norm in override_by_folder:
        return override_by_folder[folder_norm]

    by_norm = {
        normalize_text(_normalize_college_name(n)): n for n in notion_college_names
    }
    if folder_norm in by_norm:
        return by_norm[folder_norm]

    for n_norm, n_full in by_norm.items():
        if n_norm in folder_norm or folder_norm in n_norm:
            return n_full

    return None

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

    # Accepte : "Item 207 - ...", "207 - ...", "Numéro 207 - ...", "207. ..." etc.
    _ITEM_NUM_RE = re.compile(r"^(?:(?:item|num[ée]ro)\s*)?(\d{2,3})\s*[-–=.\s]", re.IGNORECASE)

    def _find_pdf_by_item_number_in_items_dir(
        self, college_folder_path: str, item_number: int
    ) -> "str | None":
        """
        Lookup direct : cherche le PDF d'un item par son numéro dans le sous-dossier
        items* du dossier college. Retourne le chemin absolu ou None.

        Plus fiable que le fuzzy quand on connaît college + numéro d'item.
        """
        if not os.path.isdir(college_folder_path):
            return None

        try:
            all_entries = os.listdir(college_folder_path)
        except OSError:
            return None

        item_subdirs = [
            os.path.join(college_folder_path, d)
            for d in all_entries
            if d.lower().startswith("item")
            and os.path.isdir(os.path.join(college_folder_path, d))
        ]
        if not item_subdirs:
            return None

        items_dir = max(item_subdirs, key=os.path.getmtime)

        try:
            pdf_files = [f for f in os.listdir(items_dir) if f.lower().endswith(".pdf")]
        except OSError:
            return None

        # Passe 1 : regex flexible sur le début du nom de fichier
        for fname in pdf_files:
            base = os.path.splitext(fname)[0]
            m = self._ITEM_NUM_RE.match(base)
            if m and int(m.group(1)) == item_number:
                return os.path.join(items_dir, fname)

        # Passe 2 : fallback — premier nombre entier dans le nom
        for fname in pdf_files:
            nums = re.findall(r'\b(\d{2,3})\b', os.path.splitext(fname)[0])
            if nums and int(nums[0]) == item_number:
                return os.path.join(items_dir, fname)

        return None

    def _get_college_folder(self, colleges_root: str, notion_name: str) -> "str | None":
        """
        Retourne le chemin absolu du dossier collège dans colleges_root, ou None.

        Ordre :
          1. PDF_COLLEGE_MAPPING (override explicite notion_name → dossier)
          2. Nom brut (si le dossier existe avec ce nom exact)
          3. Scan + correspondance normalisée (emojis strippés + lowercase)
        """
        # 1. Override explicite
        if notion_name in PDF_COLLEGE_MAPPING:
            path = os.path.join(colleges_root, PDF_COLLEGE_MAPPING[notion_name])
            if os.path.isdir(path):
                return path

        # 2. Nom brut tel quel
        path = os.path.join(colleges_root, notion_name)
        if os.path.isdir(path):
            return path

        # 3. Scan normalisé (strip emoji + lowercase)
        notion_norm = _normalize_college_name(notion_name)
        if not notion_norm:
            return None
        try:
            entries = os.listdir(colleges_root)
        except OSError:
            return None
        for entry in entries:
            entry_path = os.path.join(colleges_root, entry)
            if os.path.isdir(entry_path) and _normalize_college_name(entry) == notion_norm:
                logger.debug(f"PDF college match: '{notion_name}' → '{entry}'")
                return entry_path
        return None

    async def auto_detect_pdf(self, course, context: str = "college") -> "str | None":
        """
        Détecte automatiquement le PDF local le plus probable pour un cours.

        Logique :
          1. Guard : si l'URL PDF Notion est déjà renseignée → None (rien à faire)
          2. Cache SQLite : si un chemin valide est en cache → retourner directement
          3. Construction du search_path selon le contexte
          4. [College uniquement] Lookup direct par numéro d'item dans items/
          5. Peuplement du cache FileService + recherche floue (fallback)
          6. Persistence SQLite et retour du chemin trouvé

        Paramètres :
            course  : objet Cours Notion avec .id, .url_pdf, .url_pdf_ue,
                      .college, .title, .item_number
            context : 'college' (collège EDN) ou 'ue' (poly de fac)

        Retourne :
            str  : chemin absolu du PDF détecté
            None : aucun PDF détecté avec confiance suffisante
        """
        from backend.core.reviews import local_store  # lazy import — avoids potential circular at startup

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
            college_name = course.college[0] if course.college else ""
            colleges_root = os.path.join(settings.medicine_dir, "Collèges")
            college_dir = self._get_college_folder(colleges_root, college_name)
            search_path = college_dir or colleges_root
        else:
            search_path = settings.fac_dir or settings.medicine_dir

        if not search_path or not os.path.exists(search_path):
            return None

        # ── 4. Lookup direct par numéro d'item (college uniquement) ──────────
        if context == "college" and getattr(course, "item_number", None):
            try:
                item_num = int(float(course.item_number))
                direct = self._find_pdf_by_item_number_in_items_dir(search_path, item_num)
                if direct:
                    logger.success(
                        f"PDF auto-link: Item {item_num} → {os.path.basename(direct)!r} "
                        f"(lookup direct)"
                    )
                    local_store.set_pdf_cache(course.id, context, direct)
                    return direct
            except (ValueError, TypeError):
                pass

        # ── 5. Peuplement du cache FileService + recherche floue ─────────────
        if search_path not in self.pdf_caches:
            await self.refresh_cache_async(search_path)

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
