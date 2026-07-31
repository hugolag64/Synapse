from scripts.uness.collector import extract_question_images


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
    ]


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
