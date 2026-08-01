"""
test_externat.py — Suite de tests pour le mode Externat.
"""
from __future__ import annotations

import datetime
from unittest.mock import MagicMock, patch

import pytest

from backend.core.externat import store as externat_store
from backend.core.externat.models import Stage, ActiveStage
from backend.core.externat.service import ExternatService, STAGE_BOOST


@pytest.fixture(autouse=True)
def setup_externat_db(tmp_path, monkeypatch):
    test_db = tmp_path / "synapse_test_externat.db"
    monkeypatch.setattr(externat_store, "DB_PATH", test_db)
    externat_store.init_db()


def test_stage_model_properties():
    today = datetime.date.today()
    stage = Stage(
        id=1,
        specialty="Cardiologie",
        college_notion="Cardiologie",
        start_date=today - datetime.timedelta(days=10),
        end_date=today + datetime.timedelta(days=20),
        objectives="Objectif test",
        is_active=True,
    )
    assert stage.is_current is True
    assert stage.is_past is False
    assert stage.is_future is False
    assert stage.duration_weeks == 4
    assert stage.days_remaining == 20
    assert stage.days_elapsed == 10
    assert stage.status_label == "En cours"


def test_stage_crud():
    today = datetime.date.today()
    stage_id = externat_store.add_stage(
        specialty="Neurologie",
        college_notion="Neurologie",
        start_date=today,
        end_date=today + datetime.timedelta(days=30),
        objectives="Découvrir l'AVC",
    )
    assert stage_id is not None

    stage = externat_store.get_stage(stage_id)
    assert stage is not None
    assert stage.specialty == "Neurologie"
    assert stage.objectives == "Découvrir l'AVC"

    active_stage = externat_store.get_active_stage()
    assert active_stage is not None
    assert active_stage.id == stage_id

    externat_store.update_stage(stage_id, objectives="Découvrir l'AVC et la SEP")
    updated = externat_store.get_stage(stage_id)
    assert updated.objectives == "Découvrir l'AVC et la SEP"

    externat_store.delete_stage(stage_id)
    assert externat_store.get_stage(stage_id) is None


def test_externat_service_boost():
    service = ExternatService()
    today = datetime.date.today()
    stage = Stage(
        id=1,
        specialty="Cardiologie",
        college_notion="Cardiologie",
        start_date=today - datetime.timedelta(days=5),
        end_date=today + datetime.timedelta(days=25),
    )

    # Simuler des tâches de révision
    task1 = MagicMock()
    task1.college = ["Cardiologie"]
    task1.days_overdue = 1
    task1.priority_score = 10.0
    task1.course_title = "Infarctus"
    task1.review_type = "J3"
    task1.copy.side_effect = lambda update: MagicMock(
        college=task1.college,
        days_overdue=task1.days_overdue,
        priority_score=update["priority_score"],
        course_title=task1.course_title,
    )

    task2 = MagicMock()
    task2.college = ["Pneumologie"]
    task2.days_overdue = 1
    task2.priority_score = 12.0
    task2.course_title = "Asthme"

    tasks = [task1, task2]
    boosted = service.apply_stage_boost(tasks, stage=stage)

    # task1 (Cardiologie) passe de 10 à 15 (10 + 5.0 boost)
    # Il doit passer devant task2 (12.0)
    assert boosted[0].priority_score == 15.0
    assert boosted[0].course_title == "Infarctus"
