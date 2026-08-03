def test_flash_zero_card_model_exposes_morning_task_and_action():
    from frontend.components.flash_zero_cockpit import flash_zero_card_model

    model = flash_zero_card_model({"course_title": "Flash-Zero du matin", "duration_minutes": 5}, completed=False)

    assert model == {
        "title": "Flash-Zero du matin",
        "duration": "5 min",
        "status": "À faire",
        "action": "Lancer",
    }


def test_flash_zero_card_model_marks_completed_task():
    from frontend.components.flash_zero_cockpit import flash_zero_card_model

    assert flash_zero_card_model({"duration_minutes": 5}, completed=True)["status"] == "Fait"
