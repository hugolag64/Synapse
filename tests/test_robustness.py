import asyncio
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from backend.config.settings import NOTION_PROPS as P
from backend.core.reviews import local_store
from frontend import utils


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    monkeypatch.setattr(local_store, "DB_PATH", tmp_path / "robustness.db")
    monkeypatch.setattr(local_store, "_DB", None)
    local_store.init_db()
    yield
    if local_store._DB is not None:
        local_store._DB.close()
    monkeypatch.setattr(local_store, "_DB", None)


def test_concurrent_study_session_writes_are_serialized():
    def write(index):
        return local_store.add_study_session(
            course_id=f"course-{index}", course_title="Test", item_number=str(index)
        )

    with ThreadPoolExecutor(max_workers=8) as pool:
        ids = list(pool.map(write, range(24)))

    assert len(ids) == 24
    with local_store._conn() as con:
        assert con.execute("SELECT COUNT(*) FROM study_sessions").fetchone()[0] == 24


def test_notion_failure_rolls_back_optimistic_course_update(monkeypatch):
    course = SimpleNamespace(id="course-1", qcm_done=False)
    monkeypatch.setattr(utils.data_store, "cours", [course])

    async def fail_update(*args, **kwargs):
        raise RuntimeError("Notion indisponible")

    monkeypatch.setattr(utils.notion_service, "update_course", fail_update)

    result = asyncio.run(utils.update_course_action(
        course, {P.QCM_COLLEGE: {"checkbox": True}}
    ))

    assert result is False
    assert course.qcm_done is False


def test_notion_failure_is_persisted_for_background_retry(monkeypatch):
    class HashableCourse(SimpleNamespace):
        __hash__ = object.__hash__

    course = HashableCourse(id="course-queue", qcm_done=False)
    monkeypatch.setattr(utils.data_store, "cours", [course])

    async def fail_update(*args, **kwargs):
        raise RuntimeError("Notion indisponible")

    monkeypatch.setattr(utils.notion_service, "update_course", fail_update)

    result = asyncio.run(utils.update_course_action(
        course, {P.QCM_COLLEGE: {"checkbox": True}}
    ))

    assert result is False
    pending = local_store.list_pending_notion_sync()
    assert len(pending) == 1
    assert pending[0]["course_id"] == "course-queue"
    assert pending[0]["properties"][P.QCM_COLLEGE] == {"checkbox": True}


def test_duplicate_async_quick_action_is_coalesced(monkeypatch):
    from frontend.components import course_quick_actions as quick_actions

    course = SimpleNamespace(id="course-1", title="Test", item_number="1", nb_lectures=0)
    update_calls = []
    record_calls = []

    async def fake_update(*args, **kwargs):
        update_calls.append(1)
        await asyncio.sleep(0.01)
        return True

    monkeypatch.setattr(quick_actions, "update_course_action", fake_update)
    monkeypatch.setattr(quick_actions, "record_evaluation", lambda evaluation: record_calls.append(evaluation))

    async def run_twice():
        await asyncio.gather(
            quick_actions.quick_mark_course_action(course, "lecture"),
            quick_actions.quick_mark_course_action(course, "lecture"),
        )

    asyncio.run(run_twice())

    assert len(update_calls) == 1
    assert len(record_calls) == 1


def test_sqlite_failure_after_notion_success_is_reported(monkeypatch):
    from frontend.components import course_quick_actions as quick_actions

    course = SimpleNamespace(id="course-1", title="Test", item_number="1", nb_lectures=0)
    monkeypatch.setattr(quick_actions, "update_course_action", AsyncMock(return_value=True))
    monkeypatch.setattr(
        quick_actions, "record_evaluation", Mock(side_effect=RuntimeError("SQLite indisponible"))
    )
    notify = Mock()
    monkeypatch.setattr(quick_actions.ui, "notify", notify)

    asyncio.run(quick_actions.quick_mark_course_action(course, "lecture"))

    assert any("session" in str(call).lower() for call in notify.call_args_list)
