"""items.py — Vue « Items » (refonte, session 9, écran nouveau).

Liste transverse filtrable de tous les items médicaux.

Point d'entrée attendu par la « retard » cliquable de Collèges (session 7,
`?college=`) : filtre initial sur ce collège, colonne Collège masquée au
profit de « Dernière révision » (README §7).

Écarts assumés (voir Journal du CLAUDE.md de la refonte) :
  • chips = sélection unique (Tous / <collège navigué> / Fragile-critique /
    En retard), pas des filtres indépendants cumulables — cohérent avec la
    capture (un seul chip actif à la fois) ;
  • « type » dérivé simplement (LACUNE si lacune active, sinon PDF si
    ressource liée, sinon NOTE) — pas de distinction QCM/RAPPEL faute de
    signal fiable par cours (contrairement aux ReviewTask de Révisions) ;
  • « dernière révision » = date de la session la plus récente
    (`study_sessions`), aucune session → « — » ; couleur = fraîcheur
    (≤7 j vert, ≤30 j ambre, plus ancien ou jamais = gris), pas de grille
    officielle donnée par le README pour ce point.
"""
from __future__ import annotations

import datetime
import os
from urllib.parse import quote

from nicegui import ui
from starlette.requests import Request

from frontend.theme import frame
from backend.state.store import data_store
from backend.state.catalog_repository import CatalogRepository
from backend.core.notion.models import Cours
from backend.core.knowledge.course_aliases import canonical_course, colleges_of_item, normalized_item
from backend.core.reviews.mastery import _merged_item_course
from backend.core.reviews import local_store
from backend.core.reviews.local_store import (
    get_sessions_by_course, get_postpone_counts,
    get_qcm_done_course_ids, get_active_lacunes_count_by_course,
)
from backend.core.reviews.service import review_service
from backend.core.reviews.reentry import filter_active_review_tasks, get_study_resume_date
from backend.core.reviews.mastery import get_course_mastery, get_item_mastery
from backend.core.prep.service import anchor_first_read
from backend.core.knowledge.item_progress import scheduled_course_ids
from frontend.components.study_task_row import _ring_glyph, due_info
from frontend.components.mastery_indicator import mastery_indicator, ensure_styles as _mastery_styles
from frontend.components.ednpro_frequency_badge import ednpro_frequency_badge
from frontend.components.command_palette import open_command_palette

_PAGE_SIZE = 150

# La ligne entière est cliquable : une action posée dedans doit retenir le clic,
# sinon « Commencer » ouvre la fiche au lieu de planifier.
_STOP_PROPAGATION_JS = "(event) => { event.stopPropagation(); emit(event); }"

_CSS = """
.it-wrap { max-width:none; width:100%; min-width:0; overflow:hidden; }
.it-topbar { display:flex; align-items:flex-start; justify-content:space-between; gap:16px; padding:4px 0 14px; flex-wrap:wrap; }
.it-title { font-size:20px; font-weight:600; color:var(--text); letter-spacing:-0.01em; }
.it-subtitle { font-size:12.5px; color:var(--text-muted); margin-top:4px; }
.it-search { display:flex; align-items:center; gap:8px; height:32px; padding:0 10px; border:1px solid var(--border);
  border-radius:6px; color:var(--text-dim); font-size:12px; cursor:pointer; background:var(--bg); flex:0 0 auto; }
.it-search:hover { border-color:var(--border-strong); }
.it-search kbd { font-family:var(--font-mono); font-size:10.5px; border:1px solid var(--border); border-radius:4px; padding:0 4px; }
.it-chips-row { display:flex; align-items:center; gap:10px; margin-bottom:14px; flex-wrap:wrap; }
.it-chips { display:flex; gap:6px; flex-wrap:wrap; }
.it-chip { font-size:12px; font-weight:500; padding:5px 12px; border-radius:6px; cursor:pointer;
  color:var(--text-muted); border:1px solid var(--border); background:var(--bg);
  transition: background var(--duration-fast) var(--ease-standard),
              color var(--duration-fast) var(--ease-standard),
              border-color var(--duration-fast) var(--ease-standard); }
.it-chip:hover { background:var(--surface); }
.it-chip.active { background:var(--accent); border-color:var(--accent); color:var(--accent-text); }
.it-filter-hint { font-size:11.5px; color:var(--text-dim); font-style:italic; }
.it-head, .it-row { display:grid; box-sizing:border-box; grid-template-columns:16px 46px minmax(180px,1fr) 110px 160px 70px 140px 84px; align-items:center; column-gap:12px; }
.it-head { width:100%; padding:0 10px 8px; font-size:10px;
  text-transform:uppercase; letter-spacing:.04em; color:var(--text-dim); font-weight:600;
  border-bottom:1px solid var(--border); }
.it-head > * { text-align:center; }
.it-row { min-height:54px; height:auto; width:100%; min-width:0; padding:7px 10px; border-bottom:1px solid var(--border);
  cursor:pointer; color:var(--text); text-decoration:none; transition: background var(--duration-fast) var(--ease-standard); }
.it-row:hover { background:var(--surface); }
.it-row:last-child { border-bottom:none; }
.it-ring { font-size:14px; color:var(--text-muted); flex:0 0 16px; text-align:center; }
.it-id { font-family:var(--font-mono); font-size:11.5px; color:var(--text-muted); flex:0 0 46px; text-align:center; }
.it-title-cell { min-width:0; font-size:13px; line-height:1.3; white-space:normal; overflow:hidden; text-overflow:clip; display:-webkit-box; -webkit-box-orient:vertical; -webkit-line-clamp:2; }
.it-frequency { min-width:0; display:flex; align-items:center; justify-content:center; text-align:center; }
.it-college { min-width:0; font-size:12px; color:var(--text-muted); white-space:nowrap; overflow:hidden;
  text-overflow:ellipsis; text-align:center; }
.it-college-link { cursor:pointer; }
.it-college-link:hover { color:var(--accent); text-decoration:underline; }
.it-last { min-width:0; display:flex; align-items:center; gap:6px; font-size:12px; color:var(--text-muted); }
.it-last-dot { width:6px; height:6px; border-radius:50%; flex:0 0 6px; }
.it-type { font-family:var(--font-mono); font-size:10px; letter-spacing:.03em; color:var(--text-muted);
  border:1px solid var(--border); border-radius:4px; padding:1px 5px; text-align:center; }
.it-mastery { min-width:0; display:flex; align-items:center; justify-content:center; text-align:center; }
.it-next { min-width:0; display:flex; align-items:center; justify-content:center; gap:5px; font-size:11.5px; color:var(--text-muted); text-align:center; }
.it-next-dot { width:6px; height:6px; border-radius:50%; flex:0 0 6px; }
.it-resume { color:var(--warning-text); }
.it-unplanned { font-size:11.5px; color:var(--text-dim); font-style:italic; }
.it-start { font-size:11px; font-weight:500; padding:3px 8px; border-radius:6px; cursor:pointer;
  color:var(--accent); border:1px dashed var(--border-strong); background:var(--bg); white-space:nowrap;
  transition: background var(--duration-fast) var(--ease-standard),
              border-color var(--duration-fast) var(--ease-standard); }
.it-start:hover { background:var(--surface); border-color:var(--accent); border-style:solid; }
.it-empty { padding:32px 10px; text-align:center; color:var(--text-dim); font-size:13px; }
.it-row-missing { cursor:default; }
.it-row-missing:hover { background:transparent; }
.it-missing-badge { font-size:10px; color:var(--text-dim); font-style:italic; margin-left:6px; white-space:nowrap; }
.it-group-label { padding:12px 10px 6px; color:var(--text-dim); font-size:10px; font-weight:600;
  letter-spacing:.05em; text-transform:uppercase; border-bottom:1px solid var(--border); }
@media (max-width: 900px) {
  .it-head, .it-row { grid-template-columns:16px 46px minmax(150px,1fr) 96px 120px 70px 110px 70px; }
}
"""


def _safe_item_number(n: str | None) -> float:
    if not n:
        return 999999.0
    try:
        return float(str(n).replace(",", "."))
    except (TypeError, ValueError):
        return 999999.0


def _normalized_item_number(value) -> str:
    raw = str(value or "").strip().removeprefix("ITEM ")
    try:
        return str(int(float(raw)))
    except (TypeError, ValueError):
        return ""


def _college_names(course) -> tuple[str, ...]:
    return tuple(sorted(
        (str(name) for name in (course.college or []) if name),
        key=str.casefold,
    ))


def _primary_college(row: dict) -> str:
    names = _college_names(row["course"])
    return names[0] if names else "Sans collège"


def build_item_rows(repository: CatalogRepository | None = None) -> list[dict]:
    """Build one row per official item, including items without a fiche."""
    courses = list(data_store.cours)
    by_id = {str(course.id): course for course in courses}
    if repository is None:
        repository = CatalogRepository(os.getenv("SYNAPSE_CATALOG_DB_PATH"))

    official_items = list(repository.list_items()) if hasattr(repository, "list_items") else []
    rows: list[dict] = []
    if official_items:
        # Deux requêtes globales plutôt qu'une par item (734 requêtes, 0,93 s
        # pour 367 items avant ce correctif — N19).
        fiches_by_item: dict[str, list] = {}
        for fiche in repository.list_all_fiches():
            fiches_by_item.setdefault(str(fiche.item_id), []).append(fiche)
        colleges_by_item = repository.list_colleges_by_item()
        for item in official_items:
            fiche_records = fiches_by_item.get(item.id, [])
            fiche_ids = tuple(str(fiche.id) for fiche in fiche_records)
            fiche_courses = [by_id[fiche_id] for fiche_id in fiche_ids if fiche_id in by_id]
            item_colleges = colleges_by_item.get(item.id, [])
            if fiche_courses:
                course = _merged_item_course(fiche_courses)
            else:
                course = Cours(
                    id=item.id,
                    title=item.title,
                    item_number=str(item.item_number),
                    college=list(item_colleges),
                    created_time=datetime.datetime.now(datetime.timezone.utc),
                )
            colleges = list(item_colleges) or list(course.college or [])
            updates = {"title": item.title, "item_number": str(item.item_number), "college": colleges}
            course = course.model_copy(update=updates) if hasattr(course, "model_copy") else course.copy(update=updates)
            rows.append({
                "item_id": item.id,
                "item_number": item.item_number,
                "title": item.title,
                "course": course,
                "fiche_ids": fiche_ids,
                "colleges": colleges,
                "missing_fiche": not bool(fiche_courses),
            })
        return rows

    # Explicit fallback for an unimported installation: preserve the legacy
    # JSON-backed screen, but still collapse duplicate fiches by item number.
    groups: dict[str, list] = {}
    for course in courses:
        item_number = normalized_item(course)
        if item_number:
            groups.setdefault(item_number, []).append(course)
    for item_number, item_courses in sorted(groups.items(), key=lambda pair: int(pair[0])):
        course = _merged_item_course(item_courses)
        rows.append({
            "item_id": str(course.id),
            "item_number": int(item_number),
            "title": course.title,
            "course": course,
            "fiche_ids": tuple(str(c.id) for c in item_courses),
            "colleges": list(course.college or []),
            "missing_fiche": False,
        })
    return rows


_ANNUAL_PRIORITY_RANK = {
    "indispensable": 0,
    "important": 1,
    "basique": 2,
    "jamais_tombe": 3,
}


def _sort_item_rows(rows: list[dict], mode: str = "item") -> list[dict]:
    """Trie sans dupliquer les items multi-collèges."""
    if mode == "college":
        return sorted(
            rows,
            key=lambda r: (
                _primary_college(r).casefold(),
                _safe_item_number(r["course"].item_number),
                r["course"].title.casefold(),
            ),
        )
    if mode == "priority":
        return sorted(
            rows,
            key=lambda r: (
                _ANNUAL_PRIORITY_RANK.get(
                    str((r.get("ednpro_frequency") or {}).get("priority") or "jamais_tombe").strip().lower(),
                    _ANNUAL_PRIORITY_RANK["jamais_tombe"],
                ),
                _safe_item_number(r["course"].item_number),
                r["course"].title.casefold(),
            ),
        )
    return sorted(
        rows,
        key=lambda r: (_safe_item_number(r["course"].item_number), r["course"].title.casefold()),
    )


def group_item_rows(
    rows: list[dict], active_college: str | None = None
) -> list[tuple[str, list[dict]]]:
    """Regroupe les lignes par collège principal sans dupliquer un item.

    Le regroupement se fait par défaut sur le collège *principal* de chaque
    item (le premier par ordre alphabétique) — pour un item multi-collèges,
    ce n'est pas forcément le collège qu'un filtre actif a sélectionné : le
    libellé de groupe affiché ne correspondait alors pas au collège filtré
    (N17). Sous un filtre, toutes les lignes appartiennent déjà à ce collège :
    un seul groupe, portant son nom, évite l'étiquette trompeuse.
    """
    if active_college and active_college != "Tous":
        # Un seul groupe : trier par numéro d'item, pas par collège principal
        # (sans objet ici, toutes les lignes partagent déjà le même collège).
        return [(active_college, _sort_item_rows(rows, "item"))]
    groups: dict[str, list[dict]] = {}
    for row in _sort_item_rows(rows, "college"):
        groups.setdefault(_primary_college(row), []).append(row)
    return list(groups.items())


def get_adjacent_items(
    item_number: str, college: str | None = None, repository: CatalogRepository | None = None,
) -> tuple[dict | None, dict | None]:
    """Item précédent/suivant dans le même ordre que `/items` (par numéro),
    filtré sur le même collège si la fiche a été ouverte depuis une liste
    filtrée — la fiche détail n'avait aucun moyen de circuler entre items
    sans repasser par la liste (§7.3, 4.5)."""
    rows = build_item_rows(repository)
    if college:
        rows = [row for row in rows if college in (row["colleges"] or [])]
    rows = _sort_item_rows(rows, "item")
    current = str(item_number).strip()
    index = next(
        (i for i, row in enumerate(rows) if str(row["course"].item_number) == current), None,
    )
    if index is None:
        return None, None
    previous = rows[index - 1] if index > 0 else None
    following = rows[index + 1] if index + 1 < len(rows) else None
    return previous, following


def visible_item_rows(rows: list[dict], filt: dict) -> list[dict]:
    """
    Lignes réellement rendues : filtre courant puis tri courant.

    Le tri doit être appliqué au rendu et non à la collecte : `_compute()` n'est
    exécuté qu'une fois par chargement de page, alors que le mode de tri change
    à chaque clic sur un chip.
    """
    college = filt.get("college", "Tous")
    mode = filt.get("mode", "all")

    selected = list(rows)
    if college != "Tous":
        selected = [r for r in selected if college in (r["course"].college or [])]
    if mode == "fragile":
        selected = [r for r in selected if r["mastery_level"] in ("fragile", "critique")]
    elif mode == "overdue":
        selected = [r for r in selected if r["overdue"]]

    return _sort_item_rows(selected, filt.get("sort", "item"))


def _last_review_info(sessions: list) -> tuple[str, str]:
    """(couleur token, libellé relatif) à partir des study_sessions d'un cours."""
    if not sessions:
        return "var(--text-dim)", "—"
    dates = [s["session_date"] for s in sessions if s["session_date"]]
    if not dates:
        return "var(--text-dim)", "—"
    last = max(datetime.date.fromisoformat(d[:10]) for d in dates)
    delta = (datetime.date.today() - last).days
    if delta <= 0:
        label = "auj."
    elif delta == 1:
        label = "hier"
    else:
        label = f"il y a {delta}j"
    if delta <= 7:
        color = "var(--success)"
    elif delta <= 30:
        color = "var(--warning)"
    else:
        color = "var(--text-dim)"
    return color, label


@ui.page('/items')
@frame('Items')
def items_page(request: Request) -> None:
    if not data_store.is_loaded:
        ui.label("Chargement des données…").classes("text-slate-500")
        return

    ui.add_head_html(f"<style>{_CSS}</style>", shared=True)
    _mastery_styles()

    college_param = request.query_params.get("college") or None
    filt = {"mode": "college" if college_param else "all", "sort": "item",
            "college": college_param or "Tous", "page": 0}

    with ui.column().classes("it-wrap gap-0"):
        topbar = ui.element("div").classes("it-topbar")
        chips_row = ui.element("div").classes("it-chips-row")
        head = ui.element("div").classes("it-head")
        list_col = ui.column().classes("w-full gap-0")

    _meta: dict = {}

    def _compute() -> list[dict]:
        item_rows = build_item_rows(CatalogRepository(os.getenv("SYNAPSE_CATALOG_DB_PATH")))
        courses = [row["course"] for row in item_rows]

        sessions_map = get_sessions_by_course()
        postpone_map = get_postpone_counts()
        qcm_done_set = get_qcm_done_course_ids()
        lacune_counts = get_active_lacunes_count_by_course()
        lacune_ids = {cid for cid, n in lacune_counts.items() if n > 0}

        # Un seul passage du moteur : les tâches antérieures à la reprise sont
        # filtrées ici, et comptées pour pouvoir dire qu'elles sont masquées.
        # Ne pas passer history=/sessions_map=/postpone_map= : les fournir
        # active `explicit_data` dans le moteur et désactive son cache
        # journalier à chaque rendu — `/colleges` ne les passe pas non plus,
        # pour la même raison (N20).
        generated = review_service.generate_reviews(context="college", active_only=False)
        resume_date = get_study_resume_date(data_store.preferences)
        all_tasks = filter_active_review_tasks(generated, resume_date)
        _meta["resume_date"] = resume_date
        _meta["hidden_tasks"] = len(generated) - len(all_tasks)
        urgent_tasks = review_service.get_urgent_tasks(all_tasks)
        urgent_fiche_ids = {t.course_id for t in urgent_tasks}
        urgent_items = {
            _normalized_item_number(t.item_number)
            for t in urgent_tasks
            if _normalized_item_number(t.item_number)
        }
        next_by_item: dict[str, object] = {}
        for t in all_tasks:
            key = _normalized_item_number(t.item_number) or str(t.course_id)
            cur = next_by_item.get(key)
            if cur is None or (t.due_date, t.id) < (cur.due_date, cur.id):
                next_by_item[key] = t

        qcm_trends = local_store.get_qcm_latest_by_course()
        frequency_map = local_store.get_all_ednpro_item_frequencies()
        planned_ids = scheduled_course_ids()
        rows = []
        for item_row in item_rows:
            c = item_row["course"]
            fiche_ids = item_row["fiche_ids"]
            sessions = [session for fiche_id in fiche_ids for session in sessions_map.get(fiche_id, [])]
            try:
                mastery = get_item_mastery(c.item_number)
            except LookupError:
                # Catalog-only rows have no fiche in data_store. They are
                # still evaluated through the public mastery seam, never via
                # ReviewService's private per-fiche cache.
                mastery = get_course_mastery(
                    c,
                    context="college",
                    sessions=sessions,
                    total_postpone=sum(postpone_map.get(fid, 0) for fid in fiche_ids),
                    qcm_done_local=any(fid in qcm_done_set for fid in fiche_ids),
                )
            qcm_info = next(
                (qcm_trends.get(fiche_id, {}) for fiche_id in fiche_ids if fiche_id in qcm_trends),
                {},
            )
            rows.append({
                "course": c,
                "item_id": item_row["item_id"],
                "fiche_ids": fiche_ids,
                "missing_fiche": item_row["missing_fiche"],
                "mastery_score": mastery.score,
                "mastery_level": mastery.level,
                "evidence_count": mastery.evidence_count,
                "qcm_score": qcm_info.get("last_score"),
                "qcm_trend": qcm_info.get("trend"),
                "ednpro_frequency": frequency_map.get(
                    str(c.item_number or "").strip().removeprefix("ITEM ")
                ),
                "fiche_count": len(fiche_ids),
                "next_task": next_by_item.get(_normalized_item_number(c.item_number) or c.id),
                "planned": bool(
                    c.date_1ere_lecture
                    or planned_ids.intersection({str(c.id), *fiche_ids})
                ),
                "sessions": sessions,
                "overdue": _normalized_item_number(c.item_number) in urgent_items or bool(set(fiche_ids) & urgent_fiche_ids),
            })
        return _sort_item_rows(rows, filt["sort"])


    def _draw_topbar(total_count: int, visible_count: int) -> None:
        topbar.clear()
        with topbar:
            with ui.column().classes("gap-0"):
                ui.label("Items").classes("it-title")
                ui.label(
                    f"{visible_count} / {total_count} items affichés · cliquez pour ouvrir le détail"
                ).classes("it-subtitle")
                hidden = int(_meta.get("hidden_tasks") or 0)
                if hidden:
                    resume = _meta.get("resume_date")
                    ui.label(
                        f"Reprise le {resume:%d/%m} · {hidden} révision(s) antérieure(s) masquée(s)"
                    ).classes("it-subtitle it-resume")
            search = ui.element("div").classes("it-search")
            with search:
                ui.label("⌕")
                ui.label("Filtrer")
                ui.html("<kbd>Ctrl+Alt+P</kbd>")
            search.on("click", open_command_palette)

    def _select(mode: str) -> None:
        filt["mode"] = mode
        filt["page"] = 0
        if mode == "all":
            filt["college"] = "Tous"
        elif mode == "college" and college_param:
            filt["college"] = college_param
        visible_count = len(visible_item_rows(_all_rows["value"], filt))
        _draw_topbar(len(_all_rows["value"]), visible_count)
        _draw_chips()
        _draw_head()
        _draw_list(_all_rows["value"])

    def _draw_chips() -> None:
        chips_row.clear()
        with chips_row:
            with ui.element("div").classes("it-chips"):
                def _chip(label: str, mode: str) -> None:
                    active = filt["mode"] == mode
                    if mode == "college":
                        active = filt["college"] != "Tous"
                    el = ui.element("div").classes(
                        "it-chip active" if active else "it-chip")
                    with el:
                        ui.label(label)
                    el.on("click", lambda m=mode: _select(m))

                _chip("Tous", "all")
                if college_param:
                    _chip(college_param, "college")
                _chip("Fragile / critique", "fragile")
                _chip("En retard", "overdue")

            if filt["mode"] == "college" and college_param:
                ui.label(f"Filtré sur {college_param}").classes("it-filter-hint")

            ui.label("Trier par").classes("it-filter-hint")
            for label, mode in (("Item", "item"), ("Collège", "college"), ("Priorité annale", "priority")):
                el = ui.element("div").classes(
                    "it-chip active" if filt["sort"] == mode else "it-chip"
                )
                with el:
                    ui.label(label)
                el.on("click", lambda m=mode: _select_sort(m))

            # Alimenté par le catalogue, pas par les collèges portés par une
            # fiche : les items sans fiche (Humanités, Allergologie…) sont
            # rattachés au référentiel seul et étaient absents du menu (N06).
            _repo = CatalogRepository(os.getenv("SYNAPSE_CATALOG_DB_PATH"))
            colleges = (
                _repo.list_colleges_with_items() if _repo.is_populated()
                else sorted({name for c in data_store.cours for name in (c.college or [])})
            )
            ui.select(
                ["Tous", *colleges], value=filt["college"], label="Collège",
                on_change=lambda e: _select_college(e.value),
            ).props("outlined dense options-dense").classes("w-52")

    def _select_sort(mode: str) -> None:
        filt["sort"] = mode
        filt["page"] = 0
        _draw_chips()
        _draw_list(_all_rows["value"])

    def _select_college(name: str) -> None:
        filt["college"] = name or "Tous"
        filt["mode"] = "college" if name and name != "Tous" else "all"
        filt["page"] = 0
        visible_count = len(visible_item_rows(_all_rows["value"], filt))
        _draw_topbar(len(_all_rows["value"]), visible_count)
        _draw_chips()
        _draw_head()
        _draw_list(_all_rows["value"])

    def _draw_head() -> None:
        head.clear()
        show_college = filt["college"] == "Tous"
        with head:
            ui.label("").classes("it-h-ring")
            ui.label("ITEM").classes("it-h-id")
            ui.label("TITRE").classes("it-h-title")
            ui.label("Priorité annale").classes("it-h-frequency")
            ui.label("COLLÈGE" if show_college else "DERNIÈRE RÉVISION").classes("it-h-college")
            ui.label("FICHES").classes("it-h-type")
            ui.label("MAÎTRISE").classes("it-h-mastery")
            ui.label("PROCHAINE").classes("it-h-next")

    def _draw_row(r: dict) -> None:
        c = r["course"]
        missing_fiche = bool(r.get("missing_fiche"))
        show_college = filt["college"] == "Tous"
        row_classes = "it-row it-row-missing" if missing_fiche else "it-row"
        row = ui.element("div").classes(row_classes)
        if missing_fiche:
            # Pas de fiche dans le catalogue pour cet item : un clic menait à
            # une page « Item introuvable ». Créer une fiche est une tâche de
            # contenu, pas de code (Q5) — le clic informe plutôt que de
            # naviguer vers le vide.
            row.on(
                "click",
                lambda: ui.notify(
                    "Aucune fiche pour cet item : à créer dans le catalogue.",
                    type="warning",
                ),
            )
        else:
            target = f"/cours/{c.id}"
            if not show_college:
                target += f"?college={quote(filt['college'])}"
            row.on("click", lambda destination=target: ui.navigate.to(destination))
        with row:
            ui.label(_ring_glyph(r["mastery_score"])).classes("it-ring")
            ui.label(c.item_number or "—").classes("it-id")
            if missing_fiche:
                with ui.element("div").classes("it-title-cell flex items-center gap-1 flex-wrap"):
                    ui.label(c.title)
                    ui.label("Fiche manquante").classes("it-missing-badge")
            else:
                ui.label(c.title).classes("it-title-cell")
            with ui.element("div").classes("it-frequency"):
                ednpro_frequency_badge(r.get("ednpro_frequency"), compact=True)
            if show_college:
                college_names = list(c.college or [])
                # 50 items dépassent 60 caractères de libellés de collèges,
                # tronqués sans indication par le line-clamp CSS (N18) : le
                # premier collège plus un compteur, avec le reste au survol.
                if college_names:
                    label_text = college_names[0]
                    if len(college_names) > 1:
                        label_text += f" +{len(college_names) - 1}"
                    college_label = ui.label(label_text).classes("it-college it-college-link")
                    if len(college_names) > 1:
                        college_label.tooltip(" · ".join(college_names))
                    # La colonne était du texte mort ; elle ouvre maintenant
                    # `/colleges` sur la ligne du collège principal, dépliée
                    # (4.5). `stopPropagation` retient le clic : la ligne
                    # entière navigue déjà vers la fiche.
                    college_label.on(
                        "click",
                        lambda name=college_names[0]: ui.navigate.to(f"/colleges?open={quote(name)}"),
                        js_handler=_STOP_PROPAGATION_JS,
                    )
                else:
                    ui.label("—").classes("it-college")
            else:
                color, label = _last_review_info(r["sessions"])
                with ui.element("div").classes("it-last"):
                    ui.element("span").classes("it-last-dot").style(f"background:{color}")
                    ui.label(label)
            ui.label(str(r["fiche_count"])).classes("it-type").tooltip("Fiches liées à cet item")
            with ui.element("div").classes("it-mastery flex items-center gap-2"):
                mastery_indicator(
                    r["mastery_score"], r["mastery_level"],
                    evidence_count=r.get("evidence_count"),
                )
                q_score = r.get("qcm_score")
                if q_score is not None:
                    trend = r.get("qcm_trend") or ""
                    ui.label(f"{int(q_score)}% {trend}").classes("text-[11px] font-mono text-slate-500 font-semibold bg-slate-100 px-1.5 py-0.5 rounded")
            with ui.element("div").classes("it-next"):
                nt = r["next_task"]
                if nt is not None:
                    color, label = due_info(nt)
                    ui.element("span").classes("it-next-dot").style(f"background:{color}")
                    ui.label(label)
                elif r.get("planned"):
                    # Cycle ancré, aucune échéance ouverte : c'est un vrai
                    # « à jour », pas une absence de donnée.
                    ui.element("span").classes("it-next-dot").style("background:var(--success)")
                    ui.label("à jour")
                elif r.get("missing_fiche"):
                    ui.label("—").classes("it-unplanned")
                elif r.get("mastery_score") is not None:
                    # Un score existe déjà (déclaré ou mesuré) : l'item est
                    # connu, « Commencer » mentirait en prétendant une
                    # première lecture aujourd'hui. Même action
                    # (anchor_first_read pose le cycle J1→J30), juste un
                    # libellé honnête pour un item de consolidation.
                    plan = ui.element("div").classes("it-start")
                    with plan:
                        ui.label("Planifier")
                    plan.tooltip(
                        "Planifie une révision de consolidation J1→J30 pour cet "
                        "item déjà connu — ne compte pas comme une première lecture"
                    )
                    plan.on(
                        "click",
                        lambda cid=c.id, title=c.title: _start_item(cid, title),
                        js_handler=_STOP_PROPAGATION_JS,
                    )
                else:
                    start = ui.element("div").classes("it-start")
                    with start:
                        ui.label("Commencer")
                    start.tooltip(
                        "Pose la première lecture aujourd'hui et planifie J1, J3, J7, J14 et J30"
                    )
                    start.on(
                        "click",
                        lambda cid=c.id, title=c.title: _start_item(cid, title),
                        js_handler=_STOP_PROPAGATION_JS,
                    )

    def _start_item(course_id: str, title: str) -> None:
        """Ancre le cycle J1→J30 sans quitter la liste."""
        try:
            anchor_first_read(course_id)
        except Exception as exc:
            ui.notify(f"Planification impossible : {exc}", type="negative")
            return
        ui.notify(f"Cycle planifié · {title}", type="positive")
        _render()

    def _load_more() -> None:
        filt["page"] += 1
        _draw_list(_all_rows["value"])

    def _draw_list(rows: list[dict]) -> None:
        list_col.clear()
        visible = visible_item_rows(rows, filt)
        limit = (filt["page"] + 1) * _PAGE_SIZE
        rendered = visible[:limit]
        with list_col:
            if not visible:
                with ui.element("div").classes("it-empty"):
                    ui.label("Aucun item pour ce filtrage.")
                return
            if filt.get("sort") == "college":
                for college, group in group_item_rows(rendered, filt.get("college")):
                    ui.label(college).classes("it-group-label")
                    for r in group:
                        _draw_row(r)
            else:
                for r in rendered:
                    _draw_row(r)
            if len(rendered) < len(visible):
                ui.button(
                    f"Afficher {min(_PAGE_SIZE, len(visible) - len(rendered))} items supplémentaires",
                    on_click=_load_more,
                ).props("flat no-caps").classes("mx-auto my-3")

    _all_rows = {"value": []}

    def _render() -> None:
        _all_rows["value"] = _compute()
        visible_count = len(visible_item_rows(_all_rows["value"], filt))
        _draw_topbar(len(_all_rows["value"]), visible_count)
        _draw_chips()
        _draw_head()
        _draw_list(_all_rows["value"])

    _render()
