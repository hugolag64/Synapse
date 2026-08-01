"""Module de journalisation dédiée et de calcul des coûts des appels API IA."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from loguru import logger

from backend.core.ai.routing import AIModel, AITask

# Chemin du fichier de log dédié
LOGS_DIR = Path(__file__).resolve().parents[3] / "logs"
AI_LOG_FILE = LOGS_DIR / "ai_usage.log"

# Configuration d'un logger dédié Loguru pour l'IA
LOGS_DIR.mkdir(parents=True, exist_ok=True)
ai_logger = logger.bind(channel="ai_usage")
logger.add(
    AI_LOG_FILE,
    filter=lambda record: record["extra"].get("channel") == "ai_usage",
    rotation="10 MB",
    retention="60 days",
    format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}",
    encoding="utf-8",
)

# Tarifs au 1M tokens (Gemini 2.5 Flash / Flash Lite)
# Source: https://ai.google.dev/pricing
PRICING_PER_MILLION = {
    AIModel.FLASH_LITE: {"input": 0.075, "output": 0.30},
    AIModel.FLASH: {"input": 0.50, "output": 3.00},
}


def calculate_cost_usd(model: AIModel | str, input_tokens: int | None, output_tokens: int | None) -> float:
    """Calcule le coût estimé en USD pour un appel IA selon le modèle et les tokens."""
    in_tok = input_tokens or 0
    out_tok = output_tokens or 0
    
    try:
        model_enum = model if isinstance(model, AIModel) else AIModel(model)
        rates = PRICING_PER_MILLION.get(model_enum, {"input": 0.50, "output": 3.00})
    except ValueError:
        rates = {"input": 0.50, "output": 3.00}

    cost_in = (in_tok / 1_000_000.0) * rates["input"]
    cost_out = (out_tok / 1_000_000.0) * rates["output"]
    return round(cost_in + cost_out, 6)


def log_ai_call(
    task: AITask | str,
    model: AIModel | str,
    input_tokens: int | None,
    output_tokens: int | None,
    duration_ms: float | None = None,
    error: str | None = None,
    context: str | None = None,
) -> float:
    """Consigne l'appel IA dans le fichier ai_usage.log et en base de données."""
    task_str = task.value if isinstance(task, AITask) else str(task)
    model_str = model.value if isinstance(model, AIModel) else str(model)
    cost_usd = calculate_cost_usd(model, input_tokens, output_tokens)

    status = "ERROR" if error else "SUCCESS"
    log_msg = (
        f"[{status}] Task={task_str} | Model={model_str} | "
        f"InTokens={input_tokens or 0} | OutTokens={output_tokens or 0} | "
        f"Cost=${cost_usd:.6f} | Duration={duration_ms or 0:.0f}ms"
    )
    if context:
        log_msg += f" | Context={context}"
    if error:
        log_msg += f" | Error={error}"

    ai_logger.info(log_msg)

    # Persistance SQLite
    try:
        from backend.core.reviews.local_store import record_ai_usage
        record_ai_usage(
            task=task_str,
            model=model_str,
            input_tokens=input_tokens or 0,
            output_tokens=output_tokens or 0,
            cost_usd=cost_usd,
            duration_ms=duration_ms,
            error=error,
            context=context,
        )
    except Exception as exc:
        ai_logger.error(f"Échec de l'enregistrement SQLite du log IA: {exc}")

    return cost_usd
