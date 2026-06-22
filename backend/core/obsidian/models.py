from dataclasses import dataclass
from pathlib import Path


@dataclass
class ObsidianNote:
    course_id: str
    college: str
    item_number: str
    title: str
    path: Path
    exists: bool
