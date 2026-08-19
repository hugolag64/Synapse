from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Literal

PrepTaskType = Literal["pdf", "obsidian", "resume", "first_read"]
PrepTaskStatus = Literal["todo", "done", "cancelled"]


@dataclass(frozen=True)
class PrepTask:
    id: int
    course_id: str
    item_number: str
    lecture_date: date
    calendar_event_id: str
    calendar_title: str
    task_type: PrepTaskType
    status: PrepTaskStatus
    created_at: str
    updated_at: str
    completed_at: str | None


@dataclass(frozen=True)
class LearningSchedule:
    course_id: str
    context: str
    first_read_date: date
    j1_date: date
    j3_date: date
    j7_date: date
    j14_date: date
    j30_date: date
    updated_at: str

