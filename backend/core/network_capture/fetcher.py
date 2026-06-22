"""
network_capture/fetcher.py
---------------------------
Récupère les données QCM depuis Hypocampus / EDN Pro.

EDN Pro utilise Supabase/PostgREST :
  base URL : https://hiwarmfutyzsdlmqicvc.supabase.co
  apikey   : clé anon publique (fixe, embarquée dans le frontend)
  auth     : Bearer JWT de session (~1h) — à recopier depuis DevTools
             F12 → Network → clic sur une requête → Request Headers → Authorization

Config stockée dans data/ednpro_credentials.json (gitignore).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from loguru import logger

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

_ROOT = Path(__file__).parent.parent.parent.parent

# ── Constantes EDN Pro (publiques — présentes dans le JS du frontend) ─────────

EDNPRO_SUPABASE_URL = "https://hiwarmfutyzsdlmqicvc.supabase.co"
EDNPRO_ANON_KEY = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
    ".eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Imhpd2FybWZ1dHl6c2RsbXFpY3ZjIiwi"
    "cm9sZSI6ImFub24iLCJpYXQiOjE3NzA3MTM0MjIsImV4cCI6MjA4NjI4OTQyMn0"
    ".3SPgcoYsd47VJJsgVBjnvwwo7b4JkzRZasBWQRzhTSA"
)

EDNPRO_CREDS_PATH = _ROOT / "data" / "ednpro_credentials.json"


# ── Config des plateformes ─────────────────────────────────────────────────────

PLATFORM_CONFIG: dict[str, dict] = {
    "Hypocampus": {
        "base_url": "https://www.hypocampus.fr",
        # Endpoints à remplir après discover (scripts/capture_qcm.py discover session.har)
        "endpoints": [],
        "headers": {
            "Accept": "application/json",
        },
    },
    "EDNpro": {
        "base_url": EDNPRO_SUPABASE_URL,
        # Endpoints remplis après discover-tables (voir ci-dessous)
        # Exemples PostgREST :
        # "/rest/v1/objective_sessions?select=*,course:courses(title,item_edn)"
        #     "&user_id=eq.<user_id>&order=created_at.desc&limit=500"
        "endpoints": [],
        "headers": {
            "Accept": "application/json",
            "apikey": EDNPRO_ANON_KEY,
            # Authorization: chargé depuis data/ednpro_credentials.json à l'exécution
        },
    },
}


# ── Chargement des credentials EDN Pro ────────────────────────────────────────

def load_ednpro_credentials() -> dict:
    """
    Charge data/ednpro_credentials.json.
    Si absent, crée un template et lève une erreur explicative.
    """
    if not EDNPRO_CREDS_PATH.exists():
        _create_credentials_template()
        raise FileNotFoundError(
            f"Credentials EDN Pro manquants. Template créé dans :\n"
            f"  {EDNPRO_CREDS_PATH}\n\n"
            "Pour remplir le Bearer token :\n"
            "  F12 -> Network -> clique sur une requête -> Request Headers -> Authorization\n"
            "  Copie tout après 'Bearer ' dans le champ 'bearer_token'"
        )
    return json.loads(EDNPRO_CREDS_PATH.read_text(encoding="utf-8"))


def save_ednpro_credentials(
    bearer_token: str | None = None,
    refresh_token: str | None = None,
    user_id: str | None = None,
) -> None:
    """Sauvegarde / met à jour les credentials EDN Pro."""
    EDNPRO_CREDS_PATH.parent.mkdir(parents=True, exist_ok=True)
    existing: dict = {}
    if EDNPRO_CREDS_PATH.exists():
        try:
            existing = json.loads(EDNPRO_CREDS_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass

    existing["base_url"] = EDNPRO_SUPABASE_URL
    existing["apikey"]   = EDNPRO_ANON_KEY
    if bearer_token:
        existing["bearer_token"]  = bearer_token.removeprefix("Bearer ").strip()
    if refresh_token:
        existing["refresh_token"] = refresh_token.strip()
    if user_id:
        existing["user_id"] = user_id

    EDNPRO_CREDS_PATH.write_text(
        json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    logger.success(f"Credentials sauvegardés : {EDNPRO_CREDS_PATH}")


def refresh_ednpro_token(refresh_token: str) -> tuple[str, str]:
    """
    Échange un refresh_token contre un nouveau access_token.
    Retourne (new_access_token, new_refresh_token).
    Supabase fait du token rotation : le refresh_token change à chaque appel.
    """
    if not HAS_REQUESTS:
        raise ImportError("pip install requests")

    url = f"{EDNPRO_SUPABASE_URL}/auth/v1/token?grant_type=refresh_token"
    r = requests.post(
        url,
        json={"refresh_token": refresh_token},
        headers={
            "apikey":        EDNPRO_ANON_KEY,
            "Content-Type":  "application/json",
        },
        timeout=15,
    )
    if r.status_code == 400:
        raise ValueError(
            "Refresh token invalide ou expiré.\n"
            "  -> Lance : python scripts/capture_qcm.py init-ednpro\n"
            "  -> Et colle le JSON depuis la console du navigateur."
        )
    r.raise_for_status()
    data = r.json()
    return data["access_token"], data["refresh_token"]


def _create_credentials_template() -> None:
    EDNPRO_CREDS_PATH.parent.mkdir(parents=True, exist_ok=True)
    template = {
        "base_url":      EDNPRO_SUPABASE_URL,
        "apikey":        EDNPRO_ANON_KEY,
        "user_id":       "abc3070a-4620-4465-bb45-5ba71e84c294",
        "bearer_token":  "",
        "refresh_token": "COLLER_ICI_LE_REFRESH_TOKEN_DEPUIS_LA_CONSOLE",
    }
    EDNPRO_CREDS_PATH.write_text(
        json.dumps(template, ensure_ascii=False, indent=2), encoding="utf-8"
    )


# ── Helpers cookies (Hypocampus) ───────────────────────────────────────────────

def load_cookies(cookies_path: str | Path) -> dict[str, str]:
    data = json.loads(Path(cookies_path).read_text(encoding="utf-8"))
    if isinstance(data, dict):
        return {k: str(v) for k, v in data.items()}
    if isinstance(data, list):
        return {c["name"]: c["value"] for c in data if "name" in c and "value" in c}
    raise ValueError("Format cookies.json non reconnu (attendu list ou dict)")


# ── Fetcher générique (Hypocampus) ────────────────────────────────────────────

class PlatformFetcher:
    def __init__(self, platform: str, cookies: dict[str, str]):
        if platform not in PLATFORM_CONFIG:
            raise ValueError(f"Plateforme inconnue : {platform}")
        if not HAS_REQUESTS:
            raise ImportError("pip install requests")

        self.platform = platform
        self.config   = PLATFORM_CONFIG[platform]
        self.session  = requests.Session()
        self.session.cookies.update(cookies)
        self.session.headers.update(self.config.get("headers", {}))

    def fetch_all(self, dump_dir: Path) -> list[dict]:
        dump_dir.mkdir(parents=True, exist_ok=True)
        endpoints = self.config.get("endpoints", [])

        if not endpoints:
            logger.warning(f"Aucun endpoint configuré pour {self.platform}.")
            return []

        results = []
        base = self.config["base_url"]
        for i, endpoint in enumerate(endpoints, 1):
            url = base + endpoint
            logger.info(f"Fetch {i}/{len(endpoints)} : {url}")
            try:
                r = self.session.get(url, timeout=15)
                r.raise_for_status()
                data = r.json()
                slug = endpoint.replace("/", "_").replace("?", "_").strip("_")[:50]
                fname = f"{i:02d}_{slug}.json"
                (dump_dir / fname).write_text(
                    json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
                )
                logger.success(f"  ok {fname}")
                results.append({"url": url, "endpoint": endpoint, "data": data})
            except Exception as exc:
                logger.error(f"  err {url} -> {exc}")

        return results

    def probe_endpoints(self, candidates: list[str], dump_dir: Path) -> list[dict]:
        dump_dir.mkdir(parents=True, exist_ok=True)
        hits = []
        base = self.config["base_url"]
        for ep in candidates:
            url = base + ep
            try:
                r = self.session.get(url, timeout=8)
                if r.status_code == 200 and "json" in r.headers.get("content-type", ""):
                    hits.append({"url": url, "endpoint": ep, "data": r.json()})
                    logger.success(f"  ok {url}")
                else:
                    logger.debug(f"  {r.status_code} {url}")
            except Exception:
                logger.debug(f"  err {url}")
        return hits


# ── Fetcher Supabase/EDN Pro ───────────────────────────────────────────────────

class SupabaseFetcher:
    """
    Fetcher dédié à l'API Supabase/PostgREST d'EDN Pro.
    Charge les credentials depuis data/ednpro_credentials.json.
    """

    def __init__(self):
        if not HAS_REQUESTS:
            raise ImportError("pip install requests")

        creds = load_ednpro_credentials()
        self.base_url = creds.get("base_url", EDNPRO_SUPABASE_URL)
        self.user_id  = creds.get("user_id", "")
        self._creds   = creds

        bearer = self._get_valid_token(creds)

        self.session = requests.Session()
        self.session.headers.update({
            "Accept":         "application/json",
            "Accept-Profile": "public",
            "apikey":         creds.get("apikey", EDNPRO_ANON_KEY),
            "Authorization":  f"Bearer {bearer}",
        })

    def _get_valid_token(self, creds: dict) -> str:
        """
        Retourne un access token valide.
        Si refresh_token disponible, l'utilise pour générer un nouveau token
        sans intervention manuelle. Sauvegarde le nouveau token dans le fichier.
        """
        import time as _time

        refresh_token = creds.get("refresh_token", "")
        bearer        = creds.get("bearer_token", "")

        # Vérifie si le bearer est expiré (décode le JWT sans vérification de signature)
        if bearer and not refresh_token:
            return bearer  # Pas de refresh token → utilise ce qu'on a

        if refresh_token and refresh_token != "COLLER_ICI_LE_REFRESH_TOKEN_DEPUIS_LA_CONSOLE":
            # Vérifie l'expiration du token actuel
            expired = True
            if bearer:
                try:
                    import base64, json as _json
                    payload = bearer.split(".")[1]
                    payload += "=" * (4 - len(payload) % 4)
                    decoded = _json.loads(base64.b64decode(payload))
                    exp = decoded.get("exp", 0)
                    expired = exp < _time.time() + 60  # renouvelle 60s avant expiry
                except Exception:
                    expired = True

            if expired:
                logger.info("Token expiré — renouvellement automatique via refresh token...")
                try:
                    new_bearer, new_refresh = refresh_ednpro_token(refresh_token)
                    save_ednpro_credentials(
                        bearer_token=new_bearer,
                        refresh_token=new_refresh,
                        user_id=self.user_id,
                    )
                    logger.success("Token renouvelé automatiquement.")
                    return new_bearer
                except Exception as e:
                    logger.warning(f"Renouvellement échoué : {e}")
                    if bearer:
                        return bearer
                    raise
            return bearer

        if bearer:
            return bearer

        raise ValueError(
            "Aucun token disponible.\n"
            "  -> Lance : python scripts/capture_qcm.py init-ednpro"
        )

    def _rest(self, table: str, params: str = "") -> list:
        """GET /rest/v1/<table>?<params> → liste JSON. Auto-refresh sur 401."""
        url = f"{self.base_url}/rest/v1/{table}"
        if params:
            url += f"?{params}"
        r = self.session.get(url, timeout=15)

        if r.status_code == 401:
            # Tente un refresh automatique
            refresh = self._creds.get("refresh_token", "")
            if refresh and refresh != "COLLER_ICI_LE_REFRESH_TOKEN_DEPUIS_LA_CONSOLE":
                logger.info("401 reçu — tentative de refresh automatique...")
                try:
                    new_bearer, new_refresh = refresh_ednpro_token(refresh)
                    self._creds["refresh_token"] = new_refresh
                    self._creds["bearer_token"]  = new_bearer
                    save_ednpro_credentials(bearer_token=new_bearer,
                                            refresh_token=new_refresh)
                    self.session.headers["Authorization"] = f"Bearer {new_bearer}"
                    r = self.session.get(url, timeout=15)
                    if r.status_code != 401:
                        r.raise_for_status()
                        data = r.json()
                        return data if isinstance(data, list) else [data]
                except Exception as e:
                    logger.warning(f"Refresh échoué : {e}")

            raise PermissionError(
                "Token expiré et refresh impossible.\n"
                "  -> Lance : python scripts/capture_qcm.py init-ednpro"
            )

        r.raise_for_status()
        data = r.json()
        return data if isinstance(data, list) else [data]

    # Tables candidates connues pour EDN Pro (basées sur l'URL objective-session/multi)
    _QCM_TABLE_CANDIDATES = [
        "objective_sessions",
        "objective_session",
        "session_questions",
        "session_answers",
        "session_results",
        "user_sessions",
        "user_objectives",
        "user_results",
        "question_attempts",
        "training_sessions",
        "qcm_sessions",
        "qcm_results",
        "exam_sessions",
        "quiz_sessions",
        "attempts",
        "results",
    ]

    def probe_qcm_tables(self, dump_dir: Path) -> dict[str, list]:
        """
        Teste les tables candidates en filtrant sur user_id.
        Retourne {table_name: [rows]} pour les tables non vides.
        """
        dump_dir.mkdir(parents=True, exist_ok=True)
        candidates = self._QCM_TABLE_CANDIDATES
        logger.info(f"Sondage de {len(candidates)} tables candidates...")


        hits = {}
        for table in candidates:
            rows = self._probe_table(table)
            if rows is not None:
                logger.success(f"  [{len(rows)} row(s)] {table}  cles: {list(rows[0].keys())[:6] if rows else []}")
                hits[table] = rows
                (dump_dir / f"{table}.json").write_text(
                    json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8"
                )
            # None = pas de données ou table inexistante (déjà loggué)

        # Sauvegarde l'index
        index = {t: len(v) for t, v in hits.items()}
        (dump_dir / "_index.json").write_text(
            json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return hits

    def _probe_table(self, table: str) -> list | None:
        """
        Sonde une table avec plusieurs variantes de requête.
        Retourne une liste de rows (peut être vide) ou None si la table n'existe pas.
        """
        uid = self.user_id

        # Ordre de tentative : du plus précis au plus minimal
        attempts = [
            # Avec user_id + order
            f"select=*&order=created_at.desc&limit=5&user_id=eq.{uid}" if uid else None,
            # Avec user_id sans order
            f"select=*&limit=5&user_id=eq.{uid}" if uid else None,
            # Sans user_id, avec order
            "select=*&order=created_at.desc&limit=5",
            # Minimal
            "select=*&limit=5",
            # Sans select
            "limit=5",
        ]

        for params in attempts:
            if params is None:
                continue
            try:
                url = f"{self.base_url}/rest/v1/{table}?{params}"
                r = self.session.get(url, timeout=10)
                if r.status_code == 404:
                    logger.debug(f"  [404] {table}")
                    return None  # Table n'existe pas
                if r.status_code == 200:
                    data = r.json()
                    rows = data if isinstance(data, list) else [data]
                    return rows
                if r.status_code in (400, 406):
                    logger.debug(f"  [{r.status_code}] {table} avec '{params}' -> essai suivant")
                    continue
                if r.status_code == 401:
                    raise PermissionError("Token Bearer expire.")
                logger.debug(f"  [{r.status_code}] {table}")
            except PermissionError:
                raise
            except Exception as exc:
                logger.debug(f"  [err] {table}: {exc}")
                return None

        logger.debug(f"  [skip] {table} — aucune variante de requete n'a fonctionne")
        return None

    def _extract_course_uuid(self, resume_path: str) -> str | None:
        """Extrait le UUID de cours depuis resume_path (?courses=<uuid>&...)."""
        import re
        m = re.search(r"courses=([a-f0-9\-]{36})", resume_path or "")
        return m.group(1) if m else None

    def fetch_questions_and_propositions(self, question_ids: list[str]) -> dict:
        """
        Batch-fetch objective_questions + objective_question_propositions.
        Retourne {question_uuid: {question_text, explanation, type, propositions: [...]}}.

        Traite par lots de 200 pour rester sous les limites URL de PostgREST.
        """
        if not question_ids:
            return {}

        result: dict[str, dict] = {}
        batch_size = 200

        # Batch fetch objective_questions
        for i in range(0, len(question_ids), batch_size):
            batch = question_ids[i:i + batch_size]
            uuids_str = ",".join(batch)
            try:
                q_rows = self._rest(
                    "objective_questions",
                    f"select=id,question_text,explanation,type,tags&id=in.({uuids_str})"
                )
                for q in q_rows:
                    result[q["id"]] = {
                        "question_text": q.get("question_text") or "",
                        "explanation":   q.get("explanation") or "",
                        "type":          q.get("type") or "qcm",
                        "tags":          q.get("tags") or [],
                        "propositions":  [],
                    }
            except Exception as e:
                logger.warning(f"Fetch objective_questions batch {i//batch_size + 1}: {e}")

        # Batch fetch objective_question_propositions
        for i in range(0, len(question_ids), batch_size):
            batch = question_ids[i:i + batch_size]
            uuids_str = ",".join(batch)
            try:
                p_rows = self._rest(
                    "objective_question_propositions",
                    f"select=id,question_id,label,proposition_text,is_correct&question_id=in.({uuids_str})"
                )
                for p in p_rows:
                    qid = p.get("question_id")
                    if qid and qid in result:
                        result[qid]["propositions"].append({
                            "id":         p.get("id", ""),
                            "label":      p.get("label") or "",
                            "text":       p.get("proposition_text") or "",
                            "is_correct": bool(p.get("is_correct")),
                        })
            except Exception as e:
                logger.warning(f"Fetch propositions batch {i//batch_size + 1}: {e}")

        logger.info(f"Questions chargées : {len(result)} avec propositions")
        return result

    def fetch_training_sessions(self, limit: int = 500) -> list:
        """
        Fetch de training_sessions : item, nom du cours, score, horodatage.
        """
        uid = self.user_id
        rows = self._rest(
            "training_sessions",
            f"select=*&completed=eq.true&order=completed_at.desc&limit={limit}&user_id=eq.{uid}"
        )
        if not rows:
            return []

        # Batch fetch noms + item_number des cours (une seule requête)
        course_uuids = set()
        for r in rows:
            uuid = self._extract_course_uuid(r.get("resume_path", ""))
            if uuid:
                course_uuids.add(uuid)

        course_map: dict[str, dict] = {}
        if course_uuids:
            uuids_str = ",".join(course_uuids)
            try:
                course_rows = self._rest(
                    "courses",
                    f"select=id,name,item_number&id=in.({uuids_str})"
                )
                for c in course_rows:
                    course_map[c["id"]] = {
                        "name":        c.get("name", ""),
                        "item_number": str(c.get("item_number") or ""),
                    }
                logger.info(f"Cours trouvés : {len(course_map)}")
            except Exception as e:
                logger.warning(f"Impossible de charger les cours : {e}")

        for r in rows:
            uuid = self._extract_course_uuid(r.get("resume_path", ""))
            info = course_map.get(uuid, {}) if uuid else {}
            r["_course_name"] = info.get("name", "")
            r["_item_number"] = info.get("item_number", "")
            r["_questions"]   = []

        return rows

    def fetch_qcm_history(self, table: str, limit: int = 500) -> list:
        """
        Récupère l'historique QCM depuis une table connue.
        Essaie plusieurs colonnes d'ordre et plusieurs FK de cours.
        """
        uid = f"user_id=eq.{self.user_id}" if self.user_id else ""
        uid_suffix = f"&{uid}" if uid else ""

        # Colonnes d'ordre à essayer (quiz_sessions a completed_at / started_at, pas created_at)
        order_cols = ["completed_at", "started_at", "created_at", "id"]

        # Essai 1 : avec join FK cours (pour récupérer title + item en une requête)
        for course_fk in ("course:courses(title,item_edn)",
                           "objective:objectives(title,item_edn)",
                           "theme:themes(title,item_edn)",
                           "course:courses(title)",
                           "objective:objectives(title)"):
            for order_col in order_cols:
                try:
                    select = f"*,{course_fk}"
                    params = f"select={select}&order={order_col}.desc&limit={limit}{uid_suffix}"
                    rows = self._rest(table, params)
                    if rows:
                        logger.success(f"Fetch avec FK ({course_fk}) : {len(rows)} sessions")
                        return rows
                except Exception:
                    continue

        # Essai 2 : sans join, avec différentes colonnes d'ordre
        for order_col in order_cols:
            try:
                params = f"select=*&order={order_col}.desc&limit={limit}{uid_suffix}"
                rows = self._rest(table, params)
                logger.success(f"Fetch simple (order={order_col}) : {len(rows)} sessions depuis {table}")
                return rows
            except Exception:
                continue

        # Essai 3 : minimal sans ordre ni user_id
        params = f"select=*&limit={limit}"
        rows = self._rest(table, params)
        logger.success(f"Fetch minimal : {len(rows)} sessions depuis {table}")
        return rows


# ── Candidats Hypocampus ───────────────────────────────────────────────────────
# Endpoints GET candidats pour l'historique des sessions.
# Priorité : endpoints /api/hypo3/v1/ confirmés actifs depuis capture réseau.

HYPOCAMPUS_CANDIDATES = [
    # hypo3/v1 API (confirmé depuis capture réseau — auth: Bearer JWT)
    "/api/hypo3/v1/qs/sessions",
    "/api/hypo3/v1/qs/history",
    "/api/hypo3/v1/qs/user/sessions",
    "/api/hypo3/v1/qs/results",
    "/api/hypo3/v1/sessions",
    "/api/hypo3/v1/user/sessions",
    "/api/hypo3/v1/results",
    "/api/hypo3/v1/quiz-sessions",
    "/api/hypo3/v1/courses/progress",
    # v2 API
    "/api/v2/sessions",
    "/api/v2/quiz-sessions",
    "/api/v2/history",
    "/api/v2/results",
    # v1 legacy
    "/api/v1/quiz-sessions",
    "/api/v1/quiz_sessions",
    "/api/v1/sessions",
    "/api/v1/results",
    "/api/v1/history",
    "/api/v1/user/sessions",
    "/api/v1/me/sessions",
    "/api/v1/me/results",
    "/api/v1/training/sessions",
    "/api/v1/training/results",
]

CANDIDATES: dict[str, list[str]] = {
    "Hypocampus": HYPOCAMPUS_CANDIDATES,
    "EDNpro":     [],  # EDN Pro : utilise SupabaseFetcher.probe_qcm_tables()
}


# ── Credentials Hypocampus ─────────────────────────────────────────────────────

HYPOCAMPUS_CREDS_PATH = _ROOT / "data" / "hypocampus_credentials.json"
HYPOCAMPUS_BASE_URL   = "https://www.hypocampus.fr"


def save_hypocampus_credentials(
    bearer_token: str | None = None,
    access_token: str | None = None,
    user_id: str | None = None,
    endpoints: list | None = None,
) -> None:
    """
    Sauvegarde les tokens JWT Hypocampus.
    bearer_token = privilegeToken (pour vérification expiry)
    access_token = cortexio.accessToken (pour les appels API QCM)
    """
    HYPOCAMPUS_CREDS_PATH.parent.mkdir(parents=True, exist_ok=True)
    existing: dict = {}
    if HYPOCAMPUS_CREDS_PATH.exists():
        try:
            existing = json.loads(HYPOCAMPUS_CREDS_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    if bearer_token:
        existing["bearer_token"] = bearer_token.removeprefix("Bearer ").strip()
    if access_token:
        existing["access_token"] = access_token.removeprefix("Bearer ").strip()
    if user_id:
        existing["user_id"] = user_id
    if endpoints is not None:
        existing["endpoints"] = endpoints
    elif "endpoints" not in existing:
        existing["endpoints"] = []
    HYPOCAMPUS_CREDS_PATH.write_text(
        json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    logger.success(f"Credentials Hypocampus sauvegardés : {HYPOCAMPUS_CREDS_PATH}")


def load_hypocampus_credentials() -> dict:
    """Charge data/hypocampus_credentials.json. Lève FileNotFoundError si absent."""
    if not HYPOCAMPUS_CREDS_PATH.exists():
        raise FileNotFoundError(
            "Token Hypocampus manquant.\n"
            "Lance : python scripts/capture_qcm.py init-hypocampus\n"
            "  (ou setup-hypocampus si tu préfères copier le token manuellement)"
        )
    return json.loads(HYPOCAMPUS_CREDS_PATH.read_text(encoding="utf-8"))


def _hypocampus_token_expired(bearer: str) -> bool:
    """Vérifie si le JWT Hypocampus est expiré (décode sans vérification de signature)."""
    import base64
    import json as _json
    import time as _time
    try:
        payload = bearer.split(".")[1]
        payload += "=" * (4 - len(payload) % 4)
        decoded = _json.loads(base64.b64decode(payload))
        exp = decoded.get("exp", 0)
        return exp < _time.time() + 300  # renouvelle 5 min avant expiry
    except Exception:
        return True  # si on ne peut pas décoder, on considère expiré


def _extract_user_id_from_jwt(bearer: str) -> str:
    """Extrait le user_id (jti/aid) depuis le payload JWT."""
    import base64
    import json as _json
    try:
        payload = bearer.split(".")[1]
        payload += "=" * (4 - len(payload) % 4)
        decoded = _json.loads(base64.b64decode(payload))
        return str(decoded.get("jti") or decoded.get("aid") or decoded.get("sub") or "")
    except Exception:
        return ""


# ── Fetcher Hypocampus ─────────────────────────────────────────────────────────

class HypocampusFetcher:
    """
    Fetcher dédié à l'API Hypocampus.
    Authentification via JWT Bearer token (comme EDN Pro).

    Workflow :
      1. python scripts/capture_qcm.py init-hypocampus    (une seule fois — JS snippet)
      2. python scripts/capture_qcm.py discover-hypocampus  (trouve les endpoints GET)
      3. python scripts/capture_qcm.py fetch-hypocampus   (régulier — toutes les semaines)

    Token valide ~7 jours. Relance init-hypocampus ou setup-hypocampus si expiré.
    """

    BASE_URL = HYPOCAMPUS_BASE_URL

    def __init__(self) -> None:
        if not HAS_REQUESTS:
            raise ImportError("pip install requests")

        creds = load_hypocampus_credentials()
        bearer = creds.get("bearer_token", "")  # privilegeToken — pour expiry check

        if not bearer:
            raise ValueError(
                "Token Bearer Hypocampus vide.\n"
                "Lance : python scripts/capture_qcm.py init-hypocampus"
            )

        if _hypocampus_token_expired(bearer):
            logger.warning(
                "Token Bearer Hypocampus expiré ou bientôt expiré.\n"
                "  -> Lance : python scripts/capture_qcm.py init-hypocampus\n"
                "  -> Ou relance setup-hypocampus avec un nouveau token F12."
            )

        # cortexio.accessToken — token utilisé par l'API QCM (/api/hypo3/v1/qs/...)
        # Fallback sur bearer_token si access_token absent (anciens credentials)
        access = creds.get("access_token") or bearer

        # Extraire user_id depuis JWT si pas en config
        self.user_id = creds.get("user_id") or _extract_user_id_from_jwt(bearer)
        self.endpoints: list[str] = creds.get("endpoints", [])

        self.session = requests.Session()
        self.session.headers.update({
            "Accept":        "application/json",
            "Authorization": f"Bearer {access}",
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0.0.0 Safari/537.36"
            ),
        })

    # ── Découverte automatique des endpoints GET ───────────────────────────────

    def probe_all_endpoints(self, dump_dir: Path) -> list[str]:
        """
        Sonde tous les endpoints candidats avec le Bearer JWT.
        Sauvegarde les endpoints valides dans hypocampus_credentials.json.
        """
        dump_dir.mkdir(parents=True, exist_ok=True)
        found: list[str] = []
        got_401 = False

        # Ajoute des variantes personnalisées avec le user_id
        uid = self.user_id
        uid_candidates: list[str] = []
        if uid:
            uid_candidates = [
                f"/api/hypo3/v1/qs/sessions?userId={uid}",
                f"/api/hypo3/v1/qs/user/{uid}/sessions",
                f"/api/hypo3/v1/user/{uid}/sessions",
                f"/api/hypo3/v1/users/{uid}/sessions",
                f"/api/v2/users/{uid}/sessions",
                f"/api/v2/user/{uid}/sessions",
            ]

        candidates = uid_candidates + [
            ep for ep in HYPOCAMPUS_CANDIDATES if ep not in uid_candidates
        ]

        logger.info(f"Sondage de {len(candidates)} endpoints Hypocampus (user_id={uid})...")

        for ep in candidates:
            url = self.BASE_URL + ep
            try:
                r = self.session.get(url, timeout=10)
                if r.status_code == 401:
                    logger.warning(f"  [401] {ep} — token expiré ?")
                    got_401 = True
                    continue
                if r.status_code == 200:
                    ct = r.headers.get("content-type", "")
                    if "json" in ct:
                        data = r.json()
                        row_count = len(data) if isinstance(data, list) else (
                            len(data.get("content") or data.get("data") or data.get("sessions") or [])
                            if isinstance(data, dict) else "?"
                        )
                        fname = ep.replace("/", "_").strip("_") + ".json"
                        (dump_dir / fname).write_text(
                            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
                        )
                        logger.success(f"  [ok] {ep}  → {row_count} élément(s)")
                        found.append(ep)
                    else:
                        logger.debug(f"  [html] {ep}")
                else:
                    logger.debug(f"  [{r.status_code}] {ep}")
            except Exception as exc:
                logger.debug(f"  [err] {ep}: {exc}")

        if got_401 and not found:
            logger.error(
                "Tous les endpoints ont retourné 401.\n"
                "  -> Token expiré (valide ~7 jours).\n"
                "  -> Lance : python scripts/capture_qcm.py init-hypocampus"
            )

        # Persiste les endpoints trouvés
        creds = load_hypocampus_credentials()
        creds["endpoints"] = found
        HYPOCAMPUS_CREDS_PATH.write_text(
            json.dumps(creds, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        return found

    # ── Fetch depuis les endpoints connus ──────────────────────────────────────

    def fetch_sessions(self, dump_dir: Path) -> list[dict]:
        """
        Récupère l'historique QCM depuis les endpoints découverts.
        Si un endpoint retourne une liste, tente aussi de fetcher les détails
        de chaque session (questions + réponses utilisateur).
        """
        if not self.endpoints:
            raise ValueError(
                "Aucun endpoint configuré.\n"
                "Lance : python scripts/capture_qcm.py discover-hypocampus"
            )

        dump_dir.mkdir(parents=True, exist_ok=True)
        results: list[dict] = []

        for ep in self.endpoints:
            url = self.BASE_URL + ep
            logger.info(f"Fetch {url}")
            try:
                r = self.session.get(url, timeout=15)
                if r.status_code == 401:
                    logger.warning(
                        "  [401] — token expiré.\n"
                        "  -> Lance : python scripts/capture_qcm.py init-hypocampus"
                    )
                    continue
                r.raise_for_status()
                data = r.json()
                fname = ep.replace("/", "_").strip("_") + "_full.json"
                (dump_dir / fname).write_text(
                    json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
                )
                count = len(data) if isinstance(data, list) else "?"
                logger.success(f"  ok — {count} élément(s)")
                results.append({"url": url, "endpoint": ep, "data": data})
            except Exception as exc:
                logger.error(f"  err {url}: {exc}")

        return results

    def fetch_all_sessions_list(self, dump_dir: Path | None = None, page_size: int = 50) -> list[dict]:
        """
        Récupère TOUTES les sessions Hypocampus via l'endpoint paginé
        GET /api/hypo3/v1/qs/sessions/latest/all?limit=N&nextToken=...

        Le nextToken est un curseur DynamoDB base64 — NE PAS URL-encoder les '='
        (le serveur lit la valeur brute jusqu'au prochain '&').

        Retourne la liste de toutes les sessions (format plat, sans statistics{}).
        """
        url_base = f"{self.BASE_URL}/api/hypo3/v1/qs/sessions/latest/all"
        all_sessions: list[dict] = []
        next_token: str | None = None
        page = 0

        while True:
            url = f"{url_base}?limit={page_size}"
            if next_token:
                url += f"&nextToken={next_token}"

            try:
                r = self.session.get(url, timeout=15)
                if r.status_code == 401:
                    logger.warning("fetch_all_sessions_list: token expiré (401).")
                    break
                r.raise_for_status()
                data = r.json()
            except Exception as exc:
                logger.error(f"fetch_all_sessions_list page {page + 1}: {exc}")
                break

            sessions = data.get("sessions", []) if isinstance(data, dict) else data
            all_sessions.extend(sessions)
            page += 1
            logger.info(f"  Page {page}: {len(sessions)} sessions (total {len(all_sessions)})")

            next_token = data.get("nextToken") if isinstance(data, dict) else None
            if not next_token or not sessions:
                break

        if dump_dir:
            dump_dir.mkdir(parents=True, exist_ok=True)
            (dump_dir / "hypo_all_sessions_list.json").write_text(
                __import__("json").dumps(all_sessions, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            logger.success(f"Dump sauvegardé : {dump_dir}/hypo_all_sessions_list.json")

        logger.success(f"fetch_all_sessions_list: {len(all_sessions)} sessions en {page} page(s)")
        return all_sessions

    def fetch_session_detail(self, session_id: str) -> dict | None:
        """
        Tente de récupérer les détails d'une session (questions + réponses).
        Essaie plusieurs patterns d'URL connus.
        """
        patterns = [
            f"/api/hypo3/v1/qs/session/{session_id}",
            f"/api/hypo3/v1/qs/sessions/{session_id}",
            f"/api/hypo3/v1/qs/session/answers/{session_id}",
            f"/api/v2/sessions/{session_id}",
        ]
        for pat in patterns:
            url = self.BASE_URL + pat
            try:
                r = self.session.get(url, timeout=10)
                if r.status_code == 200:
                    ct = r.headers.get("content-type", "")
                    if "json" in ct:
                        return r.json()
            except Exception:
                pass
        return None
