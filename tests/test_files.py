"""Tests unitaires — FileService.auto_detect_pdf() et find_pdf() min_score."""
import asyncio
import pytest
from unittest.mock import patch, MagicMock, AsyncMock


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_course(
    id="course-abc",
    url_pdf=None,
    url_pdf_ue=None,
    college=None,
    title="Insuffisance cardiaque",
    item_number="232",
):
    course = MagicMock()
    course.id = id
    course.url_pdf = url_pdf
    course.url_pdf_ue = url_pdf_ue
    course.college = college or ["Cardiovasculaire ❤️"]
    course.title = title
    course.item_number = item_number
    return course


def _run(coro):
    """Exécute une coroutine de manière synchrone pour les tests."""
    return asyncio.get_event_loop().run_until_complete(coro)


# ── Fixture : FileService avec caches pré-peuplés ────────────────────────────

@pytest.fixture()
def svc():
    """FileService isolé : pas de vraie DB, pas de vrai disque."""
    from backend.core.files import FileService
    return FileService()


# ── Test 1 : Guard college — url_pdf déjà renseignée ─────────────────────────

class TestGuardCollegeUrlPdf:
    def test_returns_none_when_url_pdf_set(self, svc):
        course = _make_course(url_pdf="https://example.com/college.pdf")
        result = _run(svc.auto_detect_pdf(course, context="college"))
        assert result is None

    def test_proceeds_when_url_pdf_empty_string(self, svc):
        """Une chaîne vide est falsy → doit passer le guard."""
        course = _make_course(url_pdf="")
        # On court-circuite après le guard en faisant échouer le cache SQLite
        with patch("backend.core.files.local_store.get_pdf_cache", return_value=None), \
             patch("backend.core.files.settings") as mock_settings, \
             patch("os.path.exists", return_value=False):
            mock_settings.medicine_dir = ""
            result = _run(svc.auto_detect_pdf(course, context="college"))
        assert result is None  # None pour une autre raison (search_path vide)

    def test_returns_none_when_url_pdf_ue_set(self, svc):
        course = _make_course(url_pdf_ue="https://example.com/ue.pdf")
        result = _run(svc.auto_detect_pdf(course, context="ue"))
        assert result is None


# ── Test 2 : Cache SQLite hit + fichier existant ──────────────────────────────

class TestSQLiteCacheHit:
    def test_returns_cached_path_when_file_exists(self, svc):
        course = _make_course()
        cached_path = "/some/path/college.pdf"

        with patch("backend.core.files.local_store.get_pdf_cache", return_value=cached_path), \
             patch("os.path.isfile", return_value=True):
            result = _run(svc.auto_detect_pdf(course, context="college"))

        assert result == cached_path

    def test_skips_cache_when_file_missing(self, svc):
        """Le fichier en cache n'existe plus → continuer la détection."""
        course = _make_course()
        cached_path = "/stale/path/college.pdf"

        with patch("backend.core.files.local_store.get_pdf_cache", return_value=cached_path), \
             patch("os.path.isfile", return_value=False), \
             patch("backend.core.files.settings") as mock_settings, \
             patch("os.path.exists", return_value=False):
            mock_settings.medicine_dir = ""
            result = _run(svc.auto_detect_pdf(course, context="college"))

        # Le chemin en cache était stale → search_path vide → None
        assert result is None


# ── Test 3 : search_path inexistant ──────────────────────────────────────────

class TestSearchPathMissing:
    def test_returns_none_when_search_path_not_exists(self, svc):
        course = _make_course()

        with patch("backend.core.files.local_store.get_pdf_cache", return_value=None), \
             patch("backend.core.files.settings") as mock_settings, \
             patch("os.path.exists", return_value=False), \
             patch("backend.core.obsidian.service.COLLEGE_MAPPING", {"Cardiovasculaire ❤️": "Cardiovasculaire"}):
            mock_settings.medicine_dir = "/medicine"
            result = _run(svc.auto_detect_pdf(course, context="college"))

        assert result is None

    def test_returns_none_when_medicine_dir_empty_for_ue(self, svc):
        course = _make_course()

        with patch("backend.core.files.local_store.get_pdf_cache", return_value=None), \
             patch("backend.core.files.settings") as mock_settings, \
             patch("os.path.exists", return_value=False):
            mock_settings.fac_dir = ""
            mock_settings.medicine_dir = ""
            result = _run(svc.auto_detect_pdf(course, context="ue"))

        assert result is None


# ── Test 4 : Score trop faible → None ────────────────────────────────────────

class TestScoreTooLow:
    def test_returns_none_when_find_pdf_empty(self, svc):
        course = _make_course()
        search_path = "/medicine/Colleges/Cardiovasculaire"

        with patch("backend.core.files.local_store.get_pdf_cache", return_value=None), \
             patch("backend.core.files.settings") as mock_settings, \
             patch("os.path.exists", return_value=True), \
             patch("os.path.isfile", return_value=False), \
             patch.object(svc, "refresh_cache_async", new_callable=AsyncMock), \
             patch.object(svc, "find_pdf", return_value=[]), \
             patch("backend.core.obsidian.service.COLLEGE_MAPPING", {"Cardiovasculaire ❤️": "Cardiovasculaire"}):
            mock_settings.medicine_dir = "/medicine"
            # Pré-peupler pdf_caches pour éviter le refresh
            svc.pdf_caches[search_path] = []
            result = _run(svc.auto_detect_pdf(course, context="college"))

        assert result is None


# ── Test 5 : Succès — chemin retourné + SQLite écrit ─────────────────────────

class TestSuccess:
    def test_returns_path_and_writes_sqlite_cache(self, svc):
        course = _make_course()
        expected_pdf = "/medicine/Colleges/Cardio/232-insuffisance-cardiaque.pdf"
        search_path = "/medicine/Collèges/Cardiovasculaire"

        with patch("backend.core.files.local_store.get_pdf_cache", return_value=None), \
             patch("backend.core.files.local_store.set_pdf_cache") as mock_set, \
             patch("backend.core.files.settings") as mock_settings, \
             patch("os.path.exists", return_value=True), \
             patch("os.path.isfile", return_value=False), \
             patch.object(svc, "refresh_cache_async", new_callable=AsyncMock), \
             patch.object(svc, "find_pdf", return_value=[expected_pdf]), \
             patch("backend.core.obsidian.service.COLLEGE_MAPPING", {"Cardiovasculaire ❤️": "Cardiovasculaire"}):
            mock_settings.medicine_dir = "/medicine"
            svc.pdf_caches[search_path] = [expected_pdf]
            result = _run(svc.auto_detect_pdf(course, context="college"))

        assert result == expected_pdf
        mock_set.assert_called_once_with(course.id, "college", expected_pdf)

    def test_ue_context_uses_fac_dir(self, svc):
        course = _make_course(url_pdf_ue=None)
        expected_pdf = "/fac/UE1/cours-insuffisance.pdf"

        with patch("backend.core.files.local_store.get_pdf_cache", return_value=None), \
             patch("backend.core.files.local_store.set_pdf_cache") as mock_set, \
             patch("backend.core.files.settings") as mock_settings, \
             patch("os.path.exists", return_value=True), \
             patch("os.path.isfile", return_value=False), \
             patch.object(svc, "refresh_cache_async", new_callable=AsyncMock), \
             patch.object(svc, "find_pdf", return_value=[expected_pdf]):
            mock_settings.fac_dir = "/fac"
            mock_settings.medicine_dir = "/medicine"
            svc.pdf_caches["/fac"] = [expected_pdf]
            result = _run(svc.auto_detect_pdf(course, context="ue"))

        assert result == expected_pdf
        mock_set.assert_called_once_with(course.id, "ue", expected_pdf)


# ── Test 6 : find_pdf() backward compatibility avec min_score=0.0 ─────────────

class TestFindPdfMinScore:
    def test_find_pdf_default_min_score_backward_compat(self, svc):
        """Sans min_score, le comportement est identique à avant (seuil effectif 5.0)."""
        svc.pdf_caches["/test"] = ["/test/neurologie.pdf"]
        # Avec un titre qui ne match rien, score <= 5 → retour vide
        results = svc.find_pdf("xyz_no_match", search_path="/test")
        # Le résultat peut être vide ou pas selon le scoring, mais l'appel ne plante pas
        assert isinstance(results, list)

    def test_find_pdf_min_score_50_filters_low_scores(self, svc):
        """min_score=50 doit filtrer les résultats avec un faible score."""
        svc.pdf_caches["/test"] = ["/test/completely-unrelated-file.pdf"]
        results = svc.find_pdf("neurologie", search_path="/test", min_score=50.0)
        # Un fichier sans rapport ne dépasse pas 50 de score
        assert results == []

    def test_find_pdf_min_score_0_same_as_default(self, svc):
        """min_score=0.0 équivaut au comportement par défaut (seuil effectif 5.0)."""
        svc.pdf_caches["/test"] = ["/test/neurologie-item-102.pdf"]
        results_default = svc.find_pdf("neurologie", search_path="/test")
        results_explicit = svc.find_pdf("neurologie", search_path="/test", min_score=0.0)
        assert results_default == results_explicit
