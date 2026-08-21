"""Le bouton « Reporter » du panneau contexte doit reporter, pas ouvrir le focus.

Retour d'usage : dans la vue Aujourd'hui, `on_postpone` était câblé sur
`_open_focus`, exactement comme `on_focus` juste en dessous. Le vrai callback
`_on_postpone` existait et écrivait bien en base, il n'était simplement branché
nulle part.
"""
from pathlib import Path

from frontend.components.context_panel import POSTPONE_CHOICES

_TODAY = Path("frontend/pages/dashboard/_cockpit_today.py")
_PANEL = Path("frontend/components/context_panel.py")


def test_today_view_wires_postpone_to_the_postpone_callback():
    source = _TODAY.read_text(encoding="utf-8")

    assert "on_postpone=lambda t: _open_focus(t)" not in source
    assert "_on_postpone(t, days=d)" in source


def test_postpone_offers_the_same_delays_as_the_hero_menu():
    assert [days for days, _ in POSTPONE_CHOICES] == [1, 3, 7]

    hero = Path("frontend/pages/dashboard/_hero.py").read_text(encoding="utf-8")
    for _, label in POSTPONE_CHOICES:
        assert label in hero


def test_reading_cycle_tasks_get_the_manual_delay_menu():
    source = _PANEL.read_text(encoding="utf-8")

    assert "_post.on(\"click\", _post_menu.open)" in source
    assert "on_postpone(t, d)" in source


def test_consolidation_tasks_are_replanned_by_the_algorithm():
    """Pas de menu pour un item à consolider : un clic, et la date vient de
    la maîtrise. `None` est la convention qui demande ce calcul."""
    source = _PANEL.read_text(encoding="utf-8")

    assert "is_algorithmic_postpone(task)" in source
    assert "on_postpone(t, None)" in source
    assert "not _algorithmic" in source

    today = _TODAY.read_text(encoding="utf-8")
    assert "algorithmic = days is None" in today
    assert "days = postpone_days_for_task(task)" in today


def test_postpone_menu_is_anchored_on_its_button():
    """ui.menu s'ancre sur son parent DOM : sans position:relative sur .cp-btn
    le menu se place par rapport au panneau entier."""
    source = _PANEL.read_text(encoding="utf-8")

    css_rule = source[source.index(".cp-btn {"):source.index(".cp-btn:hover")]
    assert "position:relative" in css_rule
