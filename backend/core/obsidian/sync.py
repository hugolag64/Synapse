"""
VaultSyncService — Synapse ↔ Obsidian frontmatter sync.

Problème résolu :
  Quand une note est créée directement dans Obsidian (pas via Synapse),
  les champs notion_id et synapse_id restent vides.

Solution :
  Scan du vault → identification des notes non liées →
  matching par item number (strict) ou titre (fuzzy) →
  écriture des champs manquants dans le frontmatter.

Deux modes de match :
  - "strict"  : item number exact depuis le nom de fichier ou le frontmatter
                → appliqué automatiquement (démarrage + bouton manuel)
  - "fuzzy"   : titre normalisé approchant
                → proposé à l'utilisateur pour confirmation

Garanties :
  - Ne touche jamais au body ni aux autres champs du frontmatter.
  - Ne modifie pas une note déjà liée (notion_id + synapse_id présents).
  - Idempotent : relancer deux fois ne fait pas de doublon.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from loguru import logger

from backend.core.obsidian.templates import _split_frontmatter, _parse_fm_lines, _rebuild_fm


# ── Modèles ───────────────────────────────────────────────────────────────────

@dataclass
class NoteMatch:
    """Résultat d'un matching entre une note Obsidian et un cours Synapse."""
    path: Path
    course_id: str
    course_title: str
    item_number: str          # display_item_number du cours ("339", "12.3"…)
    confidence: str           # "strict" | "fuzzy"
    reason: str               # explication lisible du match


@dataclass
class ScanResult:
    """Résultat complet d'un scan du vault."""
    confirmed: list[NoteMatch]   # matchs stricts → appliqués automatiquement
    uncertain: list[NoteMatch]   # matchs flous   → demande confirmation utilisateur
    skipped: int                 # notes déjà liées ou sans match
    errors: list[str]            # erreurs de lecture/parsing


# ── Service ───────────────────────────────────────────────────────────────────

class VaultSyncService:
    """
    Scanne le vault Obsidian pour trouver les notes sans notion_id/synapse_id
    et les lier aux cours Synapse correspondants.
    """

    # Glob relatif dans le vault pour trouver les notes de cours
    _COURS_GLOB = "01 - Cours EDN/*/Cours/*.md"

    # Regex pour extraire item + titre du nom de fichier
    # Exemples : "339 - SCA ST+" → item="339", titre="SCA ST+"
    #            "12.3 - Méningite" → item="12.3", titre="Méningite"
    _FILENAME_RE = re.compile(r"^(\d+(?:[.,]\d+)?)\s*[-–]\s*(.+)$")

    # ── Scan ─────────────────────────────────────────────────────────────────

    def scan_unlinked_notes(self, vault_path: str, courses: list) -> ScanResult:
        """
        Parcourt le vault et identifie les notes sans notion_id/synapse_id.

        vault_path : chemin absolu vers le vault Obsidian
        courses    : liste d'objets Cours (data_store.cours)

        Retourne un ScanResult avec :
          - confirmed  : item number exact → on peut appliquer sans demander
          - uncertain  : titre approchant  → l'utilisateur confirme
          - skipped    : notes déjà liées ou sans aucun match possible
          - errors     : fichiers illisibles ou erreurs de parsing
        """
        vault = Path(vault_path)
        if not vault.exists():
            return ScanResult([], [], 0, [f"Vault introuvable : {vault_path}"])

        # ── Index des cours ───────────────────────────────────────────────────
        by_item:  dict[str, object] = {}   # "339" → Cours
        by_title: dict[str, list[object]] = {}   # titre normalisé → cours candidats

        for c in courses:
            item = str(getattr(c, "display_item_number", "") or "").strip()
            if item:
                by_item[item] = c
                # Aussi indexer sans virgule pour tolérer "12,3" vs "12.3"
                by_item[item.replace(",", ".")] = c
                by_item[item.replace(".", ",")] = c

            title_norm = self._normalize(c.title or "")
            if title_norm:
                by_title.setdefault(title_norm, []).append(c)

        # ── Scan des fichiers ─────────────────────────────────────────────────
        confirmed: list[NoteMatch] = []
        uncertain: list[NoteMatch] = []
        skipped   = 0
        errors: list[str] = []

        md_files = list(vault.glob(self._COURS_GLOB))
        logger.info(f"Scan vault : {len(md_files)} notes dans {self._COURS_GLOB}")

        for md_path in md_files:
            try:
                result = self._process_note(md_path, by_item, by_title)
                if result is None:
                    skipped += 1
                elif result.confidence == "strict":
                    confirmed.append(result)
                else:
                    uncertain.append(result)
            except Exception as exc:
                errors.append(f"{md_path.name}: {exc}")
                logger.warning(f"Erreur scan {md_path.name}: {exc}")

        logger.info(
            f"Résultat scan : {len(confirmed)} stricts, "
            f"{len(uncertain)} flous, {skipped} ignorés, {len(errors)} erreurs"
        )
        return ScanResult(confirmed, uncertain, skipped, errors)

    def _process_note(
        self,
        path: Path,
        by_item: dict,
        by_title: dict,
    ) -> Optional[NoteMatch]:
        """
        Analyse une note et retourne un NoteMatch ou None.

        None si :
          - déjà liée (notion_id + synapse_id tous deux présents et non vides)
          - aucun match trouvé
        """
        text = path.read_text(encoding="utf-8")
        fm_raw, _ = _split_frontmatter(text)
        fm = {k: v for k, v in _parse_fm_lines(fm_raw)} if fm_raw else {}

        # ── Déjà liée → skip ─────────────────────────────────────────────────
        has_notion  = bool(str(fm.get("notion_id", "")).strip())
        has_synapse = bool(str(fm.get("synapse_id", "")).strip())
        if has_notion and has_synapse:
            return None

        # ── Extraction depuis le nom de fichier ───────────────────────────────
        stem = path.stem          # "339 - SCA ST+"
        item_from_filename = ""
        title_from_filename = stem

        m = self._FILENAME_RE.match(stem)
        if m:
            item_from_filename  = m.group(1).strip().replace(",", ".")
            title_from_filename = m.group(2).strip()

        # ── Priorité 1 : item du nom de fichier (strict) ──────────────────────
        if item_from_filename and item_from_filename in by_item:
            c = by_item[item_from_filename]
            return NoteMatch(
                path=path,
                course_id=c.id,
                course_title=c.title,
                item_number=str(getattr(c, "display_item_number", "") or item_from_filename),
                confidence="strict",
                reason=f"ITEM {item_from_filename} (nom de fichier)",
            )

        # ── Priorité 2 : item du frontmatter (strict) ─────────────────────────
        fm_item = str(fm.get("item", "")).strip().replace(",", ".")
        if fm_item and fm_item in by_item:
            c = by_item[fm_item]
            return NoteMatch(
                path=path,
                course_id=c.id,
                course_title=c.title,
                item_number=str(getattr(c, "display_item_number", "") or fm_item),
                confidence="strict",
                reason=f"ITEM {fm_item} (frontmatter)",
            )

        # ── Priorité 3 : titre normalisé (fuzzy → uncertain) ──────────────────
        # Essaie d'abord le titre du frontmatter, puis du nom de fichier
        for raw_title in [fm.get("title", ""), title_from_filename]:
            norm = self._normalize(str(raw_title))
            candidates = by_title.get(norm, [])
            if len(candidates) == 1:
                c = candidates[0]
                return NoteMatch(
                    path=path,
                    course_id=c.id,
                    course_title=c.title,
                    item_number=str(getattr(c, "display_item_number", "") or ""),
                    confidence="fuzzy",
                    reason=f"Titre approchant : « {raw_title[:50]} »",
                )

        return None  # aucun match

    # ── Application des matchs ────────────────────────────────────────────────

    def apply_matches_and_get_paths(
        self, matches: list[NoteMatch]
    ) -> list[tuple[str, Path]]:
        """
        Écrit les champs frontmatter ET retourne la liste (course_id, path)
        des notes effectivement mises à jour, pour que l'appelant puisse
        mettre à jour la propriété Notion "Obsidian" et le store local.
        """
        updated: list[tuple[str, Path]] = []
        for match in matches:
            try:
                self._write_frontmatter_fields(match.path, {
                    "notion_id":  match.course_id,
                    "synapse_id": match.course_id,
                    "item":       match.item_number,
                })
                updated.append((match.course_id, match.path))
                logger.success(
                    f"✓ Frontmatter mis à jour : {match.path.name} → {match.course_id[:8]}…"
                )
            except Exception as exc:
                logger.error(f"Impossible d'écrire {match.path}: {exc}")
        return updated

    def apply_matches(self, matches: list[NoteMatch]) -> int:
        """
        Écrit notion_id, synapse_id et item dans le frontmatter
        des notes listées. Retourne le nombre de notes mises à jour.

        Idempotent : si les champs sont déjà corrects, le fichier
        est réécrit avec les mêmes valeurs (comportement sûr).
        """
        count = 0
        for match in matches:
            try:
                self._write_frontmatter_fields(match.path, {
                    "notion_id":  match.course_id,
                    "synapse_id": match.course_id,
                    "item":       match.item_number,
                })
                count += 1
                logger.success(
                    f"✓ Frontmatter mis à jour : {match.path.name} → {match.course_id[:8]}…"
                )
            except Exception as exc:
                logger.error(f"Impossible d'écrire {match.path}: {exc}")
        return count

    # ── Écriture frontmatter (partielle, non-destructive) ─────────────────────

    def _write_frontmatter_fields(self, path: Path, updates: dict):
        """
        Met à jour des champs spécifiques dans le frontmatter d'une note
        Obsidian SANS toucher au body ni aux autres champs.

        Si la note n'a pas de frontmatter, en crée un minimal.
        """
        text = path.read_text(encoding="utf-8")
        fm_raw, body = _split_frontmatter(text)

        if fm_raw:
            fields = _parse_fm_lines(fm_raw)
        else:
            fields = []

        # Mise à jour des champs existants
        seen = {k for k, _ in fields}
        new_fields: list[tuple] = []
        for k, v in fields:
            new_fields.append((k, updates.get(k, v)))

        # Ajout des champs manquants (non vides)
        for k, v in updates.items():
            if k not in seen and v:
                new_fields.append((k, v))

        new_fm   = _rebuild_fm(new_fields, {})
        new_text = new_fm + "\n" + body
        path.write_text(new_text, encoding="utf-8")

    # ── Normalisation titre ───────────────────────────────────────────────────

    @staticmethod
    def _normalize(text: str) -> str:
        """
        Normalise un titre pour comparaison floue :
        minuscules, sans accents, sans ponctuation, espaces réduits.
        """
        text = text.lower().strip()
        # Décomposer les accents
        text = unicodedata.normalize("NFD", text)
        text = "".join(c for c in text if unicodedata.category(c) != "Mn")
        # Supprimer la ponctuation sauf tiret et chiffres
        text = re.sub(r"[^\w\s\-]", "", text)
        # Normaliser les espaces
        text = re.sub(r"\s+", " ", text).strip()
        return text


# ── Singleton ─────────────────────────────────────────────────────────────────

vault_sync_service = VaultSyncService()
