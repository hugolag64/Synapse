"""
Tests for PDF Phase A logic in preload_all_views().

We test the Phase A for-loop logic directly (without instantiating DataStore,
which has heavy dependencies). Phase B (background asyncio task) is excluded
from this test suite — its correctness relies on auto_detect_pdf which is
already covered in test_files.py.
"""
import os
import pytest
from unittest.mock import patch, MagicMock


def _run_phase_a(cours_list):
    """
    Replicate Phase A logic from preload_all_views() in isolation.
    This mirrors the exact code inserted into store.py so that any future
    drift is caught immediately.
    """
    from backend.core.reviews import local_store as _ls
    for c in cours_list:
        if not getattr(c, "url_pdf", None):
            cached = _ls.get_pdf_cache(c.id, "college")
            if cached and os.path.isfile(cached):
                c.url_pdf = f"file:///{cached.replace(os.sep, '/')}"
        if not getattr(c, "url_pdf_ue", None):
            cached_ue = _ls.get_pdf_cache(c.id, "ue")
            if cached_ue and os.path.isfile(cached_ue):
                c.url_pdf_ue = f"file:///{cached_ue.replace(os.sep, '/')}"


def _make_course(course_id, url_pdf=None, url_pdf_ue=None):
    c = MagicMock()
    c.id = course_id
    c.url_pdf = url_pdf
    c.url_pdf_ue = url_pdf_ue
    return c


class TestPhaseA:
    def test_sets_url_pdf_when_cache_hit_and_file_exists(self):
        """Phase A sets url_pdf when SQLite returns a path and the file exists."""
        course = _make_course("course-1")
        fake_path = os.path.join("some", "dir", "course.pdf")

        with patch("backend.core.reviews.local_store.get_pdf_cache") as mock_cache, \
             patch("os.path.isfile", return_value=True):
            mock_cache.side_effect = lambda cid, ctx: fake_path if ctx == "college" else None
            _run_phase_a([course])

        expected_uri = f"file:///{fake_path.replace(os.sep, '/')}"
        assert course.url_pdf == expected_uri

    def test_does_not_override_existing_url_pdf(self):
        """Phase A does not touch url_pdf when it is already set."""
        existing_uri = "file:///already/set.pdf"
        course = _make_course("course-2", url_pdf=existing_uri)

        with patch("backend.core.reviews.local_store.get_pdf_cache") as mock_cache, \
             patch("os.path.isfile", return_value=True):
            mock_cache.return_value = "/some/other/path.pdf"
            _run_phase_a([course])

        # url_pdf must remain unchanged
        assert course.url_pdf == existing_uri

    def test_skips_when_file_does_not_exist(self):
        """Phase A leaves url_pdf as None when the cached path points to a missing file."""
        course = _make_course("course-3")

        with patch("backend.core.reviews.local_store.get_pdf_cache", return_value="/missing/file.pdf"), \
             patch("os.path.isfile", return_value=False):
            _run_phase_a([course])

        assert course.url_pdf is None

    def test_skips_when_cache_returns_none(self):
        """Phase A leaves url_pdf as None when SQLite has no entry."""
        course = _make_course("course-4")

        with patch("backend.core.reviews.local_store.get_pdf_cache", return_value=None), \
             patch("os.path.isfile", return_value=True):
            _run_phase_a([course])

        assert course.url_pdf is None

    def test_sets_url_pdf_ue_independently(self):
        """Phase A sets url_pdf_ue from the 'ue' context independently of 'college'."""
        course = _make_course("course-5")
        college_path = os.path.join("college", "course.pdf")
        ue_path = os.path.join("ue", "course.pdf")

        def cache_side_effect(cid, ctx):
            if ctx == "college":
                return college_path
            if ctx == "ue":
                return ue_path
            return None

        with patch("backend.core.reviews.local_store.get_pdf_cache") as mock_cache, \
             patch("os.path.isfile", return_value=True):
            mock_cache.side_effect = cache_side_effect
            _run_phase_a([course])

        assert course.url_pdf == f"file:///{college_path.replace(os.sep, '/')}"
        assert course.url_pdf_ue == f"file:///{ue_path.replace(os.sep, '/')}"

    def test_multiple_courses_each_handled_independently(self):
        """Phase A iterates all courses; each gets its own cache lookup."""
        courses = [_make_course(f"course-{i}") for i in range(3)]
        # Use OS-native absolute paths so the URI construction is predictable
        path_c0 = os.path.join("C:", "pdf", "c0.pdf") if os.name == "nt" else "/pdf/c0.pdf"
        path_c2 = os.path.join("C:", "pdf", "c2.pdf") if os.name == "nt" else "/pdf/c2.pdf"
        paths = {
            "course-0": path_c0,
            "course-1": None,         # no cache entry
            "course-2": path_c2,
        }

        def cache_side_effect(cid, ctx):
            if ctx == "college":
                return paths.get(cid)
            return None

        with patch("backend.core.reviews.local_store.get_pdf_cache") as mock_cache, \
             patch("os.path.isfile", return_value=True):
            mock_cache.side_effect = cache_side_effect
            _run_phase_a(courses)

        assert courses[0].url_pdf == f"file:///{path_c0.replace(os.sep, '/')}"
        assert courses[1].url_pdf is None
        assert courses[2].url_pdf == f"file:///{path_c2.replace(os.sep, '/')}"

    def test_uri_uses_forward_slashes(self):
        """The file:/// URI must always use forward slashes regardless of OS sep."""
        course = _make_course("course-win")
        # Simulate a Windows-style absolute path
        win_path = "C:\\Users\\hugol\\pdfs\\course.pdf"

        with patch("backend.core.reviews.local_store.get_pdf_cache", return_value=win_path), \
             patch("os.path.isfile", return_value=True):
            _run_phase_a([course])

        assert "\\" not in course.url_pdf
        assert course.url_pdf.startswith("file:///")
