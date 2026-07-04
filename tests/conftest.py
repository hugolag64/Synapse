"""Pytest configuration and shared fixtures."""
import os

# Set up required environment variables for testing BEFORE any imports
os.environ.setdefault("NOTION_TOKEN", "test-token")
os.environ.setdefault("DATABASE_COURS_ID", "test-db-id")
os.environ.setdefault("DATABASE_UE_ID", "test-ue-id")
os.environ.setdefault("MEDICINE_DIR", "")
os.environ.setdefault("FAC_DIR", "")
