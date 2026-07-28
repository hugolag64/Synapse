from types import SimpleNamespace

from frontend import cockpit_shell


def test_revision_badge_uses_overdue_task_count(monkeypatch):
    class ReviewService:
        def generate_reviews(self, context, history):
            assert context == "college"
            return [SimpleNamespace(id="a"), SimpleNamespace(id="b"), SimpleNamespace(id="c")]

        def get_urgent_tasks(self, tasks):
            return tasks[:2]

    monkeypatch.setattr("backend.core.reviews.local_store.get_all_history", lambda: {})
    monkeypatch.setattr(cockpit_shell, "_revision_badge", cockpit_shell._revision_badge)
    monkeypatch.setattr("backend.core.reviews.service.review_service", ReviewService())

    assert cockpit_shell._revision_badge() == ("count", "2")
