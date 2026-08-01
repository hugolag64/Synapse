"""Tests for the read-only UNESS import diagnostics report."""

from __future__ import annotations

import json

import pytest

from backend.core.reviews import local_store
from backend.core.uness import diagnostics, import_service


@pytest.fixture(autouse=True)
def isolated_store(tmp_path, monkeypatch):
    database = tmp_path / "synapse-test.db"
    monkeypatch.setattr(local_store, "DB_PATH", database)
    monkeypatch.setattr(local_store, "_DB", None)
    local_store.init_db()
    yield
    if local_store._DB is not None:
        local_store._DB.close()
    monkeypatch.setattr(local_store, "_DB", None)


@pytest.fixture
def uness_dirs(tmp_path, monkeypatch):
    to_review = tmp_path / "à_vérifier"
    archives = tmp_path / "archives"
    verified = tmp_path / "vérifiés"
    to_review.mkdir()
    archives.mkdir()
    verified.mkdir()
    monkeypatch.setattr(import_service, "TO_REVIEW_DIR", to_review)
    monkeypatch.setattr(import_service, "ARCHIVE_DIR", archives)
    monkeypatch.setattr(import_service, "VERIFIED_DIR", verified)
    return {"to_review": to_review, "archives": archives, "verified": verified}


def _bridge_file(path, *, source_url, collected_at, title):
    path.write_text(
        json.dumps(
            {
                "contents": [{"title": title, "html": "<div></div>", "images": []}],
                "source": {"source_url": source_url, "collected_at": collected_at, "collection_status": "submitted"},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def test_latest_collection_wins_when_a_source_url_was_scraped_twice(uness_dirs):
    session_a = uness_dirs["to_review"] / "session-A"
    session_b = uness_dirs["to_review"] / "session-B"
    session_a.mkdir()
    session_b.mkdir()
    _bridge_file(
        session_a / "dp1.json", source_url="https://x/1", collected_at="2026-01-01T00:00:00+00:00", title="DP1\nTest"
    )
    _bridge_file(
        session_b / "dp1.json", source_url="https://x/1", collected_at="2026-02-01T00:00:00+00:00", title="DP1\nTest"
    )
    _bridge_file(
        session_b / "dp2.json", source_url="https://x/1", collected_at="2026-02-01T00:00:00+00:00", title="DP2\nTest"
    )

    titles = diagnostics._latest_quiz_titles_by_source_url()

    # Only session B's titles (the more recent collected_at) count — session A's
    # lone DP1 must not shrink the reference list back down to one quiz.
    assert titles["https://x/1"] == ["DP1", "DP2"]


def test_build_report_marks_a_quiz_imported(uness_dirs):
    session = uness_dirs["to_review"] / "session-A"
    session.mkdir()
    _bridge_file(
        session / "dp1.json", source_url="https://x/1", collected_at="2026-01-01T00:00:00+00:00", title="DP1\nTest"
    )
    annale_id = local_store.create_uness_annale(
        source_url="https://x/1", collected_at="2026-01-01T00:00:00+00:00", faculte="Fac",
        niveau="N1", annee=2026, matiere="Cardio", titre="Cardio — Fac — 2026", type_annale="matiere",
    )
    from backend.core.practice.models import PracticeDifficulty, PracticeKind, PracticeSessionSpec, QuestionKind
    session_id = local_store.create_ai_practice_session(
        spec=PracticeSessionSpec(
            practice_kind=PracticeKind.QCM, total_questions=1, open_questions=0, closed_questions=1,
            course_id="", course_title="Cardio — Fac — 2026 — DP1", item_number="",
            difficulty=PracticeDifficulty.EDN,
        ),
        questions=[{"kind": QuestionKind.CLOSED, "prompt": "Q", "choices": ["a"], "answer": "[]", "explanation": "e"}],
        model="test",
    )
    local_store.set_session_annale_id(session_id, annale_id)

    report = diagnostics.build_report()

    annale_entry = next(a for a in report["annales"] if a["annale"]["id"] == annale_id)
    assert annale_entry["quizzes"] == [{"title": "DP1", "status": "imported", "detail": {}}]


def test_build_report_marks_a_quiz_retry_pending(uness_dirs):
    session = uness_dirs["to_review"] / "session-A"
    session.mkdir()
    _bridge_file(
        session / "dp1.json", source_url="https://x/1", collected_at="2026-01-01T00:00:00+00:00", title="DP1\nTest"
    )
    annale_id = local_store.create_uness_annale(
        source_url="https://x/1", collected_at="2026-01-01T00:00:00+00:00", faculte="Fac",
        niveau="N1", annee=2026, matiere="Cardio", titre="Cardio — Fac — 2026", type_annale="matiere",
    )
    failure_id = local_store.record_uness_correction_failure(
        bridge_folder=str(session), quiz_title="DP1\nTest", collected_at="2026-01-01T00:00:00+00:00",
        error_message="Réponse incomplète : 2/3 questions",
    )
    failure_row = local_store.get_uness_correction_failure(failure_id)

    report = diagnostics.build_report()

    annale_entry = next(a for a in report["annales"] if a["annale"]["id"] == annale_id)
    assert annale_entry["quizzes"] == [{
        "title": "DP1", "status": "retry_pending",
        "detail": {
            "error": "Réponse incomplète : 2/3 questions",
            "attempts": failure_row["attempts"],
            "next_retry_at": failure_row["next_retry_at"],
            "failure_id": failure_id,
        },
    }]


def test_build_report_marks_a_never_attempted_quiz(uness_dirs):
    session = uness_dirs["to_review"] / "session-A"
    session.mkdir()
    _bridge_file(
        session / "dp1.json", source_url="https://x/1", collected_at="2026-01-01T00:00:00+00:00", title="DP1\nTest"
    )
    _bridge_file(
        session / "dp2.json", source_url="https://x/1", collected_at="2026-01-01T00:00:00+00:00", title="DP2\nTest"
    )
    annale_id = local_store.create_uness_annale(
        source_url="https://x/1", collected_at="2026-01-01T00:00:00+00:00", faculte="Fac",
        niveau="N1", annee=2026, matiere="Cardio", titre="Cardio — Fac — 2026", type_annale="matiere",
    )
    # DP1 was never corrected or logged as a failure (the silent-crash case).

    report = diagnostics.build_report()

    annale_entry = next(a for a in report["annales"] if a["annale"]["id"] == annale_id)
    statuses = {q["title"]: q["status"] for q in annale_entry["quizzes"]}
    assert statuses == {"DP1": "never_attempted", "DP2": "never_attempted"}


def test_build_report_lists_pending_tag_source_urls_separately(uness_dirs):
    verified = uness_dirs["verified"]
    verified.joinpath("dp1-corrige.json").write_text(
        json.dumps({
            "schema_version": 1, "faculty": "Fac", "level": "N1", "year": 2026,
            "title": "Cardio — Fac — 2026 — DP1", "dp_context": {},
            "questions": [{
                "id": "q1", "type_question": "QRU", "enonce": "Q?", "propositions": [
                    {"id": "p1", "texte": "a", "reponse_uness": True, "verdict_ia": True,
                     "explication_ia": "e", "confiance_ia": 0.9, "statut": "concordant"}
                ], "verification_status": "verified",
            }],
            "provenance": {"source": "Gemini+UNESS", "source_url": "https://x/2",
                           "collected_at": "2026-01-01T00:00:00+00:00", "collection_status": "submitted"},
            "metadata": {"subject": "Cardio", "exam_type": "partiel"},
        }, ensure_ascii=False),
        encoding="utf-8",
    )

    report = diagnostics.build_report()

    assert [p["source_url"] for p in report["pending"]] == ["https://x/2"]
    assert report["annales"] == []


def _broken_verified_exam(*, source_url, title, error_message_fragment):
    # Missing verdict_ia trips assert_verified_exam's mandatory-verification-IA
    # check, which import_verified_directory catches and records in
    # result["errors"] instead of raising — this is how a file becomes
    # "blocked" without ever being archived out of VERIFIED_DIR.
    return {
        "schema_version": 1, "faculty": "Fac", "level": "N1", "year": 2026,
        "title": title, "dp_context": {},
        "questions": [{
            "id": "q1", "type_question": "QRU", "enonce": "Q?", "propositions": [
                {"id": error_message_fragment, "texte": "a", "reponse_uness": True, "verdict_ia": None,
                 "explication_ia": "e", "confiance_ia": 0.9, "statut": "concordant"}
            ], "verification_status": "verified",
        }],
        "provenance": {"source": "Gemini+UNESS", "source_url": source_url,
                       "collected_at": "2026-01-01T00:00:00+00:00", "collection_status": "submitted"},
        "metadata": {"subject": "Cardio", "exam_type": "partiel"},
    }


def test_build_report_keeps_blocked_quizzes_separate_across_annales_sharing_a_label(uness_dirs):
    # Two unrelated annales that both happen to have a "DP1" quiz which fails
    # import validation. A label-only key in _blocked_titles would let the
    # second one processed silently clobber the first's entry in the dict —
    # the clobbered annale's DP1 would then fall through to
    # "never_attempted", hiding a real import failure.
    session_a = uness_dirs["to_review"] / "session-A"
    session_b = uness_dirs["to_review"] / "session-B"
    session_a.mkdir()
    session_b.mkdir()
    _bridge_file(
        session_a / "dp1.json", source_url="https://x/1", collected_at="2026-01-01T00:00:00+00:00", title="DP1\nTest"
    )
    _bridge_file(
        session_b / "dp1.json", source_url="https://x/2", collected_at="2026-01-01T00:00:00+00:00", title="DP1\nTest"
    )

    verified = uness_dirs["verified"]
    verified.joinpath("dp1-annale-a.json").write_text(
        json.dumps(
            _broken_verified_exam(
                source_url="https://x/1", title="Cardio — Fac — 2026 — DP1", error_message_fragment="pA"
            ),
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    verified.joinpath("dp1-annale-b.json").write_text(
        json.dumps(
            _broken_verified_exam(
                source_url="https://x/2", title="Neuro — Fac — 2026 — DP1", error_message_fragment="pB"
            ),
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    annale_id_a = local_store.create_uness_annale(
        source_url="https://x/1", collected_at="2026-01-01T00:00:00+00:00", faculte="Fac",
        niveau="N1", annee=2026, matiere="Cardio", titre="Cardio — Fac — 2026", type_annale="matiere",
    )
    annale_id_b = local_store.create_uness_annale(
        source_url="https://x/2", collected_at="2026-01-01T00:00:00+00:00", faculte="Fac",
        niveau="N1", annee=2026, matiere="Neuro", titre="Neuro — Fac — 2026", type_annale="matiere",
    )

    report = diagnostics.build_report()

    entry_a = next(a for a in report["annales"] if a["annale"]["id"] == annale_id_a)
    entry_b = next(a for a in report["annales"] if a["annale"]["id"] == annale_id_b)
    quizzes_a = {q["title"]: q for q in entry_a["quizzes"]}
    quizzes_b = {q["title"]: q for q in entry_b["quizzes"]}

    assert quizzes_a["DP1"]["status"] == "blocked"
    assert quizzes_b["DP1"]["status"] == "blocked"
    assert "pA" in quizzes_a["DP1"]["detail"]["error"]
    assert "pB" in quizzes_b["DP1"]["detail"]["error"]


def test_build_report_skips_a_legacy_list_shaped_verified_file_without_crashing(uness_dirs):
    # A real file on disk (UNESS/vérifiés/exam_hepato_gastro_corriges.json) is an
    # old bundled multi-quiz export whose top-level JSON is a *list* of quiz
    # dicts, not the canonical single UnessExam dict every other verified file
    # is. import_verified_directory() already fails to import it for its own
    # unrelated reason (no matching bridge file for the quiz) and records that
    # in result["errors"] — but _blocked_titles used to blindly call .get() on
    # whatever json.loads() returned for that error's file, crashing with
    # AttributeError: 'list' object has no attribute 'get'. No bridge is
    # created here on purpose, so this reproduces the "no matching bridge"
    # failure path that puts the file into result["errors"].
    verified = uness_dirs["verified"]
    verified.joinpath("legacy-bundle.json").write_text(
        json.dumps(
            [
                {
                    "quiz_title": "SQI1",
                    "questions": [{"id": "q1", "type_question": "QRU", "enonce": "Q?", "propositions": []}],
                }
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    report = diagnostics.build_report()  # must not raise

    assert report["annales"] == []
    for entry in report["annales"]:
        assert all(q["status"] != "blocked" for q in entry["quizzes"])


def test_build_report_surfaces_unattributable_errors_instead_of_dropping_them(uness_dirs):
    # A raw AI response (has "quiz_title"/"questions", not the canonical
    # "title"/"provenance" shape every other verified file has) whose Gemini
    # conversion fails because no bridge file matches its quiz_title. Unlike
    # the legacy-list case above, this is a genuinely actionable failure — the
    # quiz WAS submitted and IS failing to import — but _blocked_titles has no
    # (source_url, label) to key it under, since a raw payload never carries
    # "title"/"provenance". It must show up in build_report()'s
    # "unattributed_errors" instead of silently vanishing (which used to leave
    # it misreported as "never_attempted", telling the user it was never even
    # submitted).
    verified = uness_dirs["verified"]
    verified.joinpath("raw-response.json").write_text(
        json.dumps(
            {
                "quiz_title": "SQI1\nTest",
                "questions": [
                    {
                        "id": "q1",
                        "type_question": "QRU",
                        "enonce": "Q?",
                        "propositions": [{"id": "p1", "texte": "a", "reponse_officielle": True}],
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    # No bridge file exists anywhere (à_vérifier/ and archives/ are both
    # empty), so the conversion fails with "Aucun bridge ne contient le
    # quiz...".

    report = diagnostics.build_report()

    assert report["annales"] == []
    assert len(report["unattributed_errors"]) == 1
    unattributed = report["unattributed_errors"][0]
    assert unattributed["file"] == "raw-response.json"
    assert "Aucun bridge ne contient le quiz" in unattributed["error"]
