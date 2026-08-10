"""Contrat d'import des corrections EDNpro observées dans Chromium."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def isolated_capture_db(tmp_path, monkeypatch):
    from backend.core.reviews import local_store

    monkeypatch.setattr(local_store, "DB_PATH", tmp_path / "capture.db")
    monkeypatch.setattr(local_store, "_DB", None)
    local_store.init_db()
    yield
    if local_store._DB is not None:
        local_store._DB.close()
    monkeypatch.setattr(local_store, "_DB", None)


def _raw_question(*, external_id: str, prompt: str, corrected: bool = True) -> dict:
    return {
        "session_id": "session-42",
        "question": {
            "id": external_id,
            "item_number": "221",
            "type": "QCM",
            "rank": "B",
            "prompt": prompt,
            "choices": [
                {"id": "a", "text": "Proposition A", "selected": True, "correct": True},
                {"id": "b", "text": "Proposition B", "selected": False, "correct": False},
            ],
            "simple_explanation": "Explication simple",
            "detailed_explanation": "Explication détaillée par IA",
        },
        "correction": {
            "selected_answers": ["a"],
            "correct_answers": ["a"],
            "score_percent": 100 if corrected else None,
            "is_correct": corrected if corrected else None,
            "displayed": corrected,
        },
    }


def test_normalize_observation_keeps_correction_and_explanations():
    from backend.core.ednpro.qcm_capture import normalize_observation

    observation = normalize_observation(_raw_question(external_id="q-1", prompt="Question 1"))

    assert observation.external_question_id == "q-1"
    assert observation.item_number == "221"
    assert observation.rank == "B"
    assert observation.selected_answers == ("a",)
    assert observation.correct_answers == ("a",)
    assert observation.score_percent == 100.0
    assert observation.corrected is True
    assert observation.explanation_simple == "Explication simple"
    assert observation.explanation_detailed == "Explication détaillée par IA"


def test_extract_corrected_observation_ignores_unanswered_dom_and_reads_rank():
    from backend.core.ednpro.qcm_capture import extract_corrected_observation

    unanswered = """
    <article data-qcm-question="q-dom" data-item-number="230">
      <span>Item 230 · QCM · Rang B</span>
      <h3 data-question-stem>Question visible</h3>
      <label data-choice-id="a"><input type="checkbox">A</label>
    </article>
    """
    assert extract_corrected_observation(unanswered) is None

    corrected = """
    <article data-qcm-question="q-dom" data-item-number="230" data-corrected="true">
      <span>Item 230 · QCM · Rang B</span>
      <h3 data-question-stem>Question visible</h3>
      <label data-choice-id="a" data-selected="true" data-correct="true">A</label>
      <label data-choice-id="b" data-correct="false">B</label>
      <div data-explanation-simple>Explication courte</div>
      <div data-explanation-detailed>Analyse détaillée</div>
    </article>
    """
    observation = extract_corrected_observation(corrected, source_url="https://ednpro.app/objective-session/1")
    assert observation is not None
    assert observation.external_question_id == "q-dom"
    assert observation.item_number == "230"
    assert observation.rank == "B"
    assert observation.selected_answers == ("a",)
    assert observation.correct_answers == ("a",)


def test_extract_ednpro_react_card_without_data_attributes():
    from backend.core.ednpro.qcm_capture import extract_corrected_observation

    html = """
    <div>Question 1 / 2</div>
    <div class="rounded-lg border bg-card p-6 space-y-4">
      <div><div>Item 75</div><div>QCM</div><div>Facile</div></div>
      <p class="text-base sm:text-lg">Question d'addictologie</p>
      <p class="text-xs italic">Une ou plusieurs réponses justes</p>
      <div class="space-y-3">
        <button class="w-full text-left p-3.5 rounded-lg border-2 border-destructive">
          <div>
            <span class="font-mono">A.</span>
            <span class="text-sm leading-relaxed flex-1">Réponse A</span>
            <span class="h-5 w-5"><svg></svg></span>
            <span>100%</span>
          </div>
          <div><p>Vrai</p><div class="prose">Explication A</div></div>
        </button>
        <button class="w-full text-left p-3.5 rounded-lg border-2">
          <div>
            <span class="font-mono">B.</span>
            <span class="text-sm leading-relaxed flex-1">Réponse B</span>
            <span class="h-5 w-5"></span>
            <span>0%</span>
          </div>
          <div><p>Faux</p><div class="prose">Explication B</div></div>
        </button>
      </div>
      <div class="flex border-2"><span>Note obtenue</span><span>1 / 1 pt</span></div>
      <div class="space-y-2"><div>Explication détaillée par IA</div><p>Les réponses correctes sont A. Analyse détaillée</p></div>
    </div>
    """

    observation = extract_corrected_observation(
        html,
        source_url=(
            "https://ednpro.app/objective-session/multi?"
            "legacyQids=q-75&iqIds=q-76"
        ),
    )

    assert observation is not None
    assert observation.external_question_id == "q-75"
    assert observation.item_number == "75"
    assert observation.corrected is True
    assert observation.score_percent == 100.0
    assert observation.correct_answers == ("A",)
    assert observation.selected_answers == ("A",)
    assert "Explication A" in observation.explanation_simple
    assert "Analyse détaillée" in observation.explanation_detailed


def test_import_discards_question_not_yet_corrected_and_is_idempotent():
    from backend.core.ednpro.qcm_capture import normalize_observation, import_session
    from backend.core.reviews import local_store

    session = {
        "external_session_id": "session-42",
        "session_date": "2026-08-10T13:00:00+02:00",
        "questions": [
            normalize_observation(_raw_question(external_id="q-1", prompt="Question 1")),
            normalize_observation(_raw_question(external_id="q-2", prompt="Question 2", corrected=False)),
        ],
    }

    first = import_session(session)
    second = import_session(session)

    assert first.imported_questions == 1
    assert first.discarded_questions == 1
    assert second.imported_questions == 0
    assert second.duplicate_attempts == 1
    with local_store._conn() as con:
        assert con.execute("SELECT COUNT(*) FROM ednpro_qcm_questions").fetchone()[0] == 1
        assert con.execute("SELECT COUNT(*) FROM ednpro_qcm_attempts").fetchone()[0] == 1
        assert con.execute("SELECT COUNT(*) FROM ednpro_qcm_sessions").fetchone()[0] == 1


def test_existing_question_is_preserved_but_new_attempt_is_recorded():
    from backend.core.ednpro.qcm_capture import normalize_observation, import_session
    from backend.core.reviews import local_store

    import_session({
        "external_session_id": "session-1",
        "session_date": "2026-08-10",
        "questions": [normalize_observation(_raw_question(external_id="q-1", prompt="Version originale"))],
    })
    result = import_session({
        "external_session_id": "session-2",
        "session_date": "2026-08-11",
        "questions": [normalize_observation(_raw_question(external_id="q-1", prompt="Version modifiée"))],
    })

    assert result.new_questions == 0
    assert result.new_attempts == 1
    with local_store._conn() as con:
        question = con.execute(
            "SELECT prompt FROM ednpro_qcm_questions WHERE external_question_id = ?", ("q-1",)
        ).fetchone()
        assert question["prompt"] == "Version originale"
        assert con.execute("SELECT COUNT(*) FROM ednpro_qcm_attempts").fetchone()[0] == 2


def test_item_stats_expose_correct_wrong_and_rank_counts():
    from backend.core.ednpro.qcm_capture import normalize_observation, import_session, get_item_stats

    first = normalize_observation(_raw_question(external_id="q-1", prompt="Q1"))
    second_raw = _raw_question(external_id="q-2", prompt="Q2")
    second_raw["question"]["rank"] = "A"
    second_raw["correction"] = {
        "selected_answers": ["b"],
        "correct_answers": ["a"],
        "score_percent": 0,
        "is_correct": False,
        "displayed": True,
    }
    second = normalize_observation(second_raw)
    import_session({"external_session_id": "session-1", "session_date": "2026-08-10", "questions": [first, second]})

    assert get_item_stats("221") == {
        "attempts": 2,
        "correct": 1,
        "wrong": 1,
        "average_score_percent": 50.0,
        "rank_a": {"attempts": 1, "correct": 0, "wrong": 1},
        "rank_b": {"attempts": 1, "correct": 1, "wrong": 0},
        "rank_unknown": {"attempts": 0, "correct": 0, "wrong": 0},
    }


def test_local_capture_stop_contains_only_observed_corrections():
    from backend.core.ednpro.qcm_capture import normalize_observation
    from scripts.ednpro.qcm_capture_agent import CaptureBuffer

    buffer = CaptureBuffer()
    buffer.start("session-local")
    buffer.add(normalize_observation(_raw_question(external_id="q-1", prompt="Q1")))

    session = buffer.consume_stop() if (buffer.request_stop() is None) else None

    assert session is not None
    assert session["external_session_id"] == "session-local"
    assert [question["external_question_id"] for question in session["questions"]] == ["q-1"]
    assert buffer.status()["active"] is False


def test_capture_buffer_reports_automatic_browser_lifecycle():
    from scripts.ednpro.qcm_capture_agent import CaptureBuffer

    buffer = CaptureBuffer()
    assert buffer.status()["state"] == "ready"

    buffer.start()
    assert buffer.status()["state"] == "starting"

    buffer.mark_browser_ready()
    assert buffer.status()["state"] == "capturing"


def test_capture_agent_loads_json_config_and_cli_overrides(tmp_path):
    from scripts.ednpro.qcm_capture_agent import load_agent_config

    config_path = tmp_path / "agent.json"
    config_path.write_text(
        '{"synapse_url":"https://synapse.home.arpa",'
        '"token":"test-only-token",'
        '"profile_dir":"C:/Users/test/AppData/Local/Synapse/ednpro-chrome",'
        '"listen_port":8876}',
        encoding="utf-8",
    )

    config = load_agent_config(config_path)
    assert config["synapse_url"] == "https://synapse.home.arpa"
    assert config["token"] == "test-only-token"
    assert config["listen_port"] == 8876

    overridden = load_agent_config(config_path, cli_overrides={"token": "cli-token"})
    assert overridden["token"] == "cli-token"


def test_chrome_launch_command_uses_normal_browser_with_remote_debugging(tmp_path):
    from scripts.ednpro.qcm_capture_agent import build_chrome_launch_command

    command = build_chrome_launch_command(
        chrome_path="C:/Program Files/Google/Chrome/Application/chrome.exe",
        profile_dir=tmp_path / "chrome-profile",
        cdp_port=9222,
        url="https://ednpro.app/training-v2",
    )

    assert command[0].endswith("chrome.exe")
    assert "--remote-debugging-port=9222" in command
    assert any(value.startswith("--user-data-dir=") for value in command)
    assert "--headless" not in " ".join(command)
    assert "https://ednpro.app/training-v2" in command


def test_import_can_publish_one_qcm_evaluation_per_item():
    from backend.core.ednpro.qcm_capture import import_session, normalize_observation, record_imported_evaluations
    from backend.core.reviews import local_store

    result = import_session({
        "external_session_id": "session-evaluation",
        "session_date": "2026-08-10",
        "questions": [normalize_observation(_raw_question(external_id="q-eval", prompt="Q"))],
    })
    persisted = record_imported_evaluations(
        session={"session_date": "2026-08-10"},
        result=result,
        course_resolver=lambda item: {"id": "course-221", "title": "Athérome"},
    )

    assert len(persisted) == 1
    row = local_store.get_qcm_sessions_by_course("course-221")[0]
    assert row["platform"] == "EDNpro"
    assert row["rank_a_questions"] == 0
    assert row["rank_b_questions"] == 1
    assert row["rank_b_correct"] == 1
    assert row["rank_unknown_questions"] == 0
