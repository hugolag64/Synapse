from pathlib import Path


def test_normalize_stable_resource_url_removes_ephemeral_query_parameters():
    from backend.core.ednpro.collector import normalize_stable_resource_url

    assert normalize_stable_resource_url(
        "https://ednpro.app/videos/221?token=secret&expires=123"
    ) == "https://ednpro.app/videos/221"


def test_parse_video_cards_extracts_category_and_explicit_item_number():
    from backend.core.ednpro.collector import parse_video_cards

    html = """
    <section data-category="Vidéos">
      <a class="video-card" href="/videos/221">
        <h3>Item 221 — Athérome</h3>
        <span>Cardiologie</span>
      </a>
      <a class="video-card" href="/videos/ecg">
        <h3>ECG</h3>
      </a>
    </section>
    """

    rows = parse_video_cards(html, "https://ednpro.app/videos")

    assert rows[0]["title"] == "Item 221 — Athérome"
    assert rows[0]["category"] == "Vidéos"
    assert rows[0]["item_numbers"] == ["221"]
    assert rows[1]["item_numbers"] == []


def test_parse_video_cards_accepts_video_route_links_without_card_class():
    from backend.core.ednpro.collector import parse_video_cards

    html = '<main><a href="/videos/221">Item 221 — ECG commenté</a></main>'

    rows = parse_video_cards(html, "https://ednpro.app/videos")

    assert rows == [{
        "title": "Item 221 — ECG commenté",
        "category": "",
        "url": "https://ednpro.app/videos/221",
        "item_numbers": ["221"],
    }]


def test_parse_annale_links_deduplicates_by_stable_url():
    from backend.core.ednpro.collector import parse_annale_links

    html = """
    <a href="/annales/2023-p1">Session 1 — P1</a>
    <a href="https://ednpro.app/annales/2023-p1?from=menu">Même session</a>
    <a href="/annales/2023-p2">Session 2 — P2</a>
    """

    rows = parse_annale_links(html, "https://ednpro.app/annales")

    assert [row["url"] for row in rows] == [
        "https://ednpro.app/annales/2023-p1",
        "https://ednpro.app/annales/2023-p2",
    ]


def test_extract_exam_payload_keeps_source_answers_and_video_refs():
    from scripts.ednpro.collector import extract_exam_payload

    html = """
    <main data-exam-title="EDN 2023 — P1">
      <article class="question" data-question-id="q-1" data-item-number="221">
        <p class="question-stem">Quel est le diagnostic ?</p>
        <label data-choice-id="a" data-correct="true">Réponse A</label>
        <label data-choice-id="b" data-correct="false">Réponse B</label>
      </article>
    </main>
    """

    payload = extract_exam_payload(
        html,
        url="https://ednpro.app/annales/2023-p1",
        title="EDN 2023 — P1",
        year=2023,
        session_id="2023-p1",
        resources=[{"title": "ECG", "url": "https://ednpro.app/videos/ecg", "type": "video"}],
    )

    assert payload["questions"][0]["item_numbers"] == ["221"]
    assert payload["questions"][0]["choices"][0]["correct"] is True
    assert payload["resources"][0]["url"] == "https://ednpro.app/videos/ecg"


def test_build_ednpro_exam_payload_joins_session_dossiers_questions_and_items():
    from backend.core.ednpro.collector import build_ednpro_exam_payload

    payload = build_ednpro_exam_payload(
        session={"id": "session-2023-p1", "annee": 2023, "session_label": "Session 1", "epreuve": "P1"},
        dossiers=[
            {"id": "dossier-1", "session_id": "session-2023-p1", "numero_dossier": 1, "type_dossier": "KFP"},
        ],
        questions=[
            {"id": "question-1", "dossier_id": "dossier-1", "numero_question": 1, "type": "QRM", "enonce": "Quel examen ?", "nb_reponses_attendues": 1},
        ],
        propositions=[
            {"id": "prop-a", "question_id": "question-1", "lettre": "A", "texte": "ECG", "is_correct": True},
            {"id": "prop-b", "question_id": "question-1", "lettre": "B", "texte": "IRM", "is_correct": False},
        ],
        question_oic=[{"question_id": "question-1", "item_number": 221, "rang": 1}],
        resources=[{"title": "ECG", "url": "https://ednpro.app/videos/ecg", "item_numbers": ["221"]}],
    )

    assert payload["title"] == "EDN 2023 — Session 1 · P1"
    assert payload["questions"][0]["item_numbers"] == ["221"]
    assert payload["questions"][0]["choices"][0] == {
        "id": "prop-a", "text": "ECG", "correct": True,
    }
    assert payload["questions"][0]["dp_context"]["dossier_number"] == 1


def test_build_ednpro_exam_payload_rejects_empty_question_set():
    import pytest
    from backend.core.ednpro.collector import build_ednpro_exam_payload

    with pytest.raises(ValueError, match="aucune question"):
        build_ednpro_exam_payload(
            session={"id": "session-1", "annee": 2023, "session_label": "Session 1", "epreuve": "P1"},
            dossiers=[], questions=[], propositions=[], question_oic=[],
        )


def test_build_video_resources_from_records_uses_item_edn_links():
    from backend.core.ednpro.collector import build_video_resources_from_records

    assert build_video_resources_from_records([
        {"id": "video-1", "title": "Athérome", "url": "https://ednpro.app/videos/221", "item_edn": 221},
    ]) == [{
        "title": "Athérome",
        "url": "https://ednpro.app/videos/221",
        "type": "video",
        "item_numbers": ["221"],
    }]
