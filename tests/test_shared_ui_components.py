from frontend.components.data_grid import DataGrid, GridColumn
from frontend.components.status_badge import status_class, status_label
from frontend.design_tokens import _TOKENS_CSS


def test_data_grid_exposes_one_column_template_for_header_and_rows():
    grid = DataGrid(
        columns=(
            GridColumn("item", "Item", "minmax(180px,2fr)"),
            GridColumn("progress", "Progression", "76px"),
            GridColumn("status", "Statut", "88px"),
        )
    )

    assert grid.column_template == "minmax(180px,2fr) 76px 88px"
    assert grid.labels == ("Item", "Progression", "Statut")


def test_status_badge_has_stable_label_and_css_class():
    assert status_label("non_commence") == "Non commencé"
    assert status_class("non_commence") == "non-commence"


def test_shared_tokens_define_content_width_and_panel_density():
    assert "--content-readable: 1100px" in _TOKENS_CSS
    assert "--content-full: 100%" in _TOKENS_CSS
    assert "--panel-padding: 20px" in _TOKENS_CSS
    assert status_label("critique") == "Critique"
