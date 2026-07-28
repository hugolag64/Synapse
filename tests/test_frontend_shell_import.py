def test_frontend_is_a_regular_package_with_importable_shell():
    import importlib.util
    import frontend

    assert frontend.__file__
    assert importlib.util.find_spec("frontend.cockpit_shell") is not None
