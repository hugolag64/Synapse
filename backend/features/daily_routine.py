from datetime import date, timedelta
import locale
import re
import subprocess
import sys
from loguru import logger

# Caractères PowerShell qui permettent l'injection de commandes
_PS_UNSAFE = re.compile(r'[`$;|&<>()\[\]{}\\]')
from backend.core.notion.service import notion_service
from backend.config.settings import business_today
from backend.core.reviews.local_store import (
    ensure_daily_flash_zero,
    complete_daily_flash_zero_ai_gen,
    is_daily_flash_zero_ai_gen_complete,
)
from backend.core.practice.flash_zero_service import FlashZeroService
from backend.state.store import data_store

# Set locale for French date formatting (if system supports it, otherwise fallback)
try:
    locale.setlocale(locale.LC_TIME, 'fr_FR.UTF-8')
except locale.Error:
    try:
        locale.setlocale(locale.LC_TIME, 'fra') # Windows
    except:
        pass


def _send_windows_notification(title: str, message: str) -> None:
    """Envoie une notification ballon Windows via PowerShell (sans dépendance externe)."""
    if sys.platform != "win32":
        return
    def _ps_safe(s: str, max_len: int) -> str:
        s = s.replace('"', '').replace("'", '').replace("\n", " ")
        return _PS_UNSAFE.sub('', s)[:max_len]

    safe_title   = _ps_safe(title, 64)
    safe_message = _ps_safe(message, 200)
    script = (
        "Add-Type -AssemblyName System.Windows.Forms; "
        "$n = New-Object System.Windows.Forms.NotifyIcon; "
        "$n.Icon = [System.Drawing.SystemIcons]::Information; "
        "$n.Visible = $true; "
        f'$n.ShowBalloonTip(7000, "{safe_title}", "{safe_message}", '
        "[System.Windows.Forms.ToolTipIcon]::None); "
        "Start-Sleep -Seconds 8; $n.Dispose()"
    )
    try:
        kwargs: dict = {"stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
        if hasattr(subprocess, "CREATE_NO_WINDOW"):
            kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
        subprocess.Popen(
            ["powershell", "-WindowStyle", "Hidden", "-Command", script],
            **kwargs,
        )
    except Exception as exc:
        logger.debug(f"Notification PowerShell échouée (non bloquant): {exc}")


async def _send_morning_notification() -> None:
    """Calcule le résumé du jour et envoie une notification Windows."""
    try:
        from backend.state.store import data_store
        today_iso = date.today().isoformat()
        if data_store.preferences.get("_notif_date") == today_iso:
            return  # déjà envoyée aujourd'hui

        from backend.core.reviews.service import review_service
        from backend.core.reviews import local_store
        from backend.core.reviews.recommendation_service import compute_daily_load

        history     = local_store.get_all_history()
        all_tasks   = review_service.generate_reviews("college", history)
        urgent      = review_service.get_urgent_tasks(all_tasks)
        today_tasks = review_service.get_today_tasks(all_tasks)
        load        = compute_daily_load(urgent, today_tasks)

        n_u  = load["urgent_count"]
        n_t  = load["today_count"]
        h, m = load["estimated_h"], load["estimated_m"]
        time_str = f"{h}h{m:02d}" if h else f"{load['total_min']} min"

        parts = []
        if n_u:
            parts.append(f"{n_u} urgente{'s' if n_u > 1 else ''}")
        if n_t:
            parts.append(f"{n_t} prévue{'s' if n_t > 1 else ''}")
        parts.append(f"~{time_str} estimé")
        msg = " · ".join(parts) if parts else "Bonne journée !"

        if urgent:
            _top = urgent[0]
            _name = _top.course_title
            if len(_name) > 38:
                _name = _name[:36] + "…"
            msg += f"\n↑ À prioriser : {_name}"

        _send_windows_notification("Synapse 🧠", msg)

        data_store.preferences["_notif_date"] = today_iso
        data_store.save_to_disk()

    except Exception as exc:
        logger.debug(f"Morning notification échouée (non bloquant): {exc}")


def ensure_morning_flash_zero() -> dict:
    timezone_name = data_store.preferences.get("timezone", "Europe/Paris")
    return ensure_daily_flash_zero(business_today(), timezone_name=timezone_name)


def ensure_daily_flash_zero_generation() -> None:
    """Génère jusqu'à 3 nouvelles questions Flash-Zero IA, au plus une fois par jour."""
    timezone_name = data_store.preferences.get("timezone", "Europe/Paris")
    today = business_today()
    if is_daily_flash_zero_ai_gen_complete(today, timezone_name=timezone_name):
        return
    complete_daily_flash_zero_ai_gen(today, timezone_name=timezone_name)
    try:
        FlashZeroService().generate_daily_questions(count=3)
    except Exception as exc:
        logger.debug(f"Génération Flash-Zero IA échouée (non bloquant): {exc}")


async def run_daily_routine():
    """
    Execute the daily routine:
    1. Archive past tasks (Status 'À faire'/'En cours' -> 'Terminé')
    2. Ensure tasks exist for Today, Tomorrow, Day+2
    """
    today = business_today()
    ensure_morning_flash_zero()
    ensure_daily_flash_zero_generation()
    if data_store.preferences.get("_routine_date") == today.isoformat():
        logger.debug("Daily Routine déjà exécutée aujourd'hui — skip.")
        await _send_morning_notification()
        return
    logger.debug("Running Daily Routine...")
    
    try:
        # 1. Fetch all tasks to analyze
        tasks = await notion_service.get_all_daily_tasks_for_check()
        
        # Track existing dates to avoid duplicates
        existing_dates = set()
        for task in tasks:
            if task.date:
                existing_dates.add(task.date)
                
        logger.debug(f"Found {len(tasks)} tasks. Existing dates: {[d.isoformat() for d in existing_dates]}")
        
        # --- Archiving Logic ---
        for task in tasks:
            if task.date and task.date < today and task.status in ["À faire", "En cours"]:
                logger.info(f"Archiving past task: {task.title} ({task.date})")
                await notion_service.update_task_status(task.id, "Terminé")

        # --- Creation Logic ---
        targets = [
            (today, "En cours"),       
            (today + timedelta(days=1), "À faire"),
            (today + timedelta(days=2), "À faire")
        ]

        for target_date, initial_status in targets:
            if target_date not in existing_dates:
                # Use centralized date formatting
                title = notion_service._get_formatted_date_title(target_date)
                
                logger.info(f"Creating missing daily task for {target_date}...")
                await notion_service.create_daily_task(target_date, title, status=initial_status)
            else:
                logger.debug(f"Task for {target_date} already exists, skipping.")
        
        logger.debug("Daily Routine completed.")
        data_store.preferences["_routine_date"] = today.isoformat()
        data_store.save_to_disk()

        # Notification du matin (non bloquante)
        await _send_morning_notification()

    except Exception as e:
        logger.error(f"Daily Routine failed: {e}")
