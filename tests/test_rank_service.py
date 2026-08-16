from backend.core.practice.rank_service import apply_rank_decision, resolve_rank


def test_official_rank_wins_over_gemini_and_admin():
    decision = resolve_rank(
        official_rank="B",
        gemini_rank="A",
        gemini_confidence=0.99,
        admin_rank="A",
    )

    assert decision.rank == "B"
    assert decision.source == "official"
    assert decision.confidence == 1.0


def test_reliable_gemini_wins_over_conflicting_admin_with_trace():
    decision = resolve_rank(
        gemini_rank="A",
        gemini_confidence=0.91,
        gemini_evidence=["OIC-1"],
        admin_rank="B",
        admin_reason="Correction manuelle à vérifier",
    )

    assert decision.rank == "A"
    assert decision.source == "gemini"
    assert decision.status == "admin_conflict"
    assert decision.alternatives[-1]["rank"] == "B"


def test_low_confidence_or_ambiguous_gemini_does_not_resolve_rank():
    assert resolve_rank(gemini_rank="A", gemini_confidence=0.849).status == "unknown"
    assert resolve_rank(gemini_rank="A", gemini_confidence=0.99, gemini_ambiguous=True).status == "ambiguous"


def test_admin_is_only_used_when_no_reliable_inference_exists():
    decision = resolve_rank(admin_rank="B", admin_reason="Revue expert")
    payload = apply_rank_decision({"id": "q1"}, decision)

    assert payload["rank"] == "B"
    assert payload["rank_source"] == "admin"
    assert payload["rank_rationale"] == "Revue expert"
