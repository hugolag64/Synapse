from nicegui import ui, app
from starlette.requests import Request
from dotenv import load_dotenv
from loguru import logger
import sys
import asyncio
import os

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
from frontend.pages.todo import todo_page
from frontend.pages.dashboard import dashboard_page
from frontend.pages.settings import settings_page
from frontend.pages.health import health_page
from frontend.pages.stats import stats_page
from frontend.pages.weak_points import weak_points_page
from frontend.pages.qcm import qcm_page
from frontend.pages.planning import planning_page
from frontend.pages.externat import externat_page
from frontend.theme import frame
from backend.state.store import data_store

# Load environment variables
load_dotenv()
from fastapi.responses import FileResponse

def _resolve_pdf_path(raw: str) -> str | None:
    """Normalise un chemin PDF et vérifie qu'il est sûr (extension + répertoire autorisé)."""
    path = raw
    if path.startswith('file:///'):
        path = path[8:]
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
        # --- SPLASH SCREEN (White Background, Large Logo) ---
        with ui.column().classes('w-full h-screen items-center justify-center bg-white text-slate-900') as splash_container:
            ui.image('/static/LogoSynapse.png').style('width: 280px; max-width: 80vw; object-fit: contain;').classes('mb-8')

            progress = ui.linear_progress(value=0.0).classes('w-64 h-1.5 rounded-full').style('color: #4338CA')
            status_label = ui.label('Initialisation…').classes('text-slate-400 text-sm mt-2 font-medium')

            async def check_loading():
                progress.set_value(data_store.loading_progress)
                status_label.set_text(data_store.loading_message)
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


@ui.page('/semestres')
async def semestres():
    semestres_page()

@ui.page('/todo')
async def todo():
    await todo_page()

@ui.page('/planning')
async def planning():
    with frame('Planning'):
        await planning_page()

# externat_page is already decorated with @ui.page — imported above

app.on_startup(startup_handler)

_PROD = os.getenv("SYNAPSE_ENV", "dev") == "prod"

if __name__ in {"__main__", "__mp_main__"}:
    ui.run(
        title='Synapse',
        favicon='🧠',
        dark=False,
        reload=not _PROD,
        show=not _PROD,
        host='127.0.0.1',
        port=8082
    )

