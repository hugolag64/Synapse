"""
scripts/capture_qcm.py — Synapse
---------------------------------
Capture automatique des QCM Hypocampus / EDN Pro via interception réseau.

WORKFLOW EDN PRO :
------------------
1. Configuration initiale (une seule fois) :
     python scripts/capture_qcm.py init-ednpro
   -> Colle le JSON depuis la console du navigateur

2. Fetch de l'historique :
     python scripts/capture_qcm.py fetch-ednpro training_sessions

3. Dans Synapse -> bouton "Importer IA"

WORKFLOW HYPOCAMPUS :
---------------------
1. Configuration initiale (une seule fois) :
     python scripts/capture_qcm.py init-hypocampus
   -> Colle le token depuis la console du navigateur

2. Découverte automatique des endpoints :
     python scripts/capture_qcm.py discover-hypocampus

3. Fetch de l'historique (toutes les semaines — token valide ~7 jours) :
     python scripts/capture_qcm.py fetch-hypocampus

4. Dans Synapse -> bouton "Importer IA"

REFRESH TOKEN Hypocampus (quand "401 — token expiré") :
--------------------------------------------------------
  Option A (recommandé) :
    python scripts/capture_qcm.py init-hypocampus
    -> Colle le JSON depuis la console Chrome

  Option B (manuel) :
    F12 -> Network -> n'importe quelle requête hypocampus.fr
    -> Request Headers -> Authorization -> copie après "Bearer "
    python scripts/capture_qcm.py setup-hypocampus "eyJhbGci..."
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_ROOT))

from loguru import logger
from backend.core.network_capture.har import HARAnalyzer
from backend.core.network_capture.fetcher import (
    PlatformFetcher, SupabaseFetcher, HypocampusFetcher,
    load_cookies,
    save_ednpro_credentials, refresh_ednpro_token, EDNPRO_CREDS_PATH,
    save_hypocampus_credentials, load_hypocampus_credentials, HYPOCAMPUS_CREDS_PATH,
    CANDIDATES, PLATFORM_CONFIG,
)
from backend.core.network_capture.converters import extract_sessions, detect_platform
from backend.core.network_capture.writer import write_sessions

_DUMP_DIR = _ROOT / "data" / "network_capture"


# ── init-ednpro (setup automatique via refresh token — UNE SEULE FOIS) ────────

def cmd_init_ednpro(args: argparse.Namespace) -> None:
    """Config initiale via refresh token localStorage — plus jamais de F12 après."""
    JS_SNIPPET = (
        "(function(){"
        "  const key=Object.keys(localStorage).find(k=>k.includes('auth-token'));"
        "  if(!key){console.error('Token non trouve');return;}"
        "  const d=JSON.parse(localStorage.getItem(key));"
        "  console.log('SYNAPSE:'+JSON.stringify({access_token:d.access_token,refresh_token:d.refresh_token}));"
        "})();"
    )
    print("=" * 60)
    print("CONFIGURATION INITIALE EDN Pro (une seule fois)")
    print("=" * 60)
    print()
    print("1. Ouvre EDN Pro dans Chrome (connecte-toi si besoin)")
    print("2. F12 -> onglet 'Console'")
    print("3. Colle exactement ce code et appuie sur Entree :")
    print()
    print("   " + JS_SNIPPET)
    print()
    print("4. La console affiche : SYNAPSE:{\"access_token\":\"...\",\"refresh_token\":\"...\"}")
    print("   Copie tout ce JSON (de { jusqu'a } inclus)")
    print()

    try:
        raw = input("Colle le JSON ici : ").strip()
    except KeyboardInterrupt:
        print()
        sys.exit(0)

    if raw.startswith("SYNAPSE:"):
        raw = raw[len("SYNAPSE:"):]

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        logger.error("JSON invalide. Copie tout de { jusqu'a }.")
        sys.exit(1)

    access_token  = data.get("access_token", "")
    refresh_token = data.get("refresh_token", "")
    if not refresh_token:
        logger.error("refresh_token manquant.")
        sys.exit(1)

    save_ednpro_credentials(
        bearer_token=access_token,
        refresh_token=refresh_token,
        user_id="abc3070a-4620-4465-bb45-5ba71e84c294",
    )
    logger.success(
        "Configuration terminee ! Python se reconnectera automatiquement.\n"
        "Lance maintenant : python scripts/capture_qcm.py fetch-ednpro training_sessions"
    )


# ── setup-ednpro (fallback manuel) ────────────────────────────────────────────

def cmd_setup_ednpro(args: argparse.Namespace) -> None:
    """Sauvegarde le Bearer token EDN Pro."""
    token = getattr(args, "bearer_token", None)

    if not token:
        logger.info(
            "Pour obtenir ton token Bearer :\n"
            "  1. Ouvre EDN Pro dans Chrome\n"
            "  2. F12 -> onglet Network\n"
            "  3. Clique sur n'importe quelle requete (ex: user_roles?select=...)\n"
            "  4. Headers -> Request Headers -> Authorization\n"
            "  5. Copie tout le texte apres 'Bearer ' (le long JWT)\n\n"
            "  Puis : python scripts/capture_qcm.py setup-ednpro \"eyJhbGci...\"\n"
        )
        # Mode interactif si pas d'argument
        try:
            token = input("Colle le JWT Bearer ici (ou Ctrl+C pour annuler) : ").strip()
        except KeyboardInterrupt:
            print()
            sys.exit(0)

    if not token or token.startswith("COLLER"):
        logger.error("Token invalide.")
        sys.exit(1)

    user_id = getattr(args, "user_id", None) or "abc3070a-4620-4465-bb45-5ba71e84c294"
    save_ednpro_credentials(token, user_id=user_id)
    logger.success("Token sauvegarde. Lance maintenant : python scripts/capture_qcm.py discover-tables")


# ── discover-tables ───────────────────────────────────────────────────────────

def cmd_discover_tables(args: argparse.Namespace) -> None:
    """Liste toutes les tables Supabase accessibles et sonde les candidates QCM."""
    fetcher = SupabaseFetcher()
    dump_dir = _DUMP_DIR / "ednpro_tables"

    logger.info("Interrogation de l'API Supabase EDN Pro...")
    logger.info(f"Dumps -> {dump_dir}")

    hits = fetcher.probe_qcm_tables(dump_dir)

    if not hits:
        logger.warning(
            "Aucune table QCM trouvee. Possibles causes :\n"
            "  - Token Bearer expire -> python scripts/capture_qcm.py setup-ednpro\n"
            "  - Les tables QCM ne filtrent pas sur user_id (essaie sans filtrer)\n"
        )
        return

    logger.success(f"\nTables avec donnees ({len(hits)}) :")
    for table, rows in hits.items():
        sample_keys = list(rows[0].keys())[:8] if rows else []
        logger.info(f"  {table:40s} {len(rows)} rows  cles: {sample_keys}")

    logger.info(
        f"\nProchaine etape :\n"
        f"  python scripts/capture_qcm.py fetch-ednpro <TABLE>\n"
        f"  Exemple : python scripts/capture_qcm.py fetch-ednpro {list(hits.keys())[0]}"
    )


# ── fetch-ednpro ──────────────────────────────────────────────────────────────

def cmd_fetch_ednpro(args: argparse.Namespace) -> None:
    """Récupère l'historique QCM depuis une table Supabase connue."""
    table = args.table
    limit = getattr(args, "limit", 500)

    fetcher = SupabaseFetcher()
    dump_dir = _DUMP_DIR / "ednpro_fetch"
    dump_dir.mkdir(parents=True, exist_ok=True)

    logger.info(f"Fetch {table} (limit={limit})...")
    try:
        if table == "training_sessions":
            rows = fetcher.fetch_training_sessions(limit=limit)
        else:
            rows = fetcher.fetch_qcm_history(table, limit=limit)
    except PermissionError as e:
        logger.error(str(e))
        sys.exit(1)

    if not rows:
        logger.warning("Aucune donnee recue.")
        sys.exit(1)

    # Dump brut
    dump_path = dump_dir / f"{table}.json"
    dump_path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info(f"Dump brut : {dump_path}")

    # Conversion -> Synapse
    from backend.core.network_capture.converters import extract_sessions_ednpro
    sessions = extract_sessions_ednpro(rows)

    if not sessions:
        logger.warning(
            f"Aucune session extraite depuis {table}.\n"
            f"Inspecte {dump_path} et adapte converters.py -> extract_sessions_ednpro()"
        )
        sys.exit(1)

    fpath = write_sessions("EDNpro", sessions)
    logger.success(
        f"\n{len(sessions)} session(s) ecrites -> {fpath}\n"
        f"Lance Synapse et clique sur 'Importer IA' pour les charger."
    )


# ── init-hypocampus (setup automatique via localStorage — RECOMMANDÉ) ────────

def cmd_init_hypocampus(args: argparse.Namespace) -> None:
    """
    Configuration initiale Hypocampus via JS snippet (une seule fois).
    Relance uniquement quand le token expire (~7 jours).
    """
    JS_SNIPPET = (
        "(function(){"
        "var keys=Object.keys(localStorage);"
        "var token='';"
        "for(var i=0;i<keys.length;i++){"
        "var v=localStorage.getItem(keys[i])||'';"
        "if(v.startsWith('ey')&&v.split('.').length===3&&v.length>100){"
        "token=v;break;"
        "}"
        "try{var o=JSON.parse(v);"
        "if(o&&o.access_token){token=o.access_token;break;}"
        "if(o&&o.token&&o.token.startsWith('ey')){token=o.token;break;}"
        "}catch(e){}"
        "}"
        "if(!token){console.error('Token non trouve - lance un QCM puis reessaie');return;}"
        "console.log('SYNAPSE:'+JSON.stringify({access_token:token}));"
        "})();"
    )

    print("=" * 60)
    print("CONFIGURATION INITIALE HYPOCAMPUS")
    print("=" * 60)
    print()
    print("1. Ouvre https://www.hypocampus.fr dans Chrome (connecte-toi)")
    print("2. Lance un QCM (pour s'assurer que le token est charge en memoire)")
    print("3. F12 -> onglet 'Console'")
    print("4. Colle exactement ce code et appuie sur Entree :")
    print()
    print("   " + JS_SNIPPET)
    print()
    print("5. La console affiche : SYNAPSE:{\"access_token\":\"eyJ...\"}")
    print("   Copie tout ce JSON (de { jusqu'a } inclus)")
    print()
    print("   Si rien ne s'affiche :")
    print("   -> Utilise l'option B : python scripts/capture_qcm.py setup-hypocampus")
    print()

    try:
        raw = input("Colle le JSON ici : ").strip()
    except KeyboardInterrupt:
        print()
        sys.exit(0)

    if raw.startswith("SYNAPSE:"):
        raw = raw[len("SYNAPSE:"):]

    # Accepte JSON ou token brut
    if raw.startswith("ey") and "." in raw:
        access_token = raw
    else:
        try:
            data = json.loads(raw)
            access_token = data.get("access_token", "").strip()
        except json.JSONDecodeError:
            logger.error("Format invalide. Copie le JSON de { jusqu'a } ou le token JWT directement.")
            sys.exit(1)

    if not access_token:
        logger.error("access_token manquant.")
        sys.exit(1)

    from backend.core.network_capture.fetcher import _extract_user_id_from_jwt
    user_id = _extract_user_id_from_jwt(access_token)

    save_hypocampus_credentials(bearer_token=access_token, user_id=user_id)
    logger.success(
        f"Token sauvegarde (user_id={user_id}).\n"
        "Prochain : python scripts/capture_qcm.py discover-hypocampus"
    )


# ── setup-hypocampus (fallback manuel — copier depuis F12) ────────────────────

def cmd_setup_hypocampus(args: argparse.Namespace) -> None:
    """
    Sauvegarde manuellement un Bearer token Hypocampus (si init-hypocampus echoue).

    Comment obtenir le token :
      F12 -> Network -> filtre Fetch/XHR -> n'importe quelle requete hypocampus.fr
      -> Request Headers -> Authorization -> copie apres 'Bearer '
    """
    token = getattr(args, "bearer_token", None)

    if not token:
        print("=" * 60)
        print("SETUP HYPOCAMPUS (manuel)")
        print("=" * 60)
        print()
        print("1. Ouvre https://www.hypocampus.fr -> lance un QCM")
        print("2. F12 -> onglet Network -> filtre 'Fetch/XHR'")
        print("3. Clique sur n'importe quelle requete vers hypocampus.fr")
        print("4. Request Headers -> Authorization -> copie tout apres 'Bearer '")
        print()
        try:
            token = input("Colle le JWT Bearer ici : ").strip()
        except KeyboardInterrupt:
            print()
            sys.exit(0)

    if not token or token.startswith("COLLER"):
        logger.error("Token invalide.")
        sys.exit(1)

    from backend.core.network_capture.fetcher import _extract_user_id_from_jwt
    user_id = _extract_user_id_from_jwt(token)

    save_hypocampus_credentials(bearer_token=token, user_id=user_id)
    logger.success(
        f"Token sauvegarde (user_id={user_id}).\n"
        "Prochain : python scripts/capture_qcm.py discover-hypocampus"
    )


# ── discover-hypocampus ───────────────────────────────────────────────────────

def cmd_discover_hypocampus(args: argparse.Namespace) -> None:
    """
    Sonde automatiquement tous les endpoints Hypocampus candidats avec le JWT.
    Sauvegarde les endpoints valides pour la commande fetch-hypocampus.
    """
    dump_dir = _DUMP_DIR / "hypocampus_discovery"

    try:
        fetcher = HypocampusFetcher()
    except (FileNotFoundError, ValueError) as e:
        logger.error(str(e))
        sys.exit(1)

    logger.info(f"Dumps -> {dump_dir}")
    found = fetcher.probe_all_endpoints(dump_dir)

    if not found:
        logger.warning(
            "Aucun endpoint JSON trouve.\n"
            "  -> Si 401 : token expire -> relance init-hypocampus\n"
            "  -> Inspecte les dumps dans data/network_capture/hypocampus_discovery/"
        )
        sys.exit(1)

    logger.success(f"\n{len(found)} endpoint(s) trouve(s) :")
    for ep in found:
        logger.info(f"  {ep}")

    logger.info(
        f"\nDumps bruts -> {dump_dir}\n"
        "Inspecte ces fichiers pour verifier les donnees, puis :\n"
        "  python scripts/capture_qcm.py fetch-hypocampus"
    )


# ── fetch-hypocampus ──────────────────────────────────────────────────────────

def cmd_fetch_hypocampus(args: argparse.Namespace) -> None:
    """
    Recupere l'historique QCM Hypocampus et genere un fichier .md pour Synapse.
    Necessite d'avoir lance init-hypocampus et discover-hypocampus au prealable.
    """
    dump_dir = _DUMP_DIR / "hypocampus_fetch"

    try:
        fetcher = HypocampusFetcher()
    except (FileNotFoundError, ValueError) as e:
        logger.error(str(e))
        sys.exit(1)

    raw = fetcher.fetch_sessions(dump_dir)
    if not raw:
        logger.error(
            "Aucune donnee recue.\n"
            "  -> Si 401 : token expire -> relance init-hypocampus\n"
            "  -> Relance discover-hypocampus si les endpoints ont change"
        )
        sys.exit(1)

    all_sessions = []
    for r in raw:
        try:
            s = extract_sessions("Hypocampus", r["data"])
            all_sessions.extend(s)
            logger.info(f"  {r['endpoint']} -> {len(s)} session(s)")
        except Exception as exc:
            logger.warning(f"  {r['endpoint']} -> erreur : {exc}")

    if not all_sessions:
        dump_dir_abs = (_ROOT / "data" / "network_capture" / "hypocampus_fetch").resolve()
        logger.error(
            "Aucune session extraite.\n"
            f"  -> Inspecte les dumps dans {dump_dir_abs}\n"
            "  -> Partage un dump avec l'IA pour adapter converters.py"
        )
        sys.exit(1)

    fpath = write_sessions("Hypocampus", all_sessions)
    logger.success(
        f"\n{len(all_sessions)} session(s) -> {fpath}\n"
        "Lance Synapse et clique sur 'Importer IA' pour les charger."
    )


# ── discover (HAR) ────────────────────────────────────────────────────────────

def cmd_discover(args: argparse.Namespace) -> None:
    har_path = Path(args.har_file)
    if not har_path.exists():
        logger.error(f"Fichier HAR introuvable : {har_path}")
        sys.exit(1)

    analyzer = HARAnalyzer(har_path, dump_dir=_DUMP_DIR)
    results = analyzer.discover(min_score=getattr(args, "min_score", 10))

    if not results:
        logger.warning(
            "Aucun resultat.\n"
            "  -> Verifie que tu as capture le trafic PENDANT un QCM\n"
            "  -> Baisse --min-score a 0 pour voir toutes les requetes JSON"
        )
    else:
        logger.info(f"\nDumps -> {_DUMP_DIR}")
        logger.info("Prochain : remplis fetcher.py -> PLATFORM_CONFIG -> endpoints")


# ── fetch (Hypocampus cookie-based) ──────────────────────────────────────────

def cmd_fetch(args: argparse.Namespace) -> None:
    platform = _normalize_platform(args.platform)
    cookies  = load_cookies(args.cookies_file)
    config   = PLATFORM_CONFIG[platform]

    if not config.get("endpoints"):
        logger.error(
            f"Aucun endpoint configure pour {platform}.\n"
            "  -> Lance : python scripts/capture_qcm.py discover <fichier.har>\n"
            "  -> Puis remplis PLATFORM_CONFIG dans backend/core/network_capture/fetcher.py"
        )
        sys.exit(1)

    fetcher = PlatformFetcher(platform, cookies)
    raw = fetcher.fetch_all(_DUMP_DIR / "fetch" / platform.lower())
    if not raw:
        logger.error("Aucune donnee.")
        sys.exit(1)

    all_sessions = []
    for r in raw:
        try:
            s = extract_sessions(platform, r["data"])
            all_sessions.extend(s)
            logger.info(f"  {r['endpoint']} -> {len(s)} session(s)")
        except Exception as exc:
            logger.warning(f"  {r['endpoint']} -> {exc}")

    if not all_sessions:
        logger.error("Aucune session extraite.")
        sys.exit(1)

    fpath = write_sessions(platform, all_sessions)
    logger.success(f"\n{len(all_sessions)} session(s) -> {fpath}")


# ── convert ───────────────────────────────────────────────────────────────────

def cmd_convert(args: argparse.Namespace) -> None:
    json_path = Path(args.json_file)
    if not json_path.exists():
        logger.error(f"Fichier introuvable : {json_path}")
        sys.exit(1)

    raw      = json.loads(json_path.read_text(encoding="utf-8"))
    data     = raw.get("body", raw)
    url      = raw.get("url", "")
    platform = _normalize_platform(args.platform or detect_platform(url))

    sessions = extract_sessions(platform, data)
    if not sessions:
        logger.error("Aucune session trouvee.")
        sys.exit(1)

    fpath = write_sessions(platform, sessions)
    logger.success(f"{len(sessions)} session(s) -> {fpath}")


# ── probe (Hypocampus sans HAR) ───────────────────────────────────────────────

def cmd_probe(args: argparse.Namespace) -> None:
    platform = _normalize_platform(args.platform)
    cookies  = load_cookies(args.cookies_file)
    fetcher  = PlatformFetcher(platform, cookies)
    hits     = fetcher.probe_endpoints(CANDIDATES[platform], _DUMP_DIR / "probe" / platform.lower())
    if not hits:
        logger.warning("Aucun endpoint repondu. Verifie tes cookies.")
    else:
        logger.success(f"{len(hits)} endpoint(s) trouves.")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _normalize_platform(p: str) -> str:
    m = {"hypocampus": "Hypocampus", "ednpro": "EDNpro",
         "edn-pro": "EDNpro", "edn pro": "EDNpro"}
    return m.get(p.lower(), p)


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Capture QCM Hypocampus / EDN Pro -> Synapse",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # init-ednpro
    p = sub.add_parser("init-ednpro",
                        help="Configuration initiale via localStorage (une seule fois, plus jamais de F12)")
    p.set_defaults(func=cmd_init_ednpro)

    # setup-ednpro (fallback)
    p = sub.add_parser("setup-ednpro", help="Sauvegarde manuellement un Bearer token")
    p.add_argument("bearer_token", nargs="?", help="JWT Bearer (optionnel - mode interactif sinon)")
    p.add_argument("--user-id", dest="user_id", default=None)
    p.set_defaults(func=cmd_setup_ednpro)

    # discover-tables
    p = sub.add_parser("discover-tables", help="Liste les tables Supabase EDN Pro et sonde les QCMs")
    p.set_defaults(func=cmd_discover_tables)

    # fetch-ednpro
    p = sub.add_parser("fetch-ednpro", help="Recupere l'historique QCM depuis une table Supabase")
    p.add_argument("table", help="Nom de la table (ex: objective_sessions)")
    p.add_argument("--limit", type=int, default=500, help="Nombre max de sessions (defaut: 500)")
    p.set_defaults(func=cmd_fetch_ednpro)

    # init-hypocampus (recommandé)
    p = sub.add_parser("init-hypocampus",
                        help="Configuration initiale Hypocampus via JS snippet (une seule fois)")
    p.set_defaults(func=cmd_init_hypocampus)

    # setup-hypocampus (fallback)
    p = sub.add_parser("setup-hypocampus", help="Sauvegarde manuellement un Bearer token Hypocampus")
    p.add_argument("bearer_token", nargs="?", help="JWT Bearer (optionnel - mode interactif sinon)")
    p.set_defaults(func=cmd_setup_hypocampus)

    # discover-hypocampus
    p = sub.add_parser("discover-hypocampus", help="Sonde les endpoints Hypocampus avec le JWT")
    p.set_defaults(func=cmd_discover_hypocampus)

    # fetch-hypocampus
    p = sub.add_parser("fetch-hypocampus", help="Recupere l'historique QCM Hypocampus")
    p.set_defaults(func=cmd_fetch_hypocampus)

    # discover (HAR)
    p = sub.add_parser("discover", help="Analyse un fichier HAR")
    p.add_argument("har_file")
    p.add_argument("--min-score", type=int, default=10, dest="min_score")
    p.set_defaults(func=cmd_discover)

    # fetch (legacy cookie-based)
    p = sub.add_parser("fetch", help="Fetch avec cookies (legacy)")
    p.add_argument("platform", choices=["Hypocampus"])
    p.add_argument("cookies_file")
    p.set_defaults(func=cmd_fetch)

    # probe (legacy)
    p = sub.add_parser("probe", help="Sonde des endpoints candidats avec cookies (legacy)")
    p.add_argument("platform", choices=["Hypocampus"])
    p.add_argument("cookies_file")
    p.set_defaults(func=cmd_probe)

    # convert
    p = sub.add_parser("convert", help="Convertit un dump JSON en fichier Synapse")
    p.add_argument("json_file")
    p.add_argument("platform", nargs="?")
    p.set_defaults(func=cmd_convert)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
