import asyncio

from frontend.components.session_feedback import submit_session_feedback


def test_submit_session_feedback_forwards_full_wizard_result():
    received = {}

    async def on_done(task, card, **feedback):
        received["task"] = task
        received["card"] = card
        received.update(feedback)

    task = object()
    card = object()
    asyncio.run(
        submit_session_feedback(
            on_done,
            task,
            card,
            activity_types=["révision", "qcm"],
            duration_minutes=25,
            confidence=2,
            difficulty="difficile",
            qcm_result="raté",
            weak_category="raisonnement",
            weak_detail="Oubli du diagnostic différentiel",
        )
    )

    assert received == {
        "task": task,
        "card": card,
        "activity_types": ["révision", "qcm"],
        "duration_minutes": 25,
        "confidence": 2,
        "difficulty": "difficile",
        "qcm_result": "raté",
        "weak_category": "raisonnement",
        "weak_detail": "Oubli du diagnostic différentiel",
    }
