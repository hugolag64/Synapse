from backend.core.uness.item_migration import (
    build_question_item_links,
    accepted_item_numbers,
)


def test_rejects_unconfident_or_overbroad_classification():
    assert accepted_item_numbers(["221"], confident=True) == ("221",)
    assert accepted_item_numbers(["221", "222"], confident=True) == ("221", "222")
    assert accepted_item_numbers(["221", "222", "223"], confident=True) == ()
    assert accepted_item_numbers(["221"], confident=False) == ()


def test_build_question_item_links_keeps_only_accepted_question_links():
    rows = build_question_item_links(
        {
            10: (["221"], True),
            11: (["222", "223"], True),
            12: (["224", "225", "226"], True),
            13: (["227"], False),
        }
    )

    assert rows == [
        (10, "221", 0.8, "uness_question_migration", "2026-08-03-question-v1"),
        (11, "222", 0.8, "uness_question_migration", "2026-08-03-question-v1"),
        (11, "223", 0.8, "uness_question_migration", "2026-08-03-question-v1"),
    ]
