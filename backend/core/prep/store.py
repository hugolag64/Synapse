from __future__ import annotations

import datetime
from collections.abc import Iterable

from backend.core.prep.models import LearningSchedule, PrepTask, PrepTaskStatus, PrepTaskType
from backend.core.reviews import local_store


_TASK_TYPES = {"pdf", "obsidian", "resume", "first_read"}
_TASK_STATUSES = {"todo", "done", "cancelled"}


def _task_from_row(row) -> PrepTask:
    return PrepTask(
        id=int(row["id"]),
        course_id=str(row["course_id"]),
        item_number=str(row["item_number"] or ""),
        lecture_date=datetime.date.fromisoformat(str(row["lecture_date"])),
        calendar_event_id=str(row["calendar_event_id"] or ""),
        calendar_title=str(row["calendar_title"] or ""),
        task_type=str(row["task_type"]),
        status=str(row["status"]),
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
        completed_at=str(row["completed_at"]) if row["completed_at"] else None,
    )


def _schedule_from_row(row) -> LearningSchedule:
    return LearningSchedule(
        course_id=str(row["course_id"]),
        context=str(row["context"]),
        first_read_date=datetime.date.fromisoformat(str(row["first_read_date"])),
        j1_date=datetime.date.fromisoformat(str(row["j1_date"])),
        j3_date=datetime.date.fromisoformat(str(row["j3_date"])),
        j7_date=datetime.date.fromisoformat(str(row["j7_date"])),
        j14_date=datetime.date.fromisoformat(str(row["j14_date"])),
        j30_date=datetime.date.fromisoformat(str(row["j30_date"])),
        updated_at=str(row["updated_at"]),
    )


def list_prep_tasks(
    day: datetime.date | None = None,
    statuses: tuple[str, ...] = ("todo",),
) -> list[PrepTask]:
    if not statuses or any(status not in _TASK_STATUSES for status in statuses):
        raise ValueError("Statut de préparation inconnu")
    placeholders = ",".join("?" for _ in statuses)
    params: list[object] = list(statuses)
    where = f"status IN ({placeholders})"
    if day is not None:
        where += " AND lecture_date = ?"
        params.append(day.isoformat())
    with local_store._conn() as con:
        rows = con.execute(
            f"SELECT * FROM course_prep_tasks WHERE {where} ORDER BY lecture_date, item_number, task_type, id",
            params,
        ).fetchall()
    return [_task_from_row(row) for row in rows]


def get_prep_task(task_id: int) -> PrepTask | None:
    row = local_store._conn().execute(
        "SELECT * FROM course_prep_tasks WHERE id = ?", (int(task_id),)
    ).fetchone()
    return _task_from_row(row) if row else None


def upsert_prep_task(
    course_id: str,
    item_number: str,
    lecture_date: datetime.date,
    calendar_event_id: str,
    calendar_title: str,
    task_type: PrepTaskType,
) -> PrepTask:
    if task_type not in _TASK_TYPES:
        raise ValueError("Type de préparation inconnu")
    now = local_store._now()
    with local_store._conn() as con:
        con.execute(
            """
            INSERT INTO course_prep_tasks
                (course_id, item_number, lecture_date, calendar_event_id,
                 calendar_title, task_type, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, 'todo', ?, ?)
            ON CONFLICT(course_id, lecture_date, task_type) DO UPDATE SET
                item_number = excluded.item_number,
                calendar_event_id = excluded.calendar_event_id,
                calendar_title = excluded.calendar_title,
                updated_at = excluded.updated_at
            """,
            (
                str(course_id), str(item_number), lecture_date.isoformat(),
                str(calendar_event_id or ""), str(calendar_title or ""),
                task_type, now, now,
            ),
        )
        row = con.execute(
            """SELECT * FROM course_prep_tasks
               WHERE course_id = ? AND lecture_date = ? AND task_type = ?""",
            (str(course_id), lecture_date.isoformat(), task_type),
        ).fetchone()
    return _task_from_row(row)


def update_prep_task_status(task_id: int, status: PrepTaskStatus) -> PrepTask:
    if status not in _TASK_STATUSES:
        raise ValueError("Statut de préparation inconnu")
    now = local_store._now()
    completed_at = now if status == "done" else None
    with local_store._conn() as con:
        con.execute(
            """UPDATE course_prep_tasks
               SET status = ?, completed_at = ?, updated_at = ?
               WHERE id = ?""",
            (status, completed_at, now, int(task_id)),
        )
        row = con.execute(
            "SELECT * FROM course_prep_tasks WHERE id = ?", (int(task_id),)
        ).fetchone()
    if row is None:
        raise KeyError(f"Tâche de préparation inconnue : {task_id}")
    return _task_from_row(row)


def get_learning_schedule(
    course_id: str,
    context: str = "college",
) -> LearningSchedule | None:
    with local_store._conn() as con:
        row = con.execute(
            """SELECT * FROM course_learning_schedule
               WHERE course_id = ? AND context = ?""",
            (str(course_id), str(context)),
        ).fetchone()
    return _schedule_from_row(row) if row else None


def list_learning_schedules(context: str | None = None) -> list[LearningSchedule]:
    query = "SELECT * FROM course_learning_schedule"
    params: tuple[str, ...] = ()
    if context is not None:
        query += " WHERE context = ?"
        params = (context,)
    query += " ORDER BY course_id"
    rows = local_store._conn().execute(query, params).fetchall()
    return [_schedule_from_row(row) for row in rows]


def save_learning_schedule(
    course_id: str,
    first_read_date: datetime.date,
    context: str = "college",
) -> LearningSchedule:
    dates = {
        "first_read_date": first_read_date,
        "j1_date": first_read_date + datetime.timedelta(days=1),
        "j3_date": first_read_date + datetime.timedelta(days=3),
        "j7_date": first_read_date + datetime.timedelta(days=7),
        "j14_date": first_read_date + datetime.timedelta(days=14),
        "j30_date": first_read_date + datetime.timedelta(days=30),
    }
    now = local_store._now()
    with local_store._conn() as con:
        con.execute(
            """
            INSERT INTO course_learning_schedule
                (course_id, context, first_read_date, j1_date, j3_date,
                 j7_date, j14_date, j30_date, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(course_id, context) DO UPDATE SET
                first_read_date = excluded.first_read_date,
                j1_date = excluded.j1_date,
                j3_date = excluded.j3_date,
                j7_date = excluded.j7_date,
                j14_date = excluded.j14_date,
                j30_date = excluded.j30_date,
                updated_at = excluded.updated_at
            """,
            (
                str(course_id), str(context),
                dates["first_read_date"].isoformat(), dates["j1_date"].isoformat(),
                dates["j3_date"].isoformat(), dates["j7_date"].isoformat(),
                dates["j14_date"].isoformat(), dates["j30_date"].isoformat(), now,
            ),
        )
        row = con.execute(
            """SELECT * FROM course_learning_schedule
               WHERE course_id = ? AND context = ?""",
            (str(course_id), str(context)),
        ).fetchone()
    return _schedule_from_row(row)


def move_pending_prep_tasks(
    calendar_event_id: str,
    lecture_date: datetime.date,
    calendar_title: str,
) -> int:
    now = local_store._now()
    with local_store._conn() as con:
        cursor = con.execute(
            """UPDATE course_prep_tasks
               SET lecture_date = ?, calendar_title = ?, updated_at = ?
               WHERE calendar_event_id = ? AND status = 'todo'
                 AND lecture_date != ?""",
            (
                lecture_date.isoformat(), str(calendar_title or ""), now,
                str(calendar_event_id or ""), lecture_date.isoformat(),
            ),
        )
    return int(cursor.rowcount)


def cancel_pending_prep_tasks(calendar_event_id: str) -> int:
    now = local_store._now()
    with local_store._conn() as con:
        cursor = con.execute(
            """UPDATE course_prep_tasks
               SET status = 'cancelled', updated_at = ?
               WHERE calendar_event_id = ? AND status = 'todo'""",
            (now, str(calendar_event_id or "")),
        )
    return int(cursor.rowcount)
