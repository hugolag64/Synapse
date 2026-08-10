"""Agent local de capture QCM EDNpro, piloté par un navigateur visible.

L'agent est lancé sur le PC de l'utilisateur, pas dans le conteneur Synapse.
Il n'automatise aucune réponse : il observe le DOM après correction, puis
importe les observations au moment de l'appel HTTP /stop.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import threading
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:  # Allow direct execution from the repository root.
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.core.ednpro.qcm_capture import EdnproQuestionObservation, extract_corrected_observation
from scripts.ednpro.collector import _open_ednpro_browser


def default_config_path() -> Path:
    if os.name == "nt":
        appdata = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
        return appdata / "Synapse" / "ednpro-capture-agent.json"
    return Path("data/ednpro/ednpro-capture-agent.json")


def load_agent_config(
    config_path: str | Path | None = None,
    *,
    cli_overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    path = Path(config_path) if config_path else default_config_path()
    values: dict[str, Any] = {}
    if path.exists():
        loaded = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(loaded, dict):
            raise ValueError(f"Configuration invalide : {path}")
        values.update(loaded)
    for key, value in (cli_overrides or {}).items():
        if value not in (None, ""):
            values[key] = value
    values.setdefault("profile_dir", "data/ednpro/qcm-browser-profile")
    values.setdefault("listen_host", "127.0.0.1")
    values.setdefault("listen_port", 8876)
    values.setdefault("poll_seconds", 0.75)
    return values


class CaptureBuffer:
    """État thread-safe partagé entre l'API localhost et la boucle Playwright."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self.active = False
        self.session_id = ""
        self.session_date = ""
        self.stop_requested = False
        self.last_result: dict[str, Any] | None = None
        self.observations: dict[str, EdnproQuestionObservation] = {}
        self.state = "ready"

    def start(self, session_id: str = "") -> None:
        with self._lock:
            self.active = True
            self.session_id = session_id.strip() or f"local-{datetime.now().strftime('%Y%m%dT%H%M%S')}"
            self.session_date = datetime.now().astimezone().isoformat(timespec="seconds")
            self.stop_requested = False
            self.last_result = None
            self.observations = {}
            self.state = "starting"

    def mark_browser_ready(self) -> None:
        with self._lock:
            if self.active:
                self.state = "capturing"

    def mark_error(self, message: str) -> None:
        with self._lock:
            self.active = False
            self.stop_requested = False
            self.state = "error"
            self.last_result = {"ok": False, "error": message}

    def finish_result(self, result: dict[str, Any]) -> None:
        with self._lock:
            self.last_result = result
            self.state = "imported" if result.get("ok", False) else "error"

    def add(self, observation: EdnproQuestionObservation) -> None:
        if not observation.external_question_id:
            return
        with self._lock:
            if self.active:
                self.observations[observation.external_question_id] = observation

    def request_stop(self) -> None:
        with self._lock:
            if self.active:
                self.stop_requested = True
                self.state = "stopping"

    def consume_stop(self) -> dict[str, Any] | None:
        with self._lock:
            if not self.stop_requested:
                return None
            self.stop_requested = False
            self.active = False
            return {
                "external_session_id": self.session_id,
                "session_date": self.session_date,
                "questions": [asdict(value) for value in self.observations.values()],
            }

    def status(self) -> dict[str, Any]:
        with self._lock:
            return {
                "active": self.active,
                "state": self.state,
                "external_session_id": self.session_id,
                "captured_questions": len(self.observations),
                "last_result": self.last_result,
            }


def _json_response(handler: BaseHTTPRequestHandler, status: int, payload: dict[str, Any]) -> None:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
    handler.send_header("Access-Control-Allow-Headers", "Content-Type")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def _make_handler(buffer: CaptureBuffer):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: Any) -> None:
            return

        def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
            parsed = urllib.parse.urlparse(self.path)
            query = urllib.parse.parse_qs(parsed.query)
            if parsed.path == "/health":
                _json_response(self, 200, {"ok": True})
            elif parsed.path == "/status":
                _json_response(self, 200, buffer.status())
            elif parsed.path == "/start":
                buffer.start((query.get("session_id") or [""])[0])
                _json_response(self, 200, {"ok": True, **buffer.status()})
            elif parsed.path == "/stop":
                buffer.request_stop()
                _json_response(self, 202, {"ok": True, "message": "Arrêt demandé", **buffer.status()})
            else:
                _json_response(self, 404, {"ok": False, "error": "route inconnue"})

        def do_OPTIONS(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
            self.send_response(204)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.end_headers()

    return Handler


def _serve_control(buffer: CaptureBuffer, host: str, port: int) -> ThreadingHTTPServer:
    server = ThreadingHTTPServer((host, port), _make_handler(buffer))
    thread = threading.Thread(target=server.serve_forever, name="ednpro-capture-control", daemon=True)
    thread.start()
    return server


def _post_session(server_url: str, token: str, session: dict[str, Any]) -> dict[str, Any]:
    url = server_url.rstrip("/") + "/api/ednpro/qcm/import"
    request = urllib.request.Request(
        url,
        data=json.dumps(session, ensure_ascii=False).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            **({"Authorization": f"Bearer {token}"} if token else {}),
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, json.JSONDecodeError) as exc:
        return {"ok": False, "error": str(exc)}


async def _capture_pages(buffer: CaptureBuffer, context: Any) -> None:
    pages = [page for page in getattr(context, "pages", ()) if not page.is_closed()]
    for page in pages:
        if "ednpro.app" not in str(page.url):
            continue
        observation = extract_corrected_observation(
            await page.content(), source_url=page.url
        )
        if observation:
            buffer.add(observation)


async def run_agent(args: argparse.Namespace) -> None:
    try:
        from playwright.async_api import async_playwright
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("Playwright est requis pour l'agent local") from exc

    config = load_agent_config(
        args.config,
        cli_overrides={
            "synapse_url": args.synapse_url,
            "token": args.token,
            "cdp_url": args.cdp_url,
            "profile_dir": args.profile_dir,
            "listen_host": args.listen_host,
            "listen_port": args.listen_port,
            "poll_seconds": args.poll_seconds,
        },
    )
    synapse_url = str(config.get("synapse_url") or "").strip()
    token = str(config.get("token") or "").strip()
    if not synapse_url or not token:
        raise RuntimeError("Configuration incomplète : synapse_url et token sont requis")

    buffer = CaptureBuffer()
    server = _serve_control(buffer, str(config["listen_host"]), int(config["listen_port"]))
    print(f"Agent EDNpro prêt sur http://{config['listen_host']}:{config['listen_port']}", flush=True)
    if args.auto_start:
        buffer.start()

    try:
        async with async_playwright() as playwright:
            connection = None
            context = None
            owns_context = False
            if config.get("cdp_url"):
                connection, context, owns_context = await _open_ednpro_browser(
                    playwright, Path(config["profile_dir"]), str(config["cdp_url"])
                )
                buffer.mark_browser_ready()

            try:
                while True:
                    if buffer.status()["active"] and context is None:
                        try:
                            context = await playwright.chromium.launch_persistent_context(
                                str(config["profile_dir"]), headless=False
                            )
                            owns_context = True
                            page = context.pages[0] if context.pages else await context.new_page()
                            await page.goto(
                                "https://ednpro.app/training-v2",
                                wait_until="domcontentloaded",
                            )
                            buffer.mark_browser_ready()
                        except Exception as exc:
                            buffer.mark_error(f"Impossible d'ouvrir Chromium : {exc}")
                            await asyncio.sleep(max(0.25, float(config["poll_seconds"])))
                            continue

                    if buffer.status()["active"] and context is not None:
                        await _capture_pages(buffer, context)

                    session = buffer.consume_stop()
                    if session is not None:
                        if session["questions"]:
                            result = _post_session(synapse_url, token, session)
                        else:
                            result = {
                                "ok": True,
                                "imported_questions": 0,
                                "message": "Aucune correction à importer",
                            }
                        buffer.finish_result(result)
                        print(json.dumps(result, ensure_ascii=False), flush=True)

                    await asyncio.sleep(max(0.25, float(config["poll_seconds"])))
            finally:
                if owns_context and context is not None:
                    await context.close()
                elif connection is not None:
                    await connection.close()
    finally:
        server.shutdown()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default=None, help="Fichier JSON de configuration local")
    parser.add_argument("--synapse-url", default=None, help="URL publique ou locale de Synapse")
    parser.add_argument("--token", default=None, help="Jeton EDNPRO_CAPTURE_TOKEN configuré côté Synapse")
    parser.add_argument("--cdp-url", default=None, help="URL CDP d'un Chrome visible déjà lancé")
    parser.add_argument("--profile-dir", default=None)
    parser.add_argument("--listen-host", default=None)
    parser.add_argument("--listen-port", type=int, default=None)
    parser.add_argument("--poll-seconds", type=float, default=None)
    parser.add_argument("--auto-start", action="store_true")
    return parser


if __name__ == "__main__":
    asyncio.run(run_agent(build_parser().parse_args()))

