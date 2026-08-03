import asyncio
from datetime import datetime
from loguru import logger
from backend.state.store import data_store
from backend.core.notion.service import notion_service
from backend.config.settings import now_local

# Cache pour les cours déjà correctement liés (liaison réussie uniquement)
# Encapsulé dans une classe pour faciliter le reset entre tests
class _AutoLinkCache:
    def __init__(self):
        self._processed: set[str] = set()

    def add(self, course_id: str) -> None:
        self._processed.add(course_id)

    def __contains__(self, course_id: str) -> bool:
        return course_id in self._processed

    def clear(self) -> None:
        self._processed.clear()

    def __len__(self) -> int:
        return len(self._processed)


_PROCESSED_COURSES = _AutoLinkCache()

# Syncs one-shot au démarrage
_VAULT_SYNC_DONE = False
_LACUNES_SYNC_DONE = False

# Compteur de cycles pour les rafraîchissements moins fréquents
_CYCLE = 0

# Rafraîchissement complet des cours toutes les N cycles (N × 5 min)
_FULL_REFRESH_EVERY = 12  # 60 minutes

async def _delta_refresh_cours() -> None:
    """Rafraîchit uniquement les cours modifiés depuis le dernier sync complet."""
    since = data_store.cours_last_synced
    if not since:
        return
    try:
        updated = await notion_service.get_updated_cours(since.isoformat())
        if updated:
            count = await data_store.merge_cours_delta(updated)
            data_store.cours_last_synced = now_local()
            data_store.save_to_disk()
            logger.success(f"[Delta cours] {count} cours mis à jour.")
        else:
            data_store.cours_last_synced = now_local()
            logger.debug("Delta cours : aucun changement détecté.")
    except Exception as exc:
        logger.error(f"Delta refresh cours échoué : {exc}")


async def run_background_tasks():
    """Boucle de synchronisation en arrière-plan.

    Stratégie pour serveur permanent (always-on) :
      - Toutes les 5 min  : sync différentielle des items (uniquement les mis à jour)
                            + auto-link cours ↔ items
      - Toutes les 60 min : refresh complet des cours Notion
      - Au démarrage      : vault Obsidian + lacunes (une seule fois)
    """
    global _CYCLE
    logger.info("Démarrage de la boucle de synchronisation en arrière-plan…")

    while True:
        _CYCLE += 1
        try:
            # ── 1. Refresh cours Notion (complet 60 min, delta toutes les 5 min) ──
            if _CYCLE == 1 or _CYCLE % _FULL_REFRESH_EVERY == 0:
                logger.info(f"[Cycle {_CYCLE}] Refresh complet des cours Notion…")
                await data_store.refresh()
            else:
                await _delta_refresh_cours()

            # ── 2. Sync différentielle des items ──────────────────────────────────
            since = data_store.items_last_synced
            if not data_store.items_map:
                logger.info("Cache items vide — chargement initial complet…")
                try:
                    new_map = await notion_service.get_all_items_map()
                    data_store.items_map = new_map
                    data_store.items_last_synced = now_local()
                    data_store.save_to_disk()
                    logger.success(f"{len(new_map)} items chargés.")
                except Exception as e:
                    logger.error(f"Échec chargement items : {e}")
            else:
                try:
                    if since:
                        updated = await notion_service.get_updated_items_map(since.isoformat())
                        if updated:
                            logger.success(f"{len(updated)} item(s) mis à jour détectés.")
                            data_store.items_map = {**data_store.items_map, **updated}
                            data_store.save_to_disk()
                        else:
                            logger.debug("Aucun item modifié depuis le dernier cycle.")
                    else:
                        new_map = await notion_service.get_all_items_map()
                        data_store.items_map = new_map
                        data_store.save_to_disk()
                    data_store.items_last_synced = now_local()
                except Exception as e:
                    logger.error(f"Échec sync différentielle items : {e}")

            # ── 3. Auto-link cours ↔ items ────────────────────────────────────────
            if data_store.items_map:
                await auto_link_process(data_store.items_map)

            # ── 4. Vault Obsidian — une seule fois au démarrage ───────────────────
            global _VAULT_SYNC_DONE, _LACUNES_SYNC_DONE
            if not _VAULT_SYNC_DONE:
                await _sync_vault_strict_once()
                await _push_missing_obsidian_uris()
                _VAULT_SYNC_DONE = True

            # ── 5. Lacunes Obsidian — une seule fois au démarrage ─────────────────
            if not _LACUNES_SYNC_DONE:
                await _sync_lacunes_once()
                _LACUNES_SYNC_DONE = True

            # ── 6. Watcher AI QCM — DÉSACTIVÉ (import manuel via bouton) ──────────
            # Le watcher auto-importait dès qu'un .md arrivait, causant des
            # doublons. L'import se fait maintenant uniquement via le bouton
            # "Importer QCM" dans la page QCM.

            # ── 7. Capture EDN Pro — DÉSACTIVÉ (fetch manuel via bouton) ─────────
            # L'auto-fetch toutes les heures créait des sessions fantômes.
            # Appeler ednpro_sync.sync() depuis le bouton "Importer QCM".

            # ── 8. Retry des corrections UNESS en échec (borné, silencieux) ───────
            await _retry_pending_uness_corrections()

            logger.success(f"[Cycle {_CYCLE}] Sync terminée. Prochain cycle dans 5 min.")

        except Exception as e:
            logger.error(f"Erreur dans la boucle de fond : {e}")

        await asyncio.sleep(300)

async def _sync_vault_strict_once():
    """
    Scan du vault Obsidian au premier démarrage.
    Applique les matchs stricts (item number) ET fuzzy (titre normalisé).
    Les titres de cours médicaux sont assez spécifiques pour que le fuzzy soit fiable.
    """
    try:
        from backend.config.settings import settings as _app_settings
        from backend.core.obsidian.sync import vault_sync_service

        vault_path = _app_settings.obsidian_vault_path
        if not vault_path:
            logger.debug("Vault sync ignoré : chemin non configuré.")
            return

        courses = list(data_store.cours)
        if not courses:
            logger.debug("Vault sync ignoré : aucun cours chargé.")
            return

        logger.info(f"Vault sync démarrage — {len(courses)} cours, vault : {vault_path}")
        result = vault_sync_service.scan_unlinked_notes(vault_path, courses)

        if result.errors:
            for err in result.errors:
                logger.warning(f"Vault sync erreur : {err}")

        # Appliquer stricts + fuzzy (les titres médicaux sont assez spécifiques)
        all_matches = result.confirmed + result.uncertain
        updated_pairs: list = []
        if all_matches:
            updated_pairs = vault_sync_service.apply_matches_and_get_paths(all_matches)
            logger.success(
                f"Vault sync : {len(updated_pairs)} notes liées "
                f"({len(result.confirmed)} stricts + {len(result.uncertain)} fuzzy)"
            )
            if updated_pairs:
                await _push_obsidian_uris(updated_pairs)
        else:
            logger.info(f"Vault sync : 0 nouvelle note ({result.skipped} déjà liées)")

    except Exception as exc:
        logger.error(f"Vault sync erreur inattendue : {exc}")


async def _push_obsidian_uris(updated_pairs: list[tuple[str, "Path"]]) -> None:
    """
    Pour chaque (course_id, path) issu du vault sync :
      1. Construit l'URI obsidian://
      2. Met à jour la propriété Notion "Obsidian" du cours
      3. Met à jour l'objet Cours local (data_store.cours) → badge immédiat
    """
    try:
        from backend.core.obsidian.service import obsidian_service
        from backend.core.notion.payloads import rich_text
        from backend.config.settings import NOTION_PROPS as P

        course_map = {c.id: c for c in data_store.cours}

        for course_id, path in updated_pairs:
            try:
                uri = obsidian_service.build_obsidian_uri(path)

                # 1. Notion
                ok = await notion_service.update_course(
                    course_id, {P.OBSIDIAN: rich_text(uri)}
                )
                if ok:
                    logger.success(f"Notion[Obsidian] ← {path.name}")

                # 2. Store local (badge sans attendre le prochain refresh Notion)
                cours = course_map.get(course_id)
                if cours is not None:
                    cours.obsidian_uri = uri

            except Exception as exc:
                logger.warning(f"_push_obsidian_uris({course_id}): {exc}")
            finally:
                await asyncio.sleep(0.35)   # 0.35s = 2.86 req/s, sous le rate-limit Notion

        if updated_pairs:
            data_store.save_to_disk()

    except Exception as exc:
        logger.error(f"_push_obsidian_uris global error: {exc}")


async def _push_missing_obsidian_uris():
    """
    Scanne 01 - Cours EDN/*/Cours/*.md et, pour chaque note avec notion_id,
    construit l'URI correcte depuis le chemin réel du fichier.

    Met à jour Notion si :
      - le cours n'a pas encore d'URI, OU
      - l'URI stockée ne correspond pas au chemin réel (ancien chemin, renommage…)
    """
    try:
        from pathlib import Path as _Path
        from backend.config.settings import settings as _app_settings, NOTION_PROPS as P
        from backend.core.obsidian.templates import _split_frontmatter, _parse_fm_lines
        from backend.core.obsidian.service import obsidian_service
        from backend.core.notion.payloads import rich_text
        import urllib.parse

        vault_path_str = _app_settings.obsidian_vault_path
        vault_name     = _app_settings.obsidian_vault_name
        if not vault_path_str or not vault_name:
            logger.debug("Push URI ignoré : vault_path ou vault_name non configuré.")
            return

        vault     = _Path(vault_path_str)
        md_files  = list(vault.glob("01 - Cours EDN/*/Cours/*.md"))
        if not md_files:
            return

        course_map = {c.id: c for c in data_store.cours}
        logger.info(f"Vérification URIs Obsidian : {len(md_files)} notes, {len(course_map)} cours…")

        pushed = skipped = 0

        for md_path in md_files:
            try:
                text = md_path.read_text(encoding="utf-8")
            except OSError:
                continue

            fm_raw, _ = _split_frontmatter(text)
            if not fm_raw:
                continue

            fm        = {k: v for k, v in _parse_fm_lines(fm_raw)}
            notion_id = str(fm.get("notion_id", "") or "").strip()
            if not notion_id or notion_id not in course_map:
                continue

            # URI correcte basée sur le chemin réel du fichier
            correct_uri = obsidian_service.build_obsidian_uri(md_path)
            cours       = course_map[notion_id]
            stored_uri  = (cours.obsidian_uri or "").strip()

            if stored_uri == correct_uri:
                skipped += 1
                continue

            # URI absente ou incorrecte → mise à jour Notion
            ok = await notion_service.update_course(notion_id, {P.OBSIDIAN: rich_text(correct_uri)})
            if ok:
                cours.obsidian_uri = correct_uri
                pushed += 1
                logger.debug(f"URI corrigée : {md_path.name}")
            await asyncio.sleep(0.35)   # 0.35s = 2.86 req/s, sous le rate-limit Notion

        if pushed:
            logger.success(f"URIs Obsidian : {pushed} corrigées, {skipped} déjà correctes")
            data_store.save_to_disk()
        else:
            logger.info(f"URIs Obsidian : toutes correctes ({skipped} vérifiées)")

    except Exception as exc:
        logger.error(f"_push_missing_obsidian_uris erreur : {exc}")


async def _sync_lacunes_once():
    """
    Scan silencieux des lacunes Obsidian au premier démarrage.
    Importe toutes les notes avec type: lacune dans SQLite.
    """
    try:
        from backend.config.settings import settings as _app_settings
        vault_path = _app_settings.obsidian_vault_path
        if not vault_path:
            logger.debug("Lacunes sync ignoré : vault non configuré.")
            return

        courses = list(data_store.cours)
        logger.info(f"Lacunes sync démarrage — vault : {vault_path}")

        from backend.core.obsidian.weak_points_sync import weak_points_sync_service
        result = await asyncio.to_thread(weak_points_sync_service.sync, courses)

        logger.success(f"Lacunes sync : {result.summary()}")
        if result.unmatched:
            logger.info(f"Lacunes non reliées à un cours : {len(result.unmatched)}")
        if result.errors:
            for err in result.errors:
                logger.warning(f"Lacunes sync erreur : {err}")

    except Exception as exc:
        logger.error(f"Lacunes sync erreur inattendue : {exc}")


async def _fetch_ednpro_background() -> None:
    """
    Récupère les sessions EDN Pro en arrière-plan et les dépose dans data/ai_qcm/.
    Ne génère un fichier que s'il y a de nouvelles sessions (dédup par session ID).
    Silencieux si les credentials n'existent pas (EDN Pro non configuré).
    """
    try:
        from backend.core.network_capture.fetcher import SupabaseFetcher, EDNPRO_CREDS_PATH
        from backend.core.network_capture.converters import extract_sessions_ednpro
        from backend.core.network_capture.writer import write_sessions

        if not EDNPRO_CREDS_PATH.exists():
            return  # Pas configuré → on ignore silencieusement

        import json as _json
        creds = _json.loads(EDNPRO_CREDS_PATH.read_text(encoding="utf-8"))
        if not creds.get("refresh_token") or not creds.get("bearer_token"):
            return  # Credentials incomplets

        # Fichier d'état : IDs des sessions déjà exportées
        _SYNC_STATE = EDNPRO_CREDS_PATH.parent / "ednpro_sync_state.json"

        def _do_fetch():
            # Charge les IDs déjà connus
            known_ids: set[str] = set()
            if _SYNC_STATE.exists():
                try:
                    state = _json.loads(_SYNC_STATE.read_text(encoding="utf-8"))
                    known_ids = set(state.get("session_ids", []))
                except Exception:
                    pass

            fetcher = SupabaseFetcher()
            rows    = fetcher.fetch_training_sessions(limit=500)
            if not rows:
                return None

            # Détecte les sessions nouvelles
            current_ids = {r["id"] for r in rows if r.get("id")}
            new_ids     = current_ids - known_ids
            if not new_ids:
                return None  # Rien de nouveau → pas de fichier

            # Filtre pour n'exporter que les nouvelles sessions
            new_rows = [r for r in rows if r.get("id") in new_ids]
            sessions = extract_sessions_ednpro(new_rows)
            if not sessions:
                return None

            fpath = write_sessions("EDNpro", sessions)

            # Met à jour l'état (union des anciens + nouveaux IDs) — écriture atomique
            all_ids = sorted(known_ids | current_ids)
            _tmp = _SYNC_STATE.with_suffix(".json.tmp")
            _tmp.write_text(
                _json.dumps({"session_ids": all_ids}, ensure_ascii=False),
                encoding="utf-8",
            )
            _tmp.replace(_SYNC_STATE)
            return fpath

        fpath = await asyncio.to_thread(_do_fetch)
        if fpath:
            logger.success(f"EDN Pro : {fpath.name} — nouvelles sessions importées")
        else:
            logger.debug("EDN Pro : aucune nouvelle session depuis le dernier import.")

    except Exception as exc:
        logger.warning(f"EDN Pro fetch arrière-plan : {exc}")


async def _retry_pending_uness_corrections() -> None:
    """Retente chaque correction UNESS en échec dont le délai de retry est
    passé (borné à 3 tentatives — cf. record_uness_correction_failure dans
    local_store.py). Une entrée qui a épuisé ses tentatives reste visible
    dans le bandeau /annales mais n'est plus reprise ici tant qu'un clic
    manuel "Relancer" ne lui redonne pas 3 tentatives fraîches.

    A successful retry only writes the corrected quiz JSON to
    UNESS/vérifiés/ — it does not import it (retry_failed_quiz has no
    matière to tag a brand-new annale with). Without the import pass below,
    a quiz corrected here just sits on disk forever with nothing telling
    anyone it's ready: this loop runs headless, so it can't pop the "choisir
    la matière" dialog itself, but it can safely import into an annale that
    was already tagged in an earlier session."""
    from backend.core.reviews import local_store
    from backend.core.uness import gemini_autocorrect, import_service

    due = local_store.list_pending_uness_correction_failures(due_only=True)
    if not due:
        return

    retried_ok = 0
    for failure in due:
        try:
            outcome = await asyncio.to_thread(gemini_autocorrect.retry_failed_quiz, failure["id"])
            if outcome.get("success"):
                retried_ok += 1
                logger.success(f"Retry correction UNESS #{failure['id']} ({failure['quiz_title']!r}) réussi")
            else:
                logger.info(
                    f"Retry correction UNESS #{failure['id']} ({failure['quiz_title']!r}) "
                    f"toujours en échec : {outcome.get('error')}"
                )
        except Exception as exc:
            logger.warning(f"Retry correction UNESS #{failure['id']} échoué : {exc}")

    if retried_ok:
        result = await asyncio.to_thread(import_service.import_verified_directory)
        if result["pending_tag"]:
            logger.info(
                f"Retry correction UNESS : {len(result['pending_tag'])} annale(s) corrigée(s) "
                "en attente de qualification de matière (ouvrir /annales pour les qualifier)."
            )


def reset_autolink_cache() -> None:
    """Vide le cache d'auto-link pour forcer un re-scan complet au prochain cycle."""
    _PROCESSED_COURSES.clear()
    logger.info("Cache auto-link réinitialisé — les cours seront re-scannés.")


async def trigger_autolink_now() -> int:
    """Déclenche immédiatement l'auto-link et retourne le nombre de nouvelles liaisons."""
    reset_autolink_cache()
    if not data_store.items_map:
        logger.warning("trigger_autolink_now : items_map vide, annulé.")
        return 0
    await auto_link_process(data_store.items_map)
    return len(_PROCESSED_COURSES)


async def auto_link_process(items_map: dict):
    """Link items to courses using the provided cache map."""
    count_linked = 0
    courses_to_check = list(data_store.cours)
    
    for cours in courses_to_check:
        # User Logic:
        # 1. Must have Item Number (si vide c'est pas collège)
        # 2. Must NOT be linked already (cours.item_lie)
        # 3. Must NOT be in processed cache (avoid rescan same files)
        
        if not cours.item_number or not cours.item_number.strip():
            continue
            
        if cours.item_lie:
             # Already linked, add to processed just in case
             _PROCESSED_COURSES.add(cours.id)
             continue
             
        if cours.id in _PROCESSED_COURSES:
            # Already checked this session, skip
            continue

        try:
            # items_map utilise des clés int (normalisées par DataStore.items_map setter)
            course_item_val = int(float(cours.item_number.replace(',', '.')))

            if course_item_val in items_map:
                target_item_id = items_map[course_item_val]
                logger.debug(f"Liaison Item {course_item_val} → '{cours.title}'")

                success = await notion_service.update_course(cours.id, {
                    "ITEM lié": {"relation": [{"id": target_item_id}]}
                })

                if success:
                    count_linked += 1
                    if hasattr(cours, 'item_lie'):
                        cours.item_lie = target_item_id
                    # Marquer seulement les liaisons réussies — les non-matchs
                    # seront retestés au prochain cycle (l'item peut être ajouté ensuite)
                    _PROCESSED_COURSES.add(cours.id)
                    await asyncio.sleep(0.1)
            # Pas de correspondance : ne pas marquer processed → sera retesté au prochain cycle

        except ValueError:
            # Format item_number invalide (non-numérique) : inutile de retenter
            _PROCESSED_COURSES.add(cours.id)
        except Exception as e:
            logger.error(f"Error linking '{cours.title}': {e}")
            # Don't add to processed if error, retry next time

    if count_linked > 0:
        logger.success(f"Auto-linked {count_linked} items.")
        data_store.save_to_disk()
    else:
        logger.info("No new links created this cycle.")
