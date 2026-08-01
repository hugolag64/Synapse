"""Tests pour le logger et la télémétrie des coûts IA."""

from backend.core.ai.logger import calculate_cost_usd, log_ai_call
from backend.core.ai.routing import AIModel, AITask
from backend.core.reviews.local_store import get_ai_usage_summary


def test_calculate_cost_usd_flash_lite():
    cost = calculate_cost_usd(AIModel.FLASH_LITE, 100_000, 50_000)
    # (100k/1M)*0.075 + (50k/1M)*0.30 = 0.0075 + 0.015 = 0.0225
    assert cost == 0.0225


def test_calculate_cost_usd_flash():
    cost = calculate_cost_usd(AIModel.FLASH, 1_000_000, 1_000_000)
    # 0.50 + 3.00 = 3.50
    assert cost == 3.5


def test_log_ai_call_and_summary():
    initial_summary = get_ai_usage_summary()
    initial_calls = initial_summary["summary"].get("total_calls", 0)

    cost = log_ai_call(
        task=AITask.QCM,
        model=AIModel.FLASH_LITE,
        input_tokens=1000,
        output_tokens=500,
        duration_ms=250.0,
        context="unit_test",
    )

    assert cost > 0
    updated_summary = get_ai_usage_summary()
    assert updated_summary["summary"]["total_calls"] == initial_calls + 1
