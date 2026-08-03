"""Pytest configuration and shared fixtures."""
import os

import pytest

# Set up required environment variables for testing BEFORE any imports
os.environ.setdefault("NOTION_TOKEN", "test-token")
os.environ.setdefault("DATABASE_COURS_ID", "test-db-id")
os.environ.setdefault("DATABASE_UE_ID", "test-ue-id")
os.environ.setdefault("MEDICINE_DIR", "")
os.environ.setdefault("FAC_DIR", "")


@pytest.fixture(autouse=True)
def _no_real_uness_item_classification(monkeypatch):
    """`import_uness_exam` calls Gemini (item_classifier) for any exam without
    item_number. Settings loads GEMINI_API_KEY from the real .env regardless of
    the test env vars above, so an un-mocked test here would fire a real, paid
    API call. Default to "non classifié" everywhere; a test that specifically
    wants to exercise classification can re-patch this locally."""
    monkeypatch.setattr(
        "backend.core.uness.import_service._classify_exam_items",
        lambda exam, matiere: ("", ()),
        raising=False,
    )
