from datetime import date, timedelta
from types import SimpleNamespace

from frontend.pages.colleges_cockpit import _college_item_rows, _pilotage_summary


def _course(course_id, number, title, started=True):
    return SimpleNamespace(
        id=course_id,
        item_number=number,
        title=title,
        date_1ere_lecture=date.today() if started else None,
    )


def _task(course_id, due_date):
    return SimpleNamespace(course_id=course_id, due_date=due_date)


def test_college_item_rows_expose_item_signals_without_extra_queries():
    courses = [_course("c1", "12", "Fragile"), _course("c2", "13", "A lire", started=False)]
    tasks = [_task("c1", date.today() - timedelta(days=1))]

    rows = _college_item_rows(
        courses,
        tasks,
        mastery_by_course={"c1": (24, "critique")},
        urgent_ids={"c1"},
        qcm_map={"c1": {"last_score": 42}},
    )

    assert [row["course"].id for row in rows] == ["c1", "c2"]
    assert rows[0]["level"] == "critique"
    assert rows[0]["urgent"] is True
    assert rows[0]["next_task"] is tasks[0]
    assert rows[0]["qcm_score"] == 42
    assert rows[1]["status_key"] == "à préparer"
    assert rows[1]["next_task"] is None
    assert rows[1]["qcm_score"] is None


def test_college_item_grid_uses_status_columns_and_readable_empty_state():
    source = open("frontend/pages/colleges_cockpit.py", encoding="utf-8").read()

    for label in ("Lecture", "Maîtrise", "Statut", "Retard", "Prochaine", "QCM"):
        assert f'"{label}"' in source
    assert 'GridColumn("fragile"' not in source
    assert ".cg-item-status.non-commence" in source
    assert 'ui.label("—").classes("cg-item-cell cg-item-muted cg-item-action")' in source
    assert "aucune révision prévue" not in source


def test_college_item_grid_uses_fixed_action_track():
    source = open("frontend/pages/colleges_cockpit.py", encoding="utf-8").read()

    assert 'GridColumn("action", "", "88px")' in source
    assert "grid-template-columns:minmax(180px,2fr) 76px 76px 120px 86px 100px 56px 104px 88px;" in source
    assert 'GridColumn("ednpro", "Priorité annale", "104px")' in source
    assert ".cg-item-head > *, .cg-item > * { min-width:0; box-sizing:border-box; }" in source


def test_college_items_container_plays_an_entrance_animation_on_open():
    """La fermeture d'un collège est instantanée par construction (le nœud est
    détruit, pas transitionné) ; seule l'ouverture peut être animée puisque le
    conteneur est toujours neuf à ce moment-là."""
    from pathlib import Path

    source = Path("frontend/pages/colleges_cockpit.py").read_text(encoding="utf-8")

    assert "@keyframes cgItemsEnter" in source
    assert ".cg-items-enter { animation: cgItemsEnter var(--duration-base) var(--ease-standard) both; }" in source
    assert 'ui.element("div").classes("cg-items cg-items-enter")' in source


def test_college_summary_uses_shared_grid_tracks():
    source = open("frontend/pages/colleges_cockpit.py", encoding="utf-8").read()

    assert ".cg-head, .cg-row { display:grid;" in source
    assert "grid-template-columns:minmax(200px,2fr) minmax(120px,1fr) 42px 96px 90px 90px 52px;" in source
    assert ".cg-head > *, .cg-row > * { min-width:0; box-sizing:border-box; }" in source


def test_college_item_rows_stay_inside_the_shared_grid_container():
    source = open("frontend/pages/colleges_cockpit.py", encoding="utf-8").read()

    assert "for item in item_rows:" in source
    assert source.index("for item in item_rows:") > source.index('classes("cg-items-grid")')
    assert 'item["status_text"]' in source


def test_college_pilotage_labels_reading_progress_separately_from_mastery():
    source = open("frontend/pages/colleges_cockpit.py", encoding="utf-8").read()
    assert "Avancement de lecture" in source
    assert "Répartition des statuts" in source
    assert "Maîtrise moyenne" not in source
    assert "maîtrise moyenne" in source
    assert "rétention" in source


def test_college_pilotage_status_distribution_covers_emitted_statuses():
    from frontend.pages.colleges_cockpit import status_distribution_rows

    rows = status_distribution_rows()
    keys = [key for key, _label, _color in rows]

    assert "critique" in keys
    assert "maîtrisé" in keys
    assert all(label and color for _key, label, color in rows)


def test_college_actions_stop_row_click_propagation():
    source = open("frontend/pages/colleges_cockpit.py", encoding="utf-8").read()

    assert "event.stopPropagation()" in source


def test_college_pdf_kpi_counts_fiches_not_colleges():
    source = open("frontend/pages/colleges_cockpit.py", encoding="utf-8").read()

    assert '"fiches sans PDF"' in source
    assert "count_no_pdf(courses)" in source


def test_college_reuses_computed_rows_for_filters_and_expansion():
    source = open("frontend/pages/colleges_cockpit.py", encoding="utf-8").read()

    assert "if recompute or _computed_rows is None" in source
    assert "_draw_list(_computed_rows or [])" in source
    assert "_render(recompute=True)" in source


def test_college_header_names_learning_avancement_explicitly():
    source = open("frontend/pages/colleges_cockpit.py", encoding="utf-8").read()

    assert "Avancement par matière" in source
    assert "progression par matière" not in source


def test_college_item_rows_separate_reading_from_mastery():
    """Un item lu mais sans preuve encore recueillie est « non évalué » — un
    état neutre, distinct d'une alerte (Q4 bis) — et non plus une clé de
    statut propre à `_course_semantics`. Le score reste calculé (il rend
    l'item planifiable par le moteur de révisions) ; seul le niveau affiché
    change."""
    courses = [_course("c1", "12", "Lu sans preuve")]
    rows = _college_item_rows(courses, [], mastery_by_course={"c1": (50, "non évalué")})

    assert rows[0]["lecture_label"] == "Lu"
    assert rows[0]["reading_pct"] == 100
    assert rows[0]["mastery_score"] == 50
    assert rows[0]["status_text"] == "Non évalué"


def test_an_item_started_upstream_is_read_whatever_the_college_row():
    """La validation d'un collège rendait l'item « lu » dans ce collège et
    « À lire » dans ses autres collèges. La réponse est calculée une fois, en
    amont (`is_item_started`), et transmise telle quelle à chaque ligne. Le
    statut, lui, vient toujours de `level` — ici « à lire » parce que la
    fiche elle-même n'a pas de date de première lecture, même si l'item est
    déjà commencé au sens de l'item (started_ids)."""
    courses = [_course("c1", "12", "Non lu", started=False)]

    rows = _college_item_rows(
        courses, [], mastery_by_course={"c1": (None, "à lire")}, started_ids={"c1"}
    )

    assert rows[0]["lecture_label"] == "Lu"
    assert rows[0]["reading_pct"] == 100
    assert rows[0]["mastery_score"] is None
    assert rows[0]["status_key"] == "à lire"


def test_unread_course_is_not_presented_as_mastered():
    courses = [_course("c1", "12", "A lire", started=False)]
    rows = _college_item_rows(courses, [], mastery_by_course={"c1": (None, "à lire")})

    assert rows[0]["lecture_label"] == "Non lu"
    assert rows[0]["mastery_score"] is None
    assert rows[0]["status_text"] == "À lire"
    assert rows[0]["status_key"] == "à lire"


def test_colleges_page_can_arrive_pre_expanded_on_one_college():
    """`/colleges?open=<nom>` (déclenché par le clic sur la colonne COLLÈGE de
    `/items`, 4.5) doit déplier directement cette ligne."""
    source = open("frontend/pages/colleges_cockpit.py", encoding="utf-8").read()

    assert "def render_colleges_cockpit(open_college: str | None = None) -> None:" in source
    assert "expanded: set[str] = {open_college} if open_college else set()" in source


def test_collapsed_college_row_has_a_single_sub_label():
    """La ligne repliée empilait trois sous-libellés (lecture, statut,
    preuves/consolidation) — 44 lignes à l'écran en même temps rendaient ça
    dense sans information supplémentaire utile au premier coup d'œil
    (N18/4.4). Le détail de validation ne s'affiche plus qu'au dépliage."""
    source = open("frontend/pages/colleges_cockpit.py", encoding="utf-8").read()

    row_start = source.index('def _draw_row(r: dict) -> None:')
    row_end = source.index('with ui.element("div").classes("cg-bar-cell"):', row_start)
    collapsed_block = source[row_start:row_end]

    assert collapsed_block.count('.classes("cg-name-sub")') == 1
    assert "cg-validation-detail" in source


def test_college_deplie_view_does_not_navigate_for_a_missing_fiche():
    source = open("frontend/pages/colleges_cockpit.py", encoding="utf-8").read()

    assert "missing_fiche_ids=_meta.get(\"missing_fiche_ids\")" in source
    assert "Aucune fiche pour cet item" in source


def test_college_item_rows_flag_items_without_a_fiche():
    """Un item sans fiche (8, 10) menait à `/cours/{id}` → « Item introuvable »
    depuis la vue dépliée d'un collège aussi, pas seulement `/items` (N07)."""
    courses = [_course("item:8", "8", "Les discriminations")]

    rows = _college_item_rows(courses, [], missing_fiche_ids={"item:8"})

    assert rows[0]["missing_fiche"] is True


def test_college_item_rows_default_to_not_missing_a_fiche():
    courses = [_course("c1", "12", "Fragile")]

    rows = _college_item_rows(courses, [])

    assert rows[0]["missing_fiche"] is False


def test_pilotage_summary_exposes_mastery_provenance():
    """96 % des scores fragiles/critiques viennent d'une déclaration qui
    décroît avec le temps, pas d'une mesure (N04) : la moyenne agrégée doit
    dire d'où elle vient, pas seulement chaque ligne (N16)."""
    rows = [{
        "total": 2, "started": 2, "retard": 0, "fragile": 0, "no_pdf": 0,
        "mastery_by_course": {"c1": (80, "maîtrisé", 0), "c2": (60, "à consolider", 3)},
        "retention_by_course": {}, "status_counts": {},
    }]

    summary = _pilotage_summary(rows)

    assert summary["mastery_declared"] == 1
    assert summary["mastery_measured"] == 1


def test_pilotage_summary_separates_mastery_and_retention():
    rows = [{
        "total": 2,
        "started": 2,
        "retard": 0,
        "fragile": 0,
        "no_pdf": 0,
        "mastery_by_course": {"c1": (80, "solide"), "c2": (None, None)},
        "retention_by_course": {"c1": 65, "c2": None},
        "status_counts": {"solide": 1, "lu_sans_preuve": 1},
        "courses": [],
    }]

    summary = _pilotage_summary(rows)

    assert summary["pct"] == 1
    assert summary["mastery_avg"] == 80
    assert summary["retention_avg"] == 65
    assert summary["status_counts"]["solide"] == 1
    assert summary["status_counts"]["lu_sans_preuve"] == 1
