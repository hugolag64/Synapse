from backend.core.uness.gemini_conversion import convert_with_bridge
from backend.core.uness.models import UNSUPPORTED_VISUAL_EXPLANATION


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


def test_convert_with_bridge_matches_a_simplified_ai_returned_title():
    # Real Gemini responses routinely drop everything after the first line of a
    # multi-line bridge title (e.g. "mDP1\nTest" -> "mDP1"), even though the prompt
    # is given the exact title. An exact-match lookup then wrongly reports the quiz
    # as "absent du bridge" despite it being the obvious match.
    bridge = {
        "contents": [{"title": "mDP1\nTest", "html": _HTML, "images": []}],
        "source": {
            "source_url": "https://entrainement.uness.fr/annales/course/view.php?id=1",
            "collected_at": "2026-01-01T00:00:00+00:00",
            "collection_status": "submitted",
        },
    }
    quiz = {
        "quiz_title": "mDP1",
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
            }
        ],
    }
    exams = convert_with_bridge([quiz], bridge)
    assert len(exams) == 1
    assert [q.id for q in exams[0].questions] == ["question-1-2"]


def test_unsupported_visual_question_has_its_ai_verdict_cleared():
    # A question whose image wasn't fully provided to the model must not keep
    # whatever verdict Gemini guessed anyway — it's ungrounded. The official
    # UNESS answer (reponse_uness) must survive untouched so the question can
    # still be imported and answered against a real correction.
    bridge = _bridge(_HTML)
    bridge["contents"][0]["images"] = [
        {"question_id": "question-1-2", "filename": "scan.png", "alt_text": "Scanner"}
    ]
    quiz = {
        "quiz_title": "DP1\nTest",
        "questions": [
            {
                "id": "question-1-2",
                "type_question": "QRU",
                "enonce": "Quel est le diagnostic le plus probable ?",
                "propositions": [
                    {
                        "id": "p1",
                        "texte": "Colique néphrétique",
                        "reponse_officielle": True,
                        "verdict_ia": True,
                        "avis_ia": "valide",
                        "confiance_ia": 0.95,
                        "explication": "Je vois clairement une dilatation sur le scanner.",
                        "desaccord_officiel": False,
                    }
                ],
                "media": [{"filename": "scan.png", "accessible_ia": False}],
            }
        ],
    }
    exams = convert_with_bridge([quiz], bridge)
    question = exams[0].questions[0]
    assert question.verification_status == "unsupported"
    proposition = question.propositions[0]
    assert proposition.verdict_ia is None
    assert proposition.confiance_ia is None
    assert proposition.explication_ia == UNSUPPORTED_VISUAL_EXPLANATION
    assert proposition.statut == "incertain"
    # The official answer must survive — it's the only ground truth left.
    assert proposition.reponse_uness is True
