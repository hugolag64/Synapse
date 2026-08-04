"""
test_phase5_edn.py — Synapse
-----------------------------
Tests unitaires pour la Phase 5 (Flash-Zero Quiz, Générateur IA DP Lacunes, Sprint Countdown).
"""

from datetime import date, timedelta
from backend.core.practice.flash_zero_service import FlashZeroService
from backend.core.planning.sprint_countdown import SprintCountdownService, SprintPhase


def test_flash_zero_service():
    service = FlashZeroService()
    quiz = service.get_morning_quiz(count=5)
    assert len(quiz) == 5
    for q in quiz:
        assert q.question_text
        assert len(q.choices) >= 2
        assert 0 <= q.correct_idx < len(q.choices)
        assert q.category


def test_sprint_countdown_service():
    # Test avec une date lointaine (> 120 jours)
    far_future = date.today() + timedelta(days=150)
    service_far = SprintCountdownService(target_date_str=far_future.strftime("%Y-%m-%d"))
    status_far = service_far.get_sprint_status()
    assert status_far.phase == SprintPhase.LONG_TERM
    assert status_far.days_remaining == 150

    # Test avec une date proche (Sprint Flash <= 30 jours)
    near_future = date.today() + timedelta(days=15)
    service_near = SprintCountdownService(target_date_str=near_future.strftime("%Y-%m-%d"))
    status_near = service_near.get_sprint_status()
    assert status_near.phase == SprintPhase.SPRINT_FLASH
    assert status_near.recommended_qcm_dp_ratio == 0.60


def test_sprint_countdown_accepts_the_persisted_target_date():
    service = SprintCountdownService(target_date_str="2026-10-15")

    assert service.target_date == date(2026, 10, 15)
