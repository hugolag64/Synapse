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
