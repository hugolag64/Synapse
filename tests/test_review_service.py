import asyncio
from datetime import datetime, date
from unittest import TestCase
from unittest.mock import patch, MagicMock

# Importation de tes structures
from backend.core.reviews.models import ReviewTask
from backend.core.reviews.service import ReviewService
from backend.core.notion.models import Cours


class TestReviewService(TestCase):

    def setUp(self):
        """Configuration initiale avant chaque test."""
        self.service = ReviewService()
        
        # Date de référence fixe pour le test : Vendredi 22 Mai 2026
        self.today_mock = date(2026, 5, 22)

    @patch('backend.core.reviews.service.date')
    @patch('backend.state.store.data_store')
    def test_generate_reviews_categories(self, mock_data_store, mock_date):
        """Vérifie que les cours sont triés dans les bonnes colonnes du Dashboard."""
        
        # 1. On fige la date du jour du système pour le test
        mock_date.today.return_value = self.today_mock
        mock_date.side_effect = lambda *args, **kwargs: date(*args, **kwargs)

        # 2. Création d'un jeu de fausses données (Mock)
        def create_mock_cours(id, title, date_1ere, nb_lectures, rappel_done, url_pdf, edn, anki):
            c = MagicMock(spec=Cours)
            c.id = id
            c.title = title
            c.item_number = "100"
            c.college = ["Test"]
            c.date_1ere_lecture = date_1ere
            c.nb_lectures = nb_lectures
            c.rappel_done = rappel_done
            c.url_pdf = url_pdf
            c.agregation_fiche_edn = edn
            c.anki = anki
            c.qcm_done = False
            c.course_status = "À lire"
            # Éviter les AttributeError
            c.lecture_j3_college = None
            c.lecture_j7_college = None
            c.lecture_j14_college = None
            c.lecture_j30_college = None
            c.url_pdf_ue = None
            c.nb_lectures_ue = 0
            c.date_1ere_lecture_ue = None
            c.lecture_j3_ue = None
            c.lecture_j7_ue = None
            c.lecture_j14_ue = None
            c.lecture_j30_ue = None
            return c

        # Cours 1 : En retard de 4 jours (Urgent)
        cours_urgent = create_mock_cours("1", "ITEM 169 – Infections à VIH", date(2026, 5, 18), 0, True, "path", None, False)

        # Cours 2 : à réviser aujourd'hui (Prévu)
        cours_prevu = create_mock_cours("2", "ITEM 166 – Grippe", date(2026, 5, 15), 1, True, "path", "http://edn.com", False)
    
        # Cours 3 : Pas de révision de prévue (Bonus)
        cours_bonus = create_mock_cours("3", "Eosinophilie", None, 3, False, "path", None, True)

        liste_cours = [cours_urgent, cours_prevu, cours_bonus]
        mock_data_store.cours = liste_cours

        # Simuler l'historique local pour dire que la J3 du "cours_prevu" a déjà été faite
        # Sinon elle apparaîtra comme en retard
        mock_history = {
            "2_college_J3_2026-05-18": {"status": "done", "postponed_to": None, "postponed_count": 0}
        }

        # 3. Exécution de la fonction cible
        all_tasks = self.service.generate_reviews(context="college", history=mock_history)
        
        urgent_tasks = self.service.get_urgent_tasks(all_tasks)
        prevu_tasks = self.service.get_today_tasks(all_tasks)
        bonus_tasks = self.service.get_bonus_tasks(history={}, context="college")

        # 4. Assertions (Les vérifications)
        
        # Vérification des répartitions
        self.assertEqual(len(urgent_tasks), 1, "Il devrait y avoir 1 tâche urgente")
        self.assertEqual(len(prevu_tasks), 1, "Il devrait y avoir 1 tâche prévue")
        self.assertEqual(len(bonus_tasks), 2, "Il devrait y avoir 2 tâches bonus (cours_bonus + cours_urgent qui a 0 lecture)")

        # Vérification du calcul du retard (22 mai - 18 mai = 4 jours)
        # Note: Le modèle génère "J3" depuis le 18, donc 21 Mai. Retard de 1 jour.
        self.assertEqual(urgent_tasks[0].days_overdue, 1)
        self.assertEqual(urgent_tasks[0].course_id, "1")
        self.assertEqual(urgent_tasks[0].review_type, "J3")  # Ton moteur garde le type J3 original
        self.assertEqual(urgent_tasks[0].type_badge, "J3 +1j")   # Ou la propriété qui génère la string du badge (J3 + retard)
        self.assertTrue(urgent_tasks[0].days_overdue > 0, "La tâche devrait être marquée en retard")

        # Vérification des flags d'état
        self.assertTrue(urgent_tasks[0].has_pdf)
        self.assertFalse(urgent_tasks[0].agregation_fiche_edn)
        
        self.assertTrue(prevu_tasks[0].has_pdf)
        self.assertEqual(prevu_tasks[0].agregation_fiche_edn, "http://edn.com")

    def _mock_course_min(self, cid, date_1ere, nb_lectures=0):
        """Mock minimal réutilisable pour les tests de get_urgent_course_ids."""
        c = MagicMock(spec=Cours)
        c.id = cid
        c.title = f"Cours {cid}"
        c.item_number = "100"
        c.college = ["Test"]
        c.date_1ere_lecture = date_1ere
        c.nb_lectures = nb_lectures
        c.rappel_done = True
        c.url_pdf = "path"
        c.agregation_fiche_edn = None
        c.anki = False
        c.qcm_done = False
        c.course_status = "À lire"
        c.lecture_j3_college = None
        c.lecture_j7_college = None
        c.lecture_j14_college = None
        c.lecture_j30_college = None
        c.url_pdf_ue = None
        c.nb_lectures_ue = 0
        c.date_1ere_lecture_ue = None
        c.lecture_j3_ue = None
        c.lecture_j7_ue = None
        c.lecture_j14_ue = None
        c.lecture_j30_ue = None
        return c

    @patch('backend.core.reviews.service.date')
    @patch('backend.state.store.data_store')
    def test_get_urgent_course_ids_excludes_completed_reviews(self, mock_data_store, mock_date):
        """Un cours dont TOUTES les révisions en retard sont déjà 'done' ne doit pas être urgent."""
        mock_date.today.return_value = self.today_mock
        mock_date.side_effect = lambda *args, **kwargs: date(*args, **kwargs)
        mock_date.fromisoformat = date.fromisoformat

        course = self._mock_course_min("c1", date(2026, 4, 18))
        mock_data_store.cours = [course]

        # J3=04-21, J7=04-25, J14=05-02, J30=05-18 — toutes en retard par rapport
        # au today_mock (2026-05-22), mais toutes marquées faites.
        history = {
            "c1_college_J3_2026-04-21":  {"status": "done", "postponed_to": None, "postponed_count": 0},
            "c1_college_J7_2026-04-25":  {"status": "done", "postponed_to": None, "postponed_count": 0},
            "c1_college_J14_2026-05-02": {"status": "done", "postponed_to": None, "postponed_count": 0},
            "c1_college_J30_2026-05-18": {"status": "done", "postponed_to": None, "postponed_count": 0},
        }

        urgent_ids = self.service.get_urgent_course_ids("college", history=history)

        self.assertNotIn("c1", urgent_ids)

    @patch('backend.core.reviews.service.date')
    @patch('backend.state.store.data_store')
    def test_get_urgent_course_ids_includes_real_overdue(self, mock_data_store, mock_date):
        """Un cours avec une révision réellement en retard et non traitée doit être urgent."""
        mock_date.today.return_value = self.today_mock
        mock_date.side_effect = lambda *args, **kwargs: date(*args, **kwargs)
        mock_date.fromisoformat = date.fromisoformat

        course = self._mock_course_min("c2", date(2026, 5, 10))
        mock_data_store.cours = [course]

        # J3=05-13 et J7=05-17 sont en retard par rapport à today_mock (2026-05-22)
        # et n'ont aucune entrée d'historique -> statut par défaut 'todo'.
        history: dict = {}

        urgent_ids = self.service.get_urgent_course_ids("college", history=history)

        self.assertIn("c2", urgent_ids)

    @patch('backend.core.reviews.service.date')
    @patch('backend.state.store.data_store')
    def test_get_urgent_course_ids_respects_postponed_future(self, mock_data_store, mock_date):
        """Une révision reportée à une date future ne doit pas compter comme urgente."""
        mock_date.today.return_value = self.today_mock
        mock_date.side_effect = lambda *args, **kwargs: date(*args, **kwargs)
        mock_date.fromisoformat = date.fromisoformat

        course = self._mock_course_min("c3", date(2026, 4, 1))
        mock_data_store.cours = [course]

        # J3=04-04 reporté au 2026-05-25 (futur par rapport à today_mock 2026-05-22).
        # J7/J14/J30 marquées faites pour isoler le cas testé.
        history = {
            "c3_college_J3_2026-04-04":  {"status": "postponed", "postponed_to": "2026-05-25", "postponed_count": 1},
            "c3_college_J7_2026-04-08":  {"status": "done", "postponed_to": None, "postponed_count": 0},
            "c3_college_J14_2026-04-15": {"status": "done", "postponed_to": None, "postponed_count": 0},
            "c3_college_J30_2026-05-01": {"status": "done", "postponed_to": None, "postponed_count": 0},
        }

        urgent_ids = self.service.get_urgent_course_ids("college", history=history)

        self.assertNotIn("c3", urgent_ids)


if __name__ == '__main__':
    import unittest
    unittest.main()
