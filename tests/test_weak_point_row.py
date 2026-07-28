from frontend.components.weak_point_row import status_line, dot_color, status_text_color


def _row(status="active", severity=2, recurrence_count=0, resolved_at=None):
    return {
        "status": status,
        "severity": severity,
        "recurrence_count": recurrence_count,
        "resolved_at": resolved_at,
    }


def test_status_line_active_simple():
    assert status_line(_row(status="active", severity=2)) == "Active"


def test_status_line_critique_prioritaire_sur_statut_brut():
    # sévérité >= 4 et pas résolue => "critique" remplace le statut brut
    assert status_line(_row(status="active", severity=4)) == "Critique"


def test_status_line_critique_et_recurrente():
    assert status_line(_row(status="récurrente", severity=5, recurrence_count=3)) == "Critique · récurrente 3×"


def test_status_line_recurrente_non_critique():
    assert status_line(_row(status="récurrente", severity=2, recurrence_count=3)) == "Récurrente 3×"


def test_status_line_a_revoir_avec_recurrence():
    assert status_line(_row(status="à revoir", severity=2, recurrence_count=2)) == "À revoir · 2×"


def test_status_line_resolue_avec_date():
    line = status_line(_row(status="résolue", severity=1, resolved_at="2026-06-02"))
    assert line == "Résolue · 02 juin"


def test_status_line_resolue_sans_date():
    assert status_line(_row(status="résolue", severity=1)) == "Résolue"


def test_dot_color_critique_rouge():
    assert dot_color(_row(status="active", severity=5)) == "var(--danger)"


def test_dot_color_active_ambre():
    assert dot_color(_row(status="active", severity=2)) == "var(--warning)"


def test_dot_color_resolue_vert():
    assert dot_color(_row(status="résolue", severity=5)) == "var(--success)"


def test_status_text_color_neutre_hors_urgence():
    assert status_text_color(_row(status="active", severity=2)) == "var(--text-muted)"
    assert status_text_color(_row(status="récurrente", severity=2, recurrence_count=3)) == "var(--text-muted)"
    assert status_text_color(_row(status="résolue", severity=5)) == "var(--text-muted)"


def test_status_text_color_urgence_coloree():
    assert status_text_color(_row(status="active", severity=4)) == "var(--danger)"
    assert status_text_color(_row(status="à revoir", severity=2)) == "var(--warning)"
