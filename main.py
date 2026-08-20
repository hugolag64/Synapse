from nicegui import ui, app
from starlette.requests import Request
from dotenv import load_dotenv
from loguru import logger
import sys
import asyncio
import os
import hmac
# ── Loguru : rotation quotidienne, 30 jours de rétention, compression ─────────
logger.remove()
logger.add(sys.stderr, level="INFO", colorize=True,
           format="<green>{time:HH:mm:ss}</green> | <level>{level:<8}</level> | {message}")
logger.add(
    "logs/synapse_{time:YYYY-MM-DD}.log",
    rotation="00:00",       # nouveau fichier chaque jour à minuit
    retention="30 days",    # supprimer les logs de plus de 30 jours
    compression="zip",      # compresser les anciens logs
    encoding="utf-8",
    level="DEBUG",
    format="{time:YYYY-MM-DD HH:mm:ss} | {level:<8} | {name}:{line} | {message}",
)


from frontend.pages.semestres import semestres_page
from frontend.pages.colleges import colleges_page
from frontend.pages.items import items_page
from frontend.pages.revue import revue_page
from frontend.pages.todo import todo_page
from frontend.pages.dashboard import dashboard_page
from frontend.pages.settings import settings_page
from frontend.pages.health import health_page
from frontend.pages.stats import stats_page
from frontend.pages.weak_points import weak_points_page
from frontend.pages.qcm import qcm_page
from frontend.pages.annales import annales_page
from frontend.pages.annale_detail import annale_detail_page
from frontend.pages.planning import planning_page
from frontend.pages.externat import externat_page
from frontend.pages.prepa import prepa_page
from frontend.pages.triage import triage_page
from frontend.pages.course_detail import course_detail_page
from frontend.theme import frame
from backend.state.store import data_store
from backend.api.qcm import router as qcm_api_router
from backend.config.runtime import get_runtime_config

app.include_router(qcm_api_router)


@app.post('/api/ednpro/qcm/import')
async def import_ednpro_qcm_capture(request: Request):
    """Importe les corrections remontées par l'agent Chromium local."""
    expected_token = os.getenv("EDNPRO_CAPTURE_TOKEN", "").strip()
    authorization = request.headers.get("authorization", "")
    provided_token = authorization.removeprefix("Bearer ").strip()
    if not expected_token or not hmac.compare_digest(provided_token, expected_token):
        return JSONResponse({"ok": False, "error": "capture EDNpro non authentifiée"}, status_code=401)

    from backend.core.ednpro.qcm_capture import (
        enrich_session_ranks,
        import_session,
        record_imported_evaluations,
    )

    try:
        payload = await request.json()
        payload = await asyncio.to_thread(
            enrich_session_ranks,
            payload,
            courses=getattr(data_store, "cours", []) or [],
        )
        result = import_session(payload)
        item_courses = {
            str(getattr(course, "item_number", "") or "").strip(): course
            for course in getattr(data_store, "cours", []) or []
            if str(getattr(course, "item_number", "") or "").strip()
        }
        evaluation_ids = record_imported_evaluations(
            session=payload,
            result=result,
            course_resolver=lambda item: item_courses.get(str(item).strip()),
        )
    except (TypeError, ValueError, KeyError) as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)
    return JSONResponse({
        "ok": True,
        "session_id": result.session_id,
        "imported_questions": result.imported_questions,
        "discarded_questions": result.discarded_questions,
        "new_questions": result.new_questions,
        "new_attempts": result.new_attempts,
        "duplicate_attempts": result.duplicate_attempts,
        "item_stats": result.item_stats,
        "session_item_stats": result.session_item_stats,
        "evaluation_ids": evaluation_ids,
    })


@app.get('/api/healthz')
async def healthz():
    """Liveness probe that does not wait for Notion or the preload task."""
    return {"status": "ok"}

# Load environment variables
load_dotenv()
from fastapi.responses import FileResponse, JSONResponse
from pathlib import Path
from starlette.staticfiles import StaticFiles

_QCM_NODE_DIST = Path(__file__).parent / "qcm_app" / "dist"
if (_QCM_NODE_DIST / "index.html").exists():
    app.mount("/qcm-app", StaticFiles(directory=_QCM_NODE_DIST, html=True), name="qcm_app")

def _resolve_pdf_path(raw: str) -> str | None:
    """Normalise un chemin PDF et vérifie qu'il est sûr (extension + répertoire autorisé)."""
    path = raw
    if path.startswith('file:///'):
        # `file:///data/...` is a Unix absolute path, while the legacy Windows
        # form `file:///C:/...` must keep its drive prefix on Windows.
        path = path[7:]
        if os.name == "nt" and len(path) >= 4 and path[0] == "/" and path[2:4] == ":/":
            path = path[1:]
        elif not path.startswith(("/", "\\")):
            path = os.sep + path
    path = path.replace('/', os.sep)

    if not path.lower().endswith('.pdf'):
        return None

    real = os.path.realpath(path)

    # Refuser si aucun répertoire autorisé n'est configuré (évite de servir tout le disque)
    from backend.config.settings import settings as _cfg
    allowed_roots = [r for r in (_cfg.medicine_dir, _cfg.fac_dir) if r]
    if not allowed_roots:
        return None
    if not any(real.startswith(os.path.realpath(root)) for root in allowed_roots):
        return None

    return real if os.path.isfile(real) else None


@app.post('/api/lacune/move')
async def lacune_move(request: Request):
    """Drag & drop kanban — met à jour le statut d'une lacune."""
    from backend.core.reviews import local_store as _ls
    data = await request.json()
    wp_id  = int(data['id'])
    status = data['status']
    _ls.update_weak_point_status(wp_id, status)
    return JSONResponse({'ok': True})


@app.get('/pdf/{course_id}')
async def serve_pdf(course_id: str):
    """Sert un PDF local pour un cours.
    Priorité : url_pdf (Collège) → url_pdf_ue (Fac/UE).
    Valide l'extension (.pdf) et le répertoire autorisé avant de servir.
    """
    target_course = next((c for c in data_store.cours if c.id == course_id), None)

    if target_course:
        for attr in ('url_pdf', 'url_pdf_ue'):
            raw = getattr(target_course, attr, None)
            if not raw:
                continue
            safe_path = _resolve_pdf_path(raw)
            if safe_path:
                return FileResponse(safe_path, media_type='application/pdf')

    return {"error": "Fichier PDF introuvable sur le disque local ou chemin non configuré."}

@ui.page('/')
async def main_page():
    # 1. Check if DataStore is ready
    if not data_store.is_preloaded:
        ui.add_head_html("""
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@300;600&display=swap" rel="stylesheet">
<style>
body { overflow: hidden; }
.sn-splash {
  position: fixed; inset: 0;
  background: #0A0B0F;
  display: flex; flex-direction: column;
  align-items: center; justify-content: center;
}
.sn-rings {
  position: relative;
  width: 220px; height: 220px;
  display: flex; align-items: center; justify-content: center;
  margin-bottom: 28px;
}
.sn-ring {
  position: absolute; border-radius: 50%;
  border: 1px solid rgba(99, 102, 241, 0.55);
  opacity: 0;
  animation: sn-pulse 2.8s ease-out infinite;
}
.sn-ring:nth-child(1) { width: 90px; height: 90px; animation-delay: 0s; }
.sn-ring:nth-child(2) { width: 140px; height: 140px; animation-delay: 0.7s; }
.sn-ring:nth-child(3) { width: 190px; height: 190px; animation-delay: 1.4s; }
@keyframes sn-pulse {
  0%   { opacity: 0.7; transform: scale(0.65); }
  100% { opacity: 0;   transform: scale(1); }
}
.sn-logo-img {
  position: relative; z-index: 2;
  width: 68px; height: 68px; object-fit: contain;
  filter: drop-shadow(0 0 20px rgba(99, 102, 241, 0.55));
}
.sn-wordmark {
  font-family: 'Space Grotesk', sans-serif;
  font-size: 21px; font-weight: 600;
  letter-spacing: 0.24em; color: #F8FAFC;
  text-transform: uppercase; margin: 0;
}
.sn-hairline {
  width: 28px; height: 1px; background: #4F46E5;
  margin: 14px 0; opacity: 0.65;
}
.sn-status {
  font-family: 'Space Grotesk', sans-serif;
  font-size: 12px; font-weight: 300;
  color: #818CF8; letter-spacing: 0.06em;
  margin-bottom: 20px; min-height: 18px;
}
.sn-track {
  width: 176px; height: 2px;
  background: #1E1B4B; border-radius: 1px; overflow: hidden;
}
.sn-fill {
  height: 100%; border-radius: 1px;
  background: linear-gradient(90deg, #4F46E5, #818CF8);
  box-shadow: 0 0 10px rgba(99, 102, 241, 0.7);
  transition: width 0.4s ease;
  width: 0%;
}
@media (prefers-reduced-motion: reduce) {
  .sn-ring { animation: none; opacity: 0.15; }
  .sn-fill { transition: none; }
}
</style>
""")
        with ui.element('div').classes('sn-splash'):
            with ui.element('div').classes('sn-rings'):
                ui.element('div').classes('sn-ring')
                ui.element('div').classes('sn-ring')
                ui.element('div').classes('sn-ring')
                ui.html('<img src="/static/LogoSynapse.png" class="sn-logo-img" alt="Synapse" />', sanitize=False)
            ui.html('<p class="sn-wordmark">SYNAPSE</p><div class="sn-hairline"></div>', sanitize=False)
            status_el = ui.html('<span class="sn-status">Initialisation…</span>', sanitize=False)
            progress_el = ui.html('<div class="sn-track"><div class="sn-fill" style="width:0%"></div></div>', sanitize=False)

        async def check_loading():
            pct = int(data_store.loading_progress * 100)
            status_el.set_content(f'<span class="sn-status">{data_store.loading_message}</span>')
            progress_el.set_content(f'<div class="sn-track"><div class="sn-fill" style="width:{pct}%"></div></div>')
            if data_store.is_preloaded:
                splash_timer.deactivate()
                ui.navigate.to('/')

        if not data_store.is_preloaded and not data_store._preloading:
            asyncio.create_task(data_store.preload_all_views())

        # 0.5 s = 2 Hz : assez réactif pour le feedback, sans saturer le WebSocket
        splash_timer = ui.timer(0.5, check_loading)
            
    else:
        # --- DIRECT ACCESS ---
        with frame('Dashboard'):
            await dashboard_page()

# PWA — injecter le manifest dans toutes les pages
ui.add_head_html('<link rel="manifest" href="/static/manifest.json">', shared=True)
ui.add_head_html('<meta name="theme-color" content="#6366f1">', shared=True)
ui.add_head_html('<meta name="apple-mobile-web-app-capable" content="yes">', shared=True)
ui.add_head_html('<meta name="apple-mobile-web-app-status-bar-style" content="default">', shared=True)

# Startup Event
async def startup_handler():
    # Serve static files
    app.add_static_files('/static', 'static')

    # Init externat DB (stages table — idempotent)
    from backend.core.externat import store as externat_store
    externat_store.init_db()

    # Background Sync (Periodic)
    from backend.core.background import run_background_tasks
    asyncio.create_task(run_background_tasks())

    # Daily Routine
    from backend.features.daily_routine import run_daily_routine
    asyncio.create_task(run_daily_routine())
    
    # (Knowledge Service auto-load removed)


@ui.page('/stats')
def stats():
    stats_page()


@ui.page('/lacunes')
def lacunes(request: Request):
    item_filter = request.query_params.get('item', None) or None
    weak_points_page(item_filter=item_filter)


@ui.page('/qcm')
def qcm():
    qcm_page()


@ui.page('/exam')
def exam():
    from frontend.pages.exam_simulator_page import render_exam_simulator_page
    with frame('Examens Blancs'):
        render_exam_simulator_page()


@ui.page('/todo')
async def todo():
    await todo_page()

@ui.page('/planning')
async def planning(request: Request):
    with frame('Planning'):
        await planning_page(focus=request.query_params.get("focus"))

# Détail d'un item. La route n'avait jamais été déclarée alors que la command
# palette, dashboard_card et search_bar y naviguent déjà.
@ui.page('/cours/{course_id}')
def cours(course_id: str, request: Request):
    course_detail_page(course_id, college=request.query_params.get("college"))


@ui.page('/colleges')
def colleges(request: Request):
    with frame('Collèges'):
        colleges_page(open_college=request.query_params.get("open"))


@ui.page('/semestres')
def semestres():
    with frame('Semestres'):
        semestres_page()


@ui.page('/settings')
def settings():
    with frame('Paramètres'):
        settings_page()


@ui.page('/externat')
def externat():
    with frame('Mode Externat'):
        externat_page()



# externat_page is already decorated with @ui.page — imported above

app.on_startup(startup_handler)

if __name__ in {"__main__", "__mp_main__"}:
    try:
        runtime = get_runtime_config()
        ui.run(
            title='Synapse',
            favicon='🧠',
            dark=False,
            reload=not runtime.prod,
            show=not runtime.prod,
            host=runtime.host,
            port=runtime.port,
        )
    except (KeyboardInterrupt, SystemExit, asyncio.CancelledError):
        pass

