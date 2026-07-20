"""Tests unitaires — recommendation_service (charge journalière + plafond)."""
import datetime
from backend.core.reviews.models import ReviewTask


def _task(course_id, review_type="J7", days_overdue=0, due_date=None):
    due = due_date or datetime.date.today()
    return ReviewTask(
        id=f"{course_id}_{review_type}",
        course_id=course_id,
        course_title=course_id,
        theoretical_due_date=due,
        due_date=due,
        review_type=review_type,
        days_overdue=days_overdue,
    )


# ── apply_daily_budget ───────────────────────────────────────────────────────

def test_apply_daily_budget_no_op_quand_budget_zero():
    from backend.core.reviews.recommendation_service import apply_daily_budget

    urgent = [_task("u1", days_overdue=1)]
    today = [_task("t1"), _task("t2")]
    kept_u, kept_t, overflow = apply_daily_budget(urgent, today, budget_min=0)

    assert kept_u == urgent
    assert kept_t == today
    assert overflow == 0


def test_apply_daily_budget_liste_vide():
    from backend.core.reviews.recommendation_service import apply_daily_budget

    kept_u, kept_t, overflow = apply_daily_budget([], [], budget_min=60)
    assert kept_u == []
    assert kept_t == []
    assert overflow == 0


def test_apply_daily_budget_budget_suffisant_pour_tout():
    from backend.core.reviews.recommendation_service import apply_daily_budget

    # 1 urgent (20 min, cf. get_next_action: overdue>0 non-critique) +
    # 1 today (30 min, cf. get_next_action: pas de QCM fait)
    urgent = [_task("u1", days_overdue=1)]
    today = [_task("t1")]
    kept_u, kept_t, overflow = apply_daily_budget(urgent, today, budget_min=100)

    assert kept_u == urgent
    assert kept_t == today
    assert overflow == 0


def test_apply_daily_budget_coupe_dans_today_tasks():
    from backend.core.reviews.recommendation_service import apply_daily_budget

    # 1 urgent = 20 min. 3 today = 30 min chacune.
    # Budget 50 -> urgent (20) + 1 today (30) = 50, le reste des today est coupé.
    urgent = [_task("u1", days_overdue=1)]
    today = [_task("t1"), _task("t2"), _task("t3")]
    kept_u, kept_t, overflow = apply_daily_budget(urgent, today, budget_min=50)

    assert [t.course_id for t in kept_u] == ["u1"]
    assert [t.course_id for t in kept_t] == ["t1"]
    assert overflow == 2


def test_apply_daily_budget_coupe_dans_urgent_tasks():
    from backend.core.reviews.recommendation_service import apply_daily_budget

    # 3 urgent = 20 min chacune. Budget 30 -> seule la 1ère urgent (20 min) tient,
    # aucune today n'est retenue.
    urgent = [_task("u1", days_overdue=1), _task("u2", days_overdue=2), _task("u3", days_overdue=3)]
    today = [_task("t1")]
    kept_u, kept_t, overflow = apply_daily_budget(urgent, today, budget_min=30)

    assert [t.course_id for t in kept_u] == ["u1"]
    assert kept_t == []
    assert overflow == 3  # 2 urgent + 1 today


def test_apply_daily_budget_conserve_lordre_recu_sans_retrier():
    from backend.core.reviews.recommendation_service import apply_daily_budget

    # today_tasks volontairement dans un ordre non trié par priority_score :
    # apply_daily_budget ne doit PAS le retrier, juste couper à la fin.
    today = [_task("low_prio"), _task("high_prio")]
    kept_u, kept_t, overflow = apply_daily_budget([], today, budget_min=30)

    assert [t.course_id for t in kept_t] == ["low_prio"]
    assert overflow == 1


# ── compute_daily_load : seuil configurable ─────────────────────────────────

def test_compute_daily_load_seuil_par_defaut_120():
    from backend.core.reviews.recommendation_service import compute_daily_load

    # 5 today tasks * 30 min = 150 min > 120
    today = [_task(f"t{i}") for i in range(5)]
    load = compute_daily_load([], today)
    assert load["total_min"] == 150
    assert load["is_heavy"] is True


def test_compute_daily_load_seuil_personnalise():
    from backend.core.reviews.recommendation_service import compute_daily_load

    # 3 today tasks * 30 min = 90 min : pas heavy avec seuil par défaut 120,
    # mais heavy avec un seuil personnalisé à 60.
    today = [_task(f"t{i}") for i in range(3)]
    load_default = compute_daily_load([], today)
    assert load_default["is_heavy"] is False

    load_custom = compute_daily_load([], today, heavy_threshold_min=60)
    assert load_custom["is_heavy"] is True
    assert load_custom["total_min"] == 90  # total_min ne dépend pas du seuil
