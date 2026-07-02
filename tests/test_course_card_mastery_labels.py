"""Tests pour la couverture des labels de maîtrise dans CourseCard."""
from backend.core.reviews.mastery import PROGRESSION_COLORS


def test_all_progression_colors_have_a_label():
    # Import here to avoid triggering NiceGUI page registration at module load
    # for unrelated test collection — course_card.py only defines a component
    # function, so a plain import is safe and mirrors how it's used at runtime.
    import ast
    import pathlib

    source = pathlib.Path("frontend/components/course_card.py").read_text(encoding="utf-8")
    tree = ast.parse(source)

    mastery_labels_dict = None
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "_mastery_labels":
                    mastery_labels_dict = node.value
    assert mastery_labels_dict is not None, "_mastery_labels dict not found in course_card.py"

    label_keys = {
        k.value for k in mastery_labels_dict.keys
        if isinstance(k, ast.Constant)
    }
    required_colors = set(PROGRESSION_COLORS.values())
    missing = required_colors - label_keys
    assert not missing, f"_mastery_labels is missing entries for: {missing}"
