"""
ai_qcm/watcher.py — Synapse
-----------------------------
Surveillance automatique de data/ai_qcm/.
Dès qu'un fichier .md valide est déposé, l'import est déclenché sans action utilisateur.

Démarrage : start_watcher() appelé depuis background.py au premier cycle.
Arrêt     : stop_watcher() appelé à la fermeture de l'app (optionnel — le thread daemon s'arrête avec le process).
"""
from __future__ import annotations

import threading
from pathlib import Path
from loguru import logger

from backend.core.ai_qcm.service import import_file, _is_synapse_qcm, INBOX_DIR

# Résultats d'import en attente d'affichage UI (consommés par qcm_page au prochain chargement)
_PENDING_RESULTS: list[dict] = []
_PENDING_LOCK = threading.Lock()


def pop_pending_results() -> list[dict]:
    """Retourne et vide les résultats d'import watcher non encore affichés."""
    with _PENDING_LOCK:
        results, _PENDING_RESULTS[:] = list(_PENDING_RESULTS), []
    return results


# ── Handler watchdog ──────────────────────────────────────────────────────────

class _QCMInboxHandler:
    """Handler compatible watchdog FileSystemEventHandler."""

    def __init__(self, courses_getter):
        self._courses_getter = courses_getter  # lambda → list[Cours]
        self._timers: dict[str, threading.Timer] = {}
        self._lock = threading.Lock()

    def dispatch(self, event) -> None:
        src = getattr(event, "src_path", None)
        if src and not getattr(event, "is_directory", False):
            self._schedule(src)

    def _schedule(self, path: str) -> None:
        if not path.endswith(".md"):
            return
        p = Path(path)
        if p.parent.resolve() != INBOX_DIR.resolve():
            return
        with self._lock:
            existing = self._timers.pop(path, None)
            if existing:
                existing.cancel()
            t = threading.Timer(2.0, self._process, args=[path])
            self._timers[path] = t
            t.start()

    def _process(self, path: str) -> None:
        with self._lock:
            self._timers.pop(path, None)

        p = Path(path)
        if not p.exists():
            return
        if not _is_synapse_qcm(p):
            return

        sentinel = p.with_suffix(".importing")
        error_marker = p.with_suffix(".error")

        if sentinel.exists():
            logger.debug(f"Watcher : import déjà en cours pour {p.name}, skip.")
            return

        try:
            sentinel.touch()
            courses = self._courses_getter()
            result = import_file(p, courses=courses)

            if result["success"]:
                skipped = result.get("skipped", 0)
                skipped_info = f", {skipped} doublon(s)" if skipped else ""
                logger.success(
                    f"Watcher import : {p.name} — "
                    f"{result['imported']} session(s) importée(s){skipped_info}"
                )
                with _PENDING_LOCK:
                    _PENDING_RESULTS.append(result)
            elif result["errors"]:
                logger.warning(f"Watcher import échoué ({p.name}) : {result['errors'][0]}")
                error_marker.write_text("\n".join(result["errors"]))

        except Exception as exc:
            logger.error(f"Watcher erreur inattendue ({p.name}) : {exc}")
            try:
                error_marker.write_text(str(exc))
            except Exception:
                pass
        finally:
            if sentinel.exists():
                sentinel.unlink(missing_ok=True)


# ── Lifecycle ─────────────────────────────────────────────────────────────────

_observer = None
_WATCHER_STARTED = False


def _cleanup_orphan_sentinels() -> None:
    """Supprime les .importing orphelins d'un crash précédent."""
    for s in INBOX_DIR.glob("*.importing"):
        s.unlink(missing_ok=True)
        logger.debug(f"Watcher : sentinel orphelin supprimé ({s.name})")


def start_watcher(courses_getter) -> None:
    """Démarre le watcher en arrière-plan. Idempotent."""
    global _observer, _WATCHER_STARTED
    if _WATCHER_STARTED:
        return

    try:
        from watchdog.observers import Observer
        from watchdog.events import FileSystemEventHandler

        INBOX_DIR.mkdir(parents=True, exist_ok=True)
        _cleanup_orphan_sentinels()

        handler = _QCMInboxHandler(courses_getter)

        # Adapter l'interface watchdog → notre handler
        class _WatchdogAdapter(FileSystemEventHandler):
            def dispatch(self, event):
                handler.dispatch(event)

        _observer = Observer()
        _observer.schedule(_WatchdogAdapter(), str(INBOX_DIR), recursive=False)
        _observer.start()
        _WATCHER_STARTED = True
        logger.info(f"AI QCM watcher démarré → {INBOX_DIR}")

    except ImportError:
        logger.warning(
            "watchdog non installé — watcher AI QCM désactivé. "
            "Installe-le : pip install watchdog"
        )
    except Exception as exc:
        logger.error(f"Watcher démarrage échoué : {exc}")


def stop_watcher() -> None:
    """Arrête le watcher proprement (appelé à la fermeture de l'app)."""
    global _observer, _WATCHER_STARTED
    if _observer:
        try:
            _observer.stop()
            _observer.join(timeout=3)
        except Exception:
            pass
        _observer = None
    _WATCHER_STARTED = False
