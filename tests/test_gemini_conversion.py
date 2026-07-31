from backend.core.uness.gemini_conversion import convert_with_bridge


def _bridge(html: str) -> dict:
    return {
        "contents": [{"title": "DP1\nTest", "html": html, "images": []}],
        "source": {
            "source_url": "https://entrainement.uness.fr/annales/course/view.php?id=1",
            "collected_at": "2026-01-01T00:00:00+00:00",
            "collection_status": "submitted",
        },
    }


_HTML = """
<ol class="breadcrumb"><li><a>Accueil</a></li><li><a>Faculté de médecine de La Réunion</a></li>
<li><a>DFASM1 (Urologie)</a></li><li><span>DFASM1_2023-2024_CT_UE9_070224</span></li></ol>
<div id="question-1-1" class="que description informationitem complete">
  <div class="qtext"><p>Un homme de 27 ans consulte pour une douleur lombaire.</p></div>
</div>
<div id="question-1-2" class="que sngonechoice">
  <div class="qtext"><p>Quel est le diagnostic le plus probable ?</p></div>
</div>
"""


def test_vignette_without_propositions_is_excluded_from_questions():
    # Some AI responses include the shared clinical vignette as its own "question"
    # (matching Moodle's "description" block) with zero propositions, despite the
    # prompt asking them not to. It must never surface as an answerable question.
    quiz = {
        "quiz_title": "DP1\nTest",
        "questions": [
            {
                "id": "question-1-1",
                "type_question": "DP",
                "enonce": "Un homme de 27 ans consulte pour une douleur lombaire.",
                "verification_status": "verified",
                "propositions": [],
                "correction_globale": "",
                "statut_verification": "validee",
            },
            {
                "id": "question-1-2",
                "type_question": "QRU",
                "enonce": "Quel est le diagnostic le plus probable ?",
                "verification_status": "verified",
                "propositions": [
                    {
                        "id": "p1",
                        "texte": "Colique néphrétique",
                        "reponse_officielle": True,
                        "verdict_ia": True,
                        "avis_ia": "valide",
                        "confiance_ia": 1.0,
                        "explication": "Tableau typique.",
                        "desaccord_officiel": False,
                    }
                ],
                "correction_globale": "",
                "statut_verification": "validee",
            },
        ],
    }
    exams = convert_with_bridge([quiz], _bridge(_HTML))
    assert len(exams) == 1
    exam = exams[0]
    assert [q.id for q in exam.questions] == ["question-1-2"]
    assert exam.dp_context.get("enonce_general", "").startswith("Un homme de 27 ans")


def test_question_dp_context_never_leaks_the_answer_key_before_answering():
    # question.dp_context is rendered by the frontend BEFORE the learner answers
    # (shared clinical vignette / extra pre-answer context). The AI's own
    # correction commentary (correction_globale, reponse_officielle_texte,
    # statut_verification, reponse_ia) must never end up there — it already
    # leaked once, revealing "Réponses officiellement exactes : ..." in the
    # question card before any answer was given.
    quiz = {
        "quiz_title": "DP1\nTest",
        "questions": [
            {
                "id": "question-1-2",
                "type_question": "QRU",
                "enonce": "Quel est le diagnostic le plus probable ?",
                "verification_status": "verified",
                "propositions": [
                    {
                        "id": "p1",
                        "texte": "Colique néphrétique",
                        "reponse_officielle": True,
                        "verdict_ia": True,
                        "avis_ia": "valide",
                        "confiance_ia": 1.0,
                        "explication": "Tableau typique.",
                        "desaccord_officiel": False,
                    }
                ],
                "correction_globale": "Réponses officiellement exactes : Colique néphrétique.",
                "reponse_officielle_texte": "Colique néphrétique",
                "statut_verification": "validee",
                "reponse_ia": "Colique néphrétique",
            }
        ],
    }
    exams = convert_with_bridge([quiz], _bridge(_HTML))
    question = exams[0].questions[0]
    assert "Colique néphrétique" not in str(question.dp_context)
    assert "validee" not in str(question.dp_context)
