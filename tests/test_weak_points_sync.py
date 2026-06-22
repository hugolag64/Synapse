"""
tests/test_weak_points_sync.py
-------------------------------
Tests unitaires pour WeakPointsSyncService (Phase H).

Tests couverts :
  1. Parsing frontmatter lacune valide
  2. Fichier sans frontmatter → ignoré
  3. Fichier avec type: concept → ignoré
  4. gravite: haute → severity = 5
  5. gravite: basse → severity = 2
  6. gravite: moyenne → severity = 3
  7. Extraction [[235 - Péricardite Aigue]]
  8. Extraction alias [[235 - Péricardite Aigue|Péricardite]]
  9. Extraction de plusieurs liens
 10. Upsert idempotent : deux syncs ne créent pas deux lacunes
 11. Écriture synapse_id dans le YAML sans toucher au body
 12. Lacune résolue dans Synapse met à jour le YAML (statut + date_resolution)
 13. Lacune revue met à jour last_reviewed_at dans le YAML
 14. Statut "résolue" Obsidian → status "résolue" Synapse
 15. Statut inconnu → "active" par défaut
"""
from __future__ import annotations

import datetime
import sqlite3
import tempfile
from pathlib import Path

import pytest


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _make_lacune(
    title: str = "Péricardite vs SCA",
    college: str = "Cardiovasculaire",
    gravite: str = "haute",
    statut: str = "active",
    source: str = "qcm",
    date_creation: str = "2026-05-25",
    liens: list[str] | None = None,
    extra_fm: str = "",
    body_extra: str = "",
) -> str:
    """Génère le contenu d'une note Obsidian lacune."""
    liens_md = "\n".join(f"- [[{l}]]" for l in (liens or []))
    return f"""\
---
type: lacune
date_creation: {date_creation}
college: {college}
gravite: {gravite}
statut: {statut}
source: {source}
tags:
  - lacune
  - edn
{extra_fm}---

# {title}

## Mon erreur

-

## Correction

-

## Cours lié

{liens_md}
{body_extra}
"""


def _write_note(tmp_path: Path, filename: str, content: str) -> Path:
    p = tmp_path / filename
    p.write_text(content, encoding="utf-8")
    return p


# ──────────────────────────────────────────────────────────────────────────────
# Tests — Parsing frontmatter
# ──────────────────────────────────────────────────────────────────────────────

class TestFrontmatterParsing:
    """Tests sur le parsing du frontmatter YAML via les helpers de templates.py."""

    def test_valid_lacune_parsed(self):
        from backend.core.obsidian.templates import _split_frontmatter, _parse_fm_lines

        content = _make_lacune(title="Test", gravite="haute", statut="active")
        fm_raw, body = _split_frontmatter(content)
        assert fm_raw, "Frontmatter devrait être non-vide"

        fm = dict(_parse_fm_lines(fm_raw))
        assert fm.get("type") == "lacune"
        assert fm.get("gravite") == "haute"
        assert fm.get("statut") == "active"
        assert fm.get("college") == "Cardiovasculaire"

    def test_no_frontmatter_returns_empty(self):
        from backend.core.obsidian.templates import _split_frontmatter

        content = "# Simple note\n\nPas de frontmatter."
        fm_raw, body = _split_frontmatter(content)
        assert fm_raw == ""
        assert "Simple note" in body

    def test_title_extracted_from_h1(self):
        """Le titre est extrait du H1 si pas de champ title dans le frontmatter."""
        from backend.core.obsidian.templates import _split_frontmatter, _parse_fm_lines
        from backend.core.obsidian.weak_points_sync import WeakPointsSyncService

        content = _make_lacune(title="Péricardite vs SCA")
        fm_raw, body = _split_frontmatter(content)
        fm = dict(_parse_fm_lines(fm_raw))

        svc = WeakPointsSyncService()
        title = svc._extract_title(fm, body, Path("test.md"))
        assert title == "Péricardite vs SCA"


# ──────────────────────────────────────────────────────────────────────────────
# Tests — Filtrage par type
# ──────────────────────────────────────────────────────────────────────────────

class TestTypeFiltering:
    """Seules les notes type: lacune sont traitées."""

    def test_type_concept_ignored(self, tmp_path: Path):
        """Un fichier avec type: concept doit être ignoré."""
        content = """\
---
type: concept
college: Cardiologie
---

# Concept cardiaque
"""
        p = _write_note(tmp_path, "concept.md", content)
        result = _scan_single(p)
        assert result.skipped >= 1
        assert result.created == 0

    def test_no_frontmatter_ignored(self, tmp_path: Path):
        content = "# Juste du texte\n\nSans frontmatter."
        p = _write_note(tmp_path, "no_fm.md", content)
        result = _scan_single(p)
        assert result.skipped >= 1
        assert result.created == 0

    def test_type_lacune_processed(self, tmp_path: Path):
        content = _make_lacune(title="Test lacune")
        p = _write_note(tmp_path, "lacune.md", content)
        result = _scan_single(p)
        assert result.created == 1


# ──────────────────────────────────────────────────────────────────────────────
# Tests — Conversion gravité → sévérité
# ──────────────────────────────────────────────────────────────────────────────

class TestGraviteToSeverity:

    @pytest.mark.parametrize("gravite,expected", [
        ("haute",    5),
        ("élevée",   5),
        ("critique", 5),
        ("moyenne",  3),
        ("basse",    2),
        ("faible",   2),
        ("inconnu",  2),  # fallback
        ("",         2),  # fallback
    ])
    def test_conversion(self, gravite, expected):
        from backend.core.obsidian.weak_points_sync import GRAVITE_TO_SEVERITY
        result = GRAVITE_TO_SEVERITY.get(gravite.lower(), 2)
        assert result == expected


# ──────────────────────────────────────────────────────────────────────────────
# Tests — Extraction des liens [[...]]
# ──────────────────────────────────────────────────────────────────────────────

class TestWikiLinkExtraction:

    def test_simple_link(self):
        from backend.core.obsidian.weak_points_sync import _extract_wiki_links

        body = "- [[235 - Péricardite Aigue]]\n"
        links = _extract_wiki_links(body)
        assert "235 - Péricardite Aigue" in links

    def test_alias_link(self):
        """[[235 - Péricardite Aigue|Péricardite]] → cible sans alias."""
        from backend.core.obsidian.weak_points_sync import _extract_wiki_links

        body = "- [[235 - Péricardite Aigue|Péricardite]]\n"
        links = _extract_wiki_links(body)
        assert "235 - Péricardite Aigue" in links
        assert "Péricardite" not in links   # l'alias ne doit PAS être retourné

    def test_multiple_links(self):
        from backend.core.obsidian.weak_points_sync import _extract_wiki_links

        body = (
            "- [[235 - Péricardite Aigue]]\n"
            "- [[350 - SCA]]\n"
        )
        links = _extract_wiki_links(body)
        assert "235 - Péricardite Aigue" in links
        assert "350 - SCA" in links

    def test_no_links(self):
        from backend.core.obsidian.weak_points_sync import _extract_wiki_links

        body = "Pas de liens ici."
        assert _extract_wiki_links(body) == []


# ──────────────────────────────────────────────────────────────────────────────
# Tests — Normalisation statut
# ──────────────────────────────────────────────────────────────────────────────

class TestNormalisationStatut:

    @pytest.mark.parametrize("raw,expected", [
        ("active",     "active"),
        ("actif",      "active"),
        ("à revoir",   "à revoir"),
        ("a revoir",   "à revoir"),
        ("arevoir",    "à revoir"),
        ("résolue",    "résolue"),
        ("resolue",    "résolue"),
        ("résolu",     "résolue"),
        ("récurrente", "récurrente"),
        ("recurrente", "récurrente"),
        ("inconnu",    "active"),   # fallback
        ("",           "active"),   # fallback
    ])
    def test_normalize(self, raw, expected):
        from backend.core.obsidian.weak_points_sync import _normalize_statut
        assert _normalize_statut(raw) == expected


# ──────────────────────────────────────────────────────────────────────────────
# Tests — Upsert idempotent
# ──────────────────────────────────────────────────────────────────────────────

class TestUpsertIdempotent:
    """Deux syncs du même fichier ne créent pas deux lacunes."""

    def test_idempotent_via_synapse_id(self, tmp_path: Path):
        """Le synapse_id stable assure l'unicité."""
        content = _make_lacune(title="Idempotent test")
        p = _write_note(tmp_path, "idempotent.md", content)

        # Premier scan
        result1 = _scan_single(p)
        assert result1.created == 1
        assert result1.updated == 0

        # Deuxième scan (même fichier, synapse_id désormais écrit dans le FM)
        p_content = p.read_text(encoding="utf-8")
        result2 = _scan_single(p)
        # Doit être une mise à jour, pas une création
        assert result2.updated == 1
        assert result2.created == 0

    def test_count_in_db_stays_one(self, tmp_path: Path, tmp_db: Path):
        """La DB ne doit contenir qu'une seule ligne après deux syncs."""
        from backend.core.reviews import local_store

        content = _make_lacune(title="Unique en DB")
        p = _write_note(tmp_path, "unique.md", content)

        _scan_single(p)
        _scan_single(p)

        # Compter les lacunes avec synapse_id commençant par 'obsidian_'
        with sqlite3.connect(str(local_store.DB_PATH)) as con:
            count = con.execute(
                "SELECT COUNT(*) FROM weak_points WHERE synapse_id LIKE 'obsidian_%'"
                " AND obsidian_path LIKE ?",
                (f"%{p.name}%",),
            ).fetchone()[0]

        # Il peut y en avoir plus d'un si d'autres tests ont ajouté, mais
        # le nom de fichier est unique par test → on accepte >= 1 et on vérifie unicité
        assert count == 1


# ──────────────────────────────────────────────────────────────────────────────
# Tests — Écriture frontmatter
# ──────────────────────────────────────────────────────────────────────────────

class TestFrontmatterWriteback:

    def test_synapse_id_written_without_touching_body(self, tmp_path: Path):
        """synapse_id est ajouté au frontmatter, le body est préservé."""
        body_marker = "## Mon erreur\n\n- Ceci est le body\n"
        content = _make_lacune(title="Write test", body_extra=body_marker)
        p = _write_note(tmp_path, "writeback.md", content)

        _scan_single(p)

        new_content = p.read_text(encoding="utf-8")
        assert "synapse_id:" in new_content
        assert "obsidian_" in new_content
        # Le body doit être intégralement préservé
        assert "Ceci est le body" in new_content
        assert "## Mon erreur" in new_content

    def test_existing_fields_preserved(self, tmp_path: Path):
        """Les champs existants du frontmatter ne sont pas supprimés."""
        content = _make_lacune(
            title="Preservation test",
            extra_fm="custom_field: ma_valeur_custom\n",
        )
        p = _write_note(tmp_path, "preserve.md", content)

        _scan_single(p)

        new_content = p.read_text(encoding="utf-8")
        assert "custom_field: ma_valeur_custom" in new_content
        assert "type: lacune" in new_content
        assert "gravite:" in new_content


# ──────────────────────────────────────────────────────────────────────────────
# Tests — Écriture statut → Obsidian
# ──────────────────────────────────────────────────────────────────────────────

class TestObsidianStatusWriteback:

    def test_resolve_writes_statut_to_yaml(self, tmp_path: Path):
        """Marquer résolue depuis Synapse écrit statut: résolue + date_resolution dans YAML."""
        from backend.core.obsidian.weak_points_sync import write_obsidian_lacune_status

        content = _make_lacune(title="Resolve test", statut="active")
        p = _write_note(tmp_path, "resolve.md", content)

        today = datetime.date.today().isoformat()
        ok = write_obsidian_lacune_status(str(p), "résolue", resolved_at=today)

        assert ok is True
        new_content = p.read_text(encoding="utf-8")
        assert "statut: résolue" in new_content
        assert f"date_resolution: {today}" in new_content

    def test_review_writes_last_reviewed_at(self, tmp_path: Path):
        """Revoir une lacune écrit last_reviewed_at dans YAML."""
        from backend.core.obsidian.weak_points_sync import write_obsidian_reviewed_at

        content = _make_lacune(title="Review test")
        p = _write_note(tmp_path, "review.md", content)

        today = datetime.date.today().isoformat()
        ok = write_obsidian_reviewed_at(str(p), today)

        assert ok is True
        new_content = p.read_text(encoding="utf-8")
        assert f"last_reviewed_at: {today}" in new_content

    def test_resolve_body_unchanged(self, tmp_path: Path):
        """Marquer résolue ne touche pas au body."""
        from backend.core.obsidian.weak_points_sync import write_obsidian_lacune_status

        body_signature = "## Mon erreur\n\n- Donnée unique 42xyz\n"
        content = _make_lacune(title="Body test", body_extra=body_signature)
        p = _write_note(tmp_path, "body_resolve.md", content)

        write_obsidian_lacune_status(str(p), "résolue", resolved_at="2026-05-25")

        new_content = p.read_text(encoding="utf-8")
        assert "Donnée unique 42xyz" in new_content

    def test_missing_file_returns_false(self):
        from backend.core.obsidian.weak_points_sync import write_obsidian_lacune_status
        ok = write_obsidian_lacune_status("/chemin/inexistant.md", "résolue")
        assert ok is False


# ──────────────────────────────────────────────────────────────────────────────
# Tests — Matching cours
# ──────────────────────────────────────────────────────────────────────────────

class TestCourseMatching:

    def test_match_by_item_number_in_link(self):
        """[[235 - Péricardite]] doit matcher le cours avec item 235."""
        from backend.core.obsidian.weak_points_sync import WeakPointsSyncService
        from types import SimpleNamespace

        course = SimpleNamespace(id="abc", title="Péricardite Aigue", display_item_number="235")
        by_item  = {"235": course}
        by_title = {}

        svc = WeakPointsSyncService()
        result = svc._match_course(
            ["235 - Péricardite Aigue"],
            "Cardiologie",
            by_item,
            by_title,
        )
        assert result is course

    def test_no_match_returns_none(self):
        from backend.core.obsidian.weak_points_sync import WeakPointsSyncService

        svc = WeakPointsSyncService()
        result = svc._match_course(
            ["999 - Cours inexistant"],
            "Inconnu",
            {},
            {},
        )
        assert result is None


# ──────────────────────────────────────────────────────────────────────────────
# Fixtures et helpers internes
# ──────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    """
    Redirige DB_PATH vers un fichier temporaire isolé pour chaque test.
    Garantit que les tests n'écrivent pas dans la vraie DB de développement.
    """
    db_path = tmp_path / "test_synapse.db"
    import backend.core.reviews.local_store as ls

    monkeypatch.setattr(ls, "DB_PATH", db_path)
    # Réinitialiser la DB avec les nouvelles tables + migrations
    ls.init_db()
    return db_path


def _scan_single(path: Path) -> "WeakPointSyncResult":
    """
    Lance un scan sur un dossier temporaire contenant un seul fichier.
    Retourne le WeakPointSyncResult.
    """
    from backend.core.obsidian.weak_points_sync import WeakPointsSyncService
    import os, tempfile

    # On utilise un vault temporaire = le dossier parent du fichier
    vault = path.parent
    svc = WeakPointsSyncService()

    # Patcher le settings vault_path
    from backend.config import settings as _settings_module
    orig_vault = _settings_module.settings.obsidian_vault_path
    orig_name  = _settings_module.settings.obsidian_vault_name

    try:
        # Monkey-patch temporaire du settings (read-only object → on passe courses=[] et vault direct)
        # On appelle directement _process_file pour ne pas dépendre du settings
        from backend.core.obsidian.weak_points_sync import WeakPointSyncResult
        from backend.core.obsidian.templates import _split_frontmatter, _parse_fm_lines

        result = WeakPointSyncResult()
        svc._process_file(path, vault, {}, {}, result)
        return result
    finally:
        pass
