from scripts.uness.collector import _stage_review_images, extract_question_images


def test_extract_question_images_finds_content_images_per_question():
    html = """
    <div id="question-16814955-1" class="que description informationitem complete">
      <img src="/theme/image.php/boost/core/icon" alt="icon">
      <img src="pluginfile.php/123/question/questiontext/1/dermato1.jpg" alt="Lesion cutanee">
    </div>
    <div id="question-16814955-2" class="que sngonechoice">
      <img src="https://entrainement.uness.fr/annales/pluginfile.php/123/question/questiontext/2/radio.png" alt="Radio thorax">
      <img src="data:image/png;base64,AAAA" alt="inline">
    </div>
    """
    images = extract_question_images(
        html, "https://entrainement.uness.fr/annales/mod/quiz/review.php?attempt=16814955"
    )
    assert images == [
        {
            "question_id": "question-16814955-1",
            "absolute_url": "https://entrainement.uness.fr/annales/mod/quiz/pluginfile.php/123/question/questiontext/1/dermato1.jpg",
            "alt_text": "Lesion cutanee",
        },
        {
            "question_id": "question-16814955-2",
            "absolute_url": "https://entrainement.uness.fr/annales/pluginfile.php/123/question/questiontext/2/radio.png",
            "alt_text": "Radio thorax",
        },
        {
            "question_id": "question-16814955-2",
            "data_uri": "data:image/png;base64,AAAA",
            "alt_text": "inline",
        },
    ]


def test_extract_question_images_captures_plain_img_with_inline_base64_data_uri():
    # Real-world UNESS DP/scanner questions embed the image directly as a plain
    # <img src="data:image/webp;base64,..."> — no pluginfile URL, no qzone <script>
    # wrapper. This must not be silently dropped like a theme/UI icon would be.
    html = """
    <div id="question-1-1" class="que description informationitem complete">
      <div class="qtext"><p>Vous réalisez des examens complémentaires (cf. image).</p></div>
      <img src="data:image/webp;base64,UklGRlZIREFTQQ==" alt="Scanner thoracique">
    </div>
    """
    images = extract_question_images(html, "https://entrainement.uness.fr/annales/")
    assert images == [
        {
            "question_id": "question-1-1",
            "data_uri": "data:image/webp;base64,UklGRlZIREFTQQ==",
            "alt_text": "Scanner thoracique",
        }
    ]


def test_extract_question_images_ignores_non_image_or_malformed_data_uris():
    html = """
    <div id="question-1-1" class="que">
      <img src="data:text/plain;base64,AAAA" alt="not an image">
      <img src="data:image/png" alt="missing base64 marker">
    </div>
    """
    assert extract_question_images(html, "https://entrainement.uness.fr/annales/") == []


def test_extract_question_images_ignores_duplicate_urls():
    html = """
    <div id="question-1-1" class="que">
      <img src="pluginfile.php/1/radio.png" alt="Radio">
      <img src="pluginfile.php/1/radio.png" alt="Radio (repeated in feedback)">
    </div>
    """
    images = extract_question_images(html, "https://entrainement.uness.fr/annales/")
    assert len(images) == 1


def test_extract_question_images_returns_empty_list_when_no_questions():
    assert extract_question_images("<html><body>no questions here</body></html>", "https://x/") == []


def test_extract_question_images_decodes_qzone_embedded_base64_image():
    # Moodle's "qzone" (click-a-zone) question type has no <img> at all: the
    # qzone-player.js widget draws its background image from a base64 data URI
    # embedded in an inline <script>.
    html = """
    <div id="question-16815044-6" class="que qzone immediatefeedback notanswered">
      <div class="qtext"><p>Où est l'obstacle sur cette coupe de scanographie ?</p></div>
      <script>
        document.addEventListener('DOMContentLoaded', function() {
          const imageUrl = 'data:image/webp;base64,AAAA';
        });
      </script>
    </div>
    """
    images = extract_question_images(html, "https://entrainement.uness.fr/annales/")
    assert images == [
        {
            "question_id": "question-16815044-6",
            "data_uri": "data:image/webp;base64,AAAA",
            "alt_text": "",
        }
    ]


def test_stage_review_images_copies_into_both_staging_and_review_dirs(tmp_path):
    images_dir = tmp_path / "artifact" / "images"
    images_dir.mkdir(parents=True)
    (images_dir / "dermato1.jpg").write_bytes(b"fake-image-bytes")
    staging_dir = tmp_path / "UNESS" / "images" / "20260731T140000Z"
    review_dir = tmp_path / "UNESS" / "a_verifier" / "session-20260731T140000Z"
    review_dir.mkdir(parents=True)

    copied = _stage_review_images(images_dir, staging_dir, review_dir)

    assert copied == ["dermato1.jpg"]
    assert (staging_dir / "dermato1.jpg").read_bytes() == b"fake-image-bytes"
    assert (review_dir / "dermato1.jpg").read_bytes() == b"fake-image-bytes"


def test_stage_review_images_returns_empty_list_when_no_images(tmp_path):
    images_dir = tmp_path / "artifact" / "images"
    images_dir.mkdir(parents=True)
    staging_dir = tmp_path / "UNESS" / "images" / "stamp"
    review_dir = tmp_path / "UNESS" / "a_verifier" / "session-stamp"
    review_dir.mkdir(parents=True)

    assert _stage_review_images(images_dir, staging_dir, review_dir) == []
    assert not staging_dir.exists()
