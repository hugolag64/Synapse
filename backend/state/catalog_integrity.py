"""Preuves rattachées à des fiches qui n'existent plus dans le catalogue.

La bascule vers le catalogue SQLite a laissé des traces orphelines : 104
révisions terminées sur 380 pointaient vers un `course_id` absent du catalogue
actif. Trois cas très différents s'y mélangeaient, et seul le premier est
normal :

  - **archivé** : cours pré-externat sorti du périmètre EDN — la trace doit
    rester où elle est ;
  - **rattachable** : la ligne porte un `item_number` dont l'item existe
    toujours ; la preuve appartient à cet item et peut lui être rendue ;
  - **inconnu** : ni item, ni fiche — reliquats de tests (`c1`, `c2`, `c99`).
    Ce module les compte et ne les touche jamais.

`reattach_orphan_evidence()` simule par défaut : rien n'est écrit sans
`apply=True`.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from backend.core.reviews import local_store

# Tables portant une preuve rattachée à une fiche, avec la colonne qui permet
# de retrouver l'item quand la fiche a disparu.
_EVIDENCE_TABLES = (
    ("review_history", "item_number"),
    ("study_sessions", "item_number"),
    ("qcm_sessions", "item_number"),
)


@dataclass
class OrphanReport:
    """Photographie des traces orphelines, par table et par cause."""

    archived: dict[str, int] = field(default_factory=dict)
    reattachable: dict[str, int] = field(default_factory=dict)
    duplicates: dict[str, int] = field(default_factory=dict)
    unknown: dict[str, int] = field(default_factory=dict)
    unknown_ids: tuple[str, ...] = ()

    @property
    def total_reattachable(self) -> int:
        return sum(self.reattachable.values())

    @property
    def total_duplicates(self) -> int:
        return sum(self.duplicates.values())

    @property
    def total_unknown(self) -> int:
        return sum(self.unknown.values())

    @property
    def total_archived(self) -> int:
        return sum(self.archived.values())

    @property
    def is_clean(self) -> bool:
        """Aucune preuve à rendre. Doublons et reliquats restent signalés."""
        return not self.total_reattachable


def _active_fiche_by_item() -> tuple[set[str], dict[str, str]]:
    """({fiche_ids actives}, {numéro d'item: fiche canonique})."""
    from backend.core.knowledge.course_aliases import canonical_course, normalized_item
    from backend.state.store import data_store

    courses = list(data_store.cours)
    active = {str(course.id) for course in courses}
    groups: dict[str, list] = {}
    for course in courses:
        number = normalized_item(course)
        if number:
            groups.setdefault(number, []).append(course)
    canonical = {number: str(canonical_course(fiches).id) for number, fiches in groups.items()}
    return active, canonical


def _archived_ids() -> set[str]:
    try:
        with local_store._conn() as con:
            return {
                str(row[0])
                for row in con.execute("SELECT id FROM catalog_archived_courses")
            }
    except Exception:
        return set()


def _normalized_number(value) -> str:
    raw = str(value or "").strip().removeprefix("ITEM ")
    try:
        return str(int(float(raw)))
    except (TypeError, ValueError):
        return ""


def orphan_report() -> OrphanReport:
    """Compte les traces orphelines sans rien modifier."""
    active, canonical = _active_fiche_by_item()
    archived = _archived_ids()
    report = OrphanReport()
    unknown_ids: set[str] = set()

    with local_store._conn() as con:
        known_tasks = {
            str(row[0]) for row in con.execute("SELECT task_id FROM review_history")
        }
        for table, number_column in _EVIDENCE_TABLES:
            columns = "course_id, task_id" if table == "review_history" else "course_id"
            try:
                rows = con.execute(
                    f"SELECT {columns}, {number_column} AS item_number FROM {table}"
                ).fetchall()
            except Exception:
                continue
            for row in rows:
                course_id = str(row["course_id"] or "")
                if not course_id or course_id in active:
                    continue
                if course_id in archived:
                    report.archived[table] = report.archived.get(table, 0) + 1
                    continue
                target = canonical.get(_normalized_number(row["item_number"]))
                if not target:
                    report.unknown[table] = report.unknown.get(table, 0) + 1
                    unknown_ids.add(course_id)
                    continue
                # La même révision déjà enregistrée sur la fiche d'accueil :
                # la trace orpheline est un doublon, pas une preuve à rendre.
                if table == "review_history" and str(
                    row["task_id"] or ""
                ).replace(course_id, target, 1) in known_tasks:
                    report.duplicates[table] = report.duplicates.get(table, 0) + 1
                else:
                    report.reattachable[table] = report.reattachable.get(table, 0) + 1

    report.unknown_ids = tuple(sorted(unknown_ids))
    return report


def reattach_orphan_evidence(apply: bool = False) -> dict:
    """Rend à leur item les preuves dont la fiche a disparu.

    `review_history.task_id` encode le `course_id` : le réécrire est
    indispensable, sinon le moteur ne reconnaîtrait plus la tâche terminée et
    la reproposerait. Un `task_id` déjà présent sur la fiche d'accueil signale
    la même révision déjà enregistrée : la ligne orpheline est laissée en
    place plutôt que d'écraser la trace existante.
    """
    active, canonical = _active_fiche_by_item()
    archived = _archived_ids()
    moved: dict[str, int] = {}
    conflicts: dict[str, int] = {}
    details: list[dict] = []

    with local_store._conn() as con:
        for table, number_column in _EVIDENCE_TABLES:
            try:
                rows = con.execute(
                    f"SELECT rowid AS _rowid, * FROM {table}"
                ).fetchall()
            except Exception:
                continue
            existing_tasks = set()
            if table == "review_history":
                existing_tasks = {
                    str(row[0])
                    for row in con.execute("SELECT task_id FROM review_history")
                }
            for row in rows:
                course_id = str(row["course_id"] or "")
                if not course_id or course_id in active or course_id in archived:
                    continue
                target = canonical.get(_normalized_number(row["item_number"]))
                if not target:
                    continue
                if table == "review_history":
                    task_id = str(row["task_id"] or "")
                    new_task_id = task_id.replace(course_id, target, 1)
                    if new_task_id in existing_tasks:
                        conflicts[table] = conflicts.get(table, 0) + 1
                        continue
                    if apply:
                        con.execute(
                            "UPDATE review_history SET course_id = ?, task_id = ? WHERE rowid = ?",
                            (target, new_task_id, row["_rowid"]),
                        )
                    existing_tasks.add(new_task_id)
                elif apply:
                    con.execute(
                        f"UPDATE {table} SET course_id = ? WHERE rowid = ?",
                        (target, row["_rowid"]),
                    )
                moved[table] = moved.get(table, 0) + 1
                if len(details) < 20:
                    details.append({
                        "table": table,
                        "from": course_id,
                        "to": target,
                        "item_number": _normalized_number(row["item_number"]),
                        "title": str(row["course_title"] or "") if "course_title" in row.keys() else "",
                    })

    return {
        "applied": bool(apply),
        "moved": moved,
        "total_moved": sum(moved.values()),
        "conflicts": conflicts,
        "details": details,
    }
