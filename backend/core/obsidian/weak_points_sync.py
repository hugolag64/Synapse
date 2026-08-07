"""
WeakPointsSyncService — Synapse ↔ Obsidian (lacunes)
------------------------------------------------------
Scans le vault Obsidian pour les notes avec `type: lacune` en frontmatter,
extrait les données, matche avec les cours Synapse, et upsert dans SQLite.

Flux :
  Obsidian *.md (type: lacune)
    ↓ scan frontmatter + [[liens]]
  WeakPointsSyncService.sync()
    ↓ matching cours Synapse
    ↓ upsert SQLite weak_points
    ↓ écriture synapse_id dans le frontmatter
  WeakPointSyncResult

Garanties :
  - Ne touche jamais au body ni aux autres champs YAML.
  - Idempotent : relancer deux fois ne crée pas de doublon.
  - Utilise un ID stable (hash du chemin absolu) pour éviter les doublons.
  - Compatible Windows (chemins avec backslash).
"""
from __future__ import annotations

import hashlib
import re
import datetime
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from loguru import logger

from backend.config.settings import settings
from backend.core.obsidian.templates import _split_frontmatter, _parse_fm_lines


# ── Constantes ────────────────────────────────────────────────────────────────

GRAVITE_TO_SEVERITY: dict[str, int] = {
    "basse":    2,
    "faible":   2,
    "légère":   2,
    "legere":   2,
    "moyenne":  3,
    "moyen":    3,
    "haute":    5,
    "élevée":   5,
    "elevee":   5,
    "critique": 5,
    "très haute": 5,
}

# Mapping sévérité Synapse → gravité Obsidian
_SEV_TO_GRAVITE: dict[int, str] = {
    1: "basse",
    2: "basse",
    3: "moyenne",
    4: "haute",
    5: "critique",
}

# Mapping statut Synapse → sous-dossier Obsidian
_STATUS_TO_FOLDER: dict[str, str] = {
    "active":     "Actives",
    "à revoir":   "À revoir",
    "résolue":    "Corrigées",
    "récurrente": "Actives",
}

# Caractères interdits dans les noms de fichiers Windows
_WIN_FORBIDDEN_WP = re.compile(r'[<>:"/\\|?*\x00-\x1f]')

# Regex pour extraire les liens Obsidian [[target]] ou [[target|alias]]
_WIKI_LINK_RE = re.compile(r'\[\[([^\]|]+?)(?:\|[^\]]+?)?\]\]')

# Regex pour extraire le H1 du body
_H1_RE = re.compile(r'^#\s+(.+)', re.MULTILINE)

# Statuts valides Synapse
_VALID_STATUSES = {"active", "à revoir", "résolue", "récurrente"}

# Mapping statut Obsidian → statut Synapse
_STATUT_MAP: dict[str, str] = {
    "active":      "active",
    "actif":       "active",
    "actifs":      "active",
    "à revoir":    "à revoir",
    "a revoir":    "à revoir",
    "arevoir":     "à revoir",
    "a_revoir":    "à revoir",
    "revoir":      "à revoir",
    "résolue":     "résolue",
    "resolue":     "résolue",
    "résolu":      "résolue",
    "resolu":      "résolue",
    "resolved":    "résolue",
    "récurrente":  "récurrente",
    "recurrente":  "récurrente",
    "récurrent":   "récurrente",
    "recurrent":   "récurrente",
}


# ── Modèle résultat ───────────────────────────────────────────────────────────

@dataclass
class WeakPointSyncResult:
    """Résultat d'une synchronisation vault → SQLite."""
    created:   int = 0
    updated:   int = 0
    skipped:   int = 0
    unmatched: list[str] = field(default_factory=list)
    errors:    list[str] = field(default_factory=list)

    @property
    def total(self) -> int:
        return self.created + self.updated

    def summary(self) -> str:
        parts = []
        if self.created:
            parts.append(f"✓ {self.created} créée{'s' if self.created > 1 else ''}")
        if self.updated:
            parts.append(f"↺ {self.updated} mise{'s' if self.updated > 1 else ''} à jour")
        if not parts:
            parts.append("Aucune modification")
        if self.unmatched:
            parts.append(f"⚠ {len(self.unmatched)} non reliée{'s' if len(self.unmatched) > 1 else ''}")
        if self.errors:
            parts.append(f"✗ {len(self.errors)} erreur{'s' if len(self.errors) > 1 else ''}")
        return " · ".join(parts)


# ── Service principal ─────────────────────────────────────────────────────────

class WeakPointsSyncService:
    """
    Scanne le vault Obsidian pour les notes avec type: lacune,
    les lie aux cours Synapse, et les synchronise dans SQLite.
    """

    # ── Entry point ───────────────────────────────────────────────────────────

    def sync(self, courses: list | None = None) -> WeakPointSyncResult:
        """
        Scanne le vault et upsert les lacunes Obsidian dans SQLite.

        courses : liste des cours Synapse (data_store.cours).
                  Si None, chargé automatiquement depuis data_store.
        """
        from backend.state.store import data_store

        if courses is None:
            courses = data_store.cours

        vault_path_str = settings.obsidian_vault_path
        if not vault_path_str:
            logger.warning("WeakPointsSync: OBSIDIAN_VAULT_PATH non configuré")
            return WeakPointSyncResult(errors=["OBSIDIAN_VAULT_PATH non configuré"])

        vault = Path(vault_path_str)
        if not vault.exists():
            logger.error(f"WeakPointsSync: vault introuvable : {vault_path_str}")
            return WeakPointSyncResult(errors=[f"Vault introuvable : {vault_path_str}"])

        result = WeakPointSyncResult()

        # ── Index des cours ───────────────────────────────────────────────────
        by_item:  dict[str, object] = {}   # "235" → Cours
        by_title: dict[str, list[object]] = {}   # titre normalisé → cours candidats

        for c in courses:
            item = str(getattr(c, "display_item_number", "") or "").strip()
            if item:
                by_item[item] = c
                by_item[item.replace(",", ".")] = c
                by_item[item.replace(".", ",")] = c
            norm = _normalize(c.title or "")
            if norm:
                by_title.setdefault(norm, []).append(c)

        # ── Scan de tous les .md ──────────────────────────────────────────────
        md_files = list(vault.rglob("*.md"))
        logger.info(f"WeakPointsSync: {len(md_files)} fichiers .md à analyser")

        for md_path in md_files:
            # Ignorer les fichiers dans un dossier "Templates"
            if any("template" in part.lower() for part in md_path.parts):
                result.skipped += 1
                continue
            try:
                self._process_file(md_path, vault, by_item, by_title, result)
            except Exception as exc:
                logger.error(f"WeakPointsSync: erreur sur {md_path.name}: {exc}")
                result.errors.append(f"{md_path.name}: {exc}")

        logger.info(
            f"WeakPointsSync terminé: {result.created} créées, {result.updated} màj, "
            f"{result.skipped} ignorées, {len(result.unmatched)} non reliées, "
            f"{len(result.errors)} erreurs"
        )
        return result

    # ── Traitement d'un fichier ───────────────────────────────────────────────

    def _process_file(
        self,
        path: Path,
        vault: Path,
        by_item: dict,
        by_title: dict,
        result: WeakPointSyncResult,
    ) -> None:
        """Traite un seul fichier .md. Modifie `result` en place."""
        # Lecture
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            result.errors.append(f"{path.name}: lecture impossible ({exc})")
            return

        # Parsing frontmatter
        fm_raw, body = _split_frontmatter(text)
        if not fm_raw:
            result.skipped += 1
            return

        fm_pairs = _parse_fm_lines(fm_raw)
        fm = {k: v for k, v in fm_pairs}

        # Seulement type: lacune
        fm_type = str(fm.get("type", "")).strip().lower()
        if fm_type != "lacune":
            result.skipped += 1
            return

        # ── Extraction des champs ─────────────────────────────────────────────
        title = self._extract_title(fm, body, path)
        if not title:
            result.skipped += 1
            return

        college        = str(fm.get("college", "") or "").strip()
        gravite        = str(fm.get("gravite", "") or "").strip().lower()
        statut_raw     = str(fm.get("statut", "") or "active").strip().lower()
        source         = str(fm.get("source", "") or "obsidian").strip()
        date_creation  = str(fm.get("date_creation", "") or "").strip()
        synapse_id_fm  = str(fm.get("synapse_id", "") or "").strip()

        # Sévérité : préférer le champ 'severity' explicite, sinon convertir 'gravite'
        sev_raw = str(fm.get("severity", "") or "").strip()
        if sev_raw.isdigit():
            severity = max(1, min(5, int(sev_raw)))
        else:
            severity = GRAVITE_TO_SEVERITY.get(gravite, 2)

        status = _normalize_statut(statut_raw)

        # Liens [[...]]
        cours_lies = _extract_wiki_links(body)

        # ── ID stable ─────────────────────────────────────────────────────────
        if synapse_id_fm and synapse_id_fm not in ("null", "None", ""):
            synapse_id = synapse_id_fm
        else:
            h = hashlib.md5(str(path.absolute()).encode("utf-8")).hexdigest()[:12]
            synapse_id = f"obsidian_{h}"

        # ── URI Obsidian ──────────────────────────────────────────────────────
        obsidian_uri   = self._build_uri(path, vault)
        obsidian_path  = str(path.absolute()).replace("\\", "/")

        # ── Matching cours ────────────────────────────────────────────────────
        matched = self._match_course(cours_lies, college, by_item, by_title)
        course_id    = matched.id    if matched else ""
        course_title = matched.title if matched else ""
        item_number  = str(getattr(matched, "display_item_number", "") or "") if matched else ""

        if not matched:
            result.unmatched.append(f"{path.name} — {title}")

        # ── Résolu : date_resolution ──────────────────────────────────────────
        resolved_at = None
        if status == "résolue":
            resolved_at = str(fm.get("date_resolution", "") or "").strip() or None

        # ── Frontmatter brut (JSON) ───────────────────────────────────────────
        import json as _json
        raw_fm = _json.dumps(
            {k: (list(v) if isinstance(v, list) else str(v)) for k, v in fm.items()},
            ensure_ascii=False,
        )

        # ── Upsert SQLite ─────────────────────────────────────────────────────
        from backend.core.reviews import local_store as ls

        existing = ls.get_weak_point_by_synapse_id(synapse_id)
        is_update = existing is not None

        ls.upsert_weak_point_from_obsidian(
            synapse_id=synapse_id,
            course_id=course_id,
            course_title=course_title,
            item_number=item_number,
            detail=title,
            severity=severity,
            status=status,
            source=source,
            college=college,
            obsidian_path=obsidian_path,
            obsidian_uri=obsidian_uri,
            obsidian_title=title,
            raw_frontmatter=raw_fm,
            created_at=date_creation or None,
            resolved_at=resolved_at,
        )

        if is_update:
            result.updated += 1
        else:
            result.created += 1

        # ── Écriture synapse_id dans le frontmatter si absent ─────────────────
        if not synapse_id_fm or synapse_id_fm in ("null", "None", ""):
            try:
                self._write_fm_fields(path, {
                    "synapse_id":    synapse_id,
                    "obsidian_path": obsidian_path,
                })
                logger.debug(f"synapse_id écrit dans {path.name}")
            except Exception as exc:
                logger.warning(f"Impossible d'écrire synapse_id dans {path.name}: {exc}")
                result.errors.append(
                    f"{path.name}: écriture du lien Obsidian impossible ({exc})"
                )

    # ── Extraction du titre ───────────────────────────────────────────────────

    @staticmethod
    def _extract_title(fm: dict, body: str, path: Path) -> str:
        """
        Extrait le titre d'une lacune Obsidian.
        Ordre : frontmatter.title → H1 du body → nom du fichier.
        """
        title = str(fm.get("title", "") or "").strip()
        if title and "<%" not in title:
            return title
        m = _H1_RE.search(body)
        if m:
            h1 = m.group(1).strip()
            if "<%" not in h1:
                return h1
        stem = path.stem
        if "<%" in stem:
            return ""
        return stem

    # ── Matching cours ────────────────────────────────────────────────────────

    def _match_course(
        self,
        cours_lies: list[str],
        college: str,
        by_item: dict,
        by_title: dict,
    ):
        """
        Tente de lier la lacune à un cours Synapse.

        Ordre de priorité :
          1. Numéro d'item extrait des [[liens]] (strict)
          2. Titre normalisé des [[liens]] (strict)
          3. Aucun match → None
        """
        # Priorité 1 : item dans les liens [[235 - Péricardite]]
        for link in cours_lies:
            m = re.match(r'^(\d+(?:[.,]\d+)?)\s*[-–]', link)
            if m:
                item = m.group(1).strip().replace(",", ".")
                if item in by_item:
                    return by_item[item]

        # Priorité 2 : titre normalisé des liens
        for link in cours_lies:
            norm = _normalize(link)
            candidates = by_title.get(norm, [])
            if len(candidates) == 1:
                return candidates[0]

        return None

    # ── URI Obsidian ──────────────────────────────────────────────────────────

    @staticmethod
    def _build_uri(path: Path, vault: Path) -> str:
        """Construit l'URI obsidian://open?vault=...&file=... ou fallback chemin."""
        import urllib.parse
        vault_name = settings.obsidian_vault_name
        if not vault_name:
            return str(path.absolute()).replace("\\", "/")
        try:
            relative = path.relative_to(vault)
            encoded_file  = urllib.parse.quote(
                str(relative).replace("\\", "/"), safe=""
            )
            encoded_vault = urllib.parse.quote(vault_name, safe="")
            return f"obsidian://open?vault={encoded_vault}&file={encoded_file}"
        except Exception:
            return str(path.absolute()).replace("\\", "/")

    # ── Écriture frontmatter (réutilise la logique de sync.py) ───────────────

    @staticmethod
    def _write_fm_fields(path: Path, updates: dict) -> None:
        """
        Met à jour des champs spécifiques dans le frontmatter YAML.
        Ne touche pas au body ni aux autres champs.
        """
        from backend.core.obsidian.sync import vault_sync_service
        vault_sync_service._write_frontmatter_fields(path, updates)


# ── Helpers de module ─────────────────────────────────────────────────────────

def _normalize(text: str) -> str:
    """Normalise un titre pour comparaison : minuscules, sans accents, sans ponctuation."""
    text = text.lower().strip()
    text = unicodedata.normalize("NFD", text)
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    text = re.sub(r"[^\w\s\-]", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _normalize_statut(statut: str) -> str:
    """Convertit un statut Obsidian en statut Synapse valide."""
    return _STATUT_MAP.get(statut.lower().strip(), "active")


def _extract_wiki_links(body: str) -> list[str]:
    """Extrait les cibles [[lien]] ou [[lien|alias]] d'un corps Markdown."""
    return [m.group(1).strip() for m in _WIKI_LINK_RE.finditer(body)]


# ── Fonctions d'écriture statut/review → Obsidian ────────────────────────────

def write_obsidian_lacune_status(
    obsidian_path: str,
    status: str,
    resolved_at: Optional[str] = None,
) -> bool:
    """
    Écrit le nouveau statut dans le frontmatter YAML d'une lacune Obsidian.
    Ajoute `date_resolution` si `resolved_at` est fourni.

    Retourne True si succès, False sinon.
    """
    from backend.core.obsidian.sync import vault_sync_service

    path = Path(obsidian_path)
    if not path.exists():
        logger.warning(f"write_obsidian_lacune_status: fichier introuvable : {obsidian_path}")
        return False

    updates: dict[str, str] = {"statut": status}
    if resolved_at:
        updates["date_resolution"] = resolved_at

    try:
        vault_sync_service._write_frontmatter_fields(path, updates)
        logger.debug(f"Statut Obsidian mis à jour → {status} : {path.name}")
        return True
    except Exception as exc:
        logger.error(f"write_obsidian_lacune_status échoué pour {path.name}: {exc}")
        return False


def create_obsidian_lacune_note(
    title: str,
    college: str = "",
    severity: int = 2,
    course_title: str = "",
    item_number: str = "",
    synapse_id: str = "",
    source: str = "synapse",
    status: str = "active",
) -> tuple[bool, str, str]:
    """
    Crée une note lacune dans 08 - Lacunes/{sous-dossier}/{titre}.md.

    Utilise 90 - Templates/Template - Lacune.md si disponible.
    Retourne (ok, chemin_absolu_slash, uri_obsidian).
    """
    vault_path_str = settings.obsidian_vault_path
    if not vault_path_str:
        return False, "", ""

    vault = Path(vault_path_str)
    subfolder = _STATUS_TO_FOLDER.get(status, "Actives")
    target_dir = vault / "08 - Lacunes" / subfolder
    target_dir.mkdir(parents=True, exist_ok=True)

    safe_title = _WIN_FORBIDDEN_WP.sub("", title).strip() or "Lacune sans titre"
    safe_title = re.sub(r'[\s.]+$', '', safe_title)

    path = target_dir / f"{safe_title}.md"
    if path.exists():
        stem, i = safe_title, 2
        while path.exists():
            path = target_dir / f"{stem} ({i}).md"
            i += 1

    gravite   = _SEV_TO_GRAVITE.get(severity, "moyenne")
    today     = datetime.date.today().isoformat()
    obs_path  = str(path.absolute()).replace("\\", "/")
    cours_val = f"{item_number} - {course_title}" if item_number and course_title else course_title

    # ── Frontmatter (champs fixes) ─────────────────────────────────────────────
    fm_lines = [
        "---",
        "type: lacune",
        f"date_creation: {today}",
        f"college: {college}",
        f"gravite: {gravite}",
        f"statut: {status}",
        f"source: {source}",
        "prochaine_revision:",
        "tags:",
        "  - lacune",
        "  - edn",
        f"synapse_id: {synapse_id}",
        f'obsidian_path: "{obs_path}"',
    ]
    if cours_val:
        fm_lines.append(f'cours: "{cours_val}"')
    fm_lines.append("---")
    frontmatter = "\n".join(fm_lines) + "\n"

    # ── Body : depuis le template Obsidian si disponible ──────────────────────
    tpl_path = vault / "90 - Templates" / "Template - Lacune.md"
    if tpl_path.exists():
        try:
            tpl_text = tpl_path.read_text(encoding="utf-8")
            _, tpl_body = _split_frontmatter(tpl_text)
            # Remplacer le placeholder Templater par le titre réel
            body = tpl_body.replace("<% tp.file.title %>", title)
            # Supprimer toute syntaxe Templater résiduelle
            body = re.sub(r'<%[-_]?.*?[-_]?%>', '', body)
            body = body.strip()
        except Exception as exc:
            logger.warning(f"Lecture template lacune échouée, fallback : {exc}")
            body = _default_lacune_body(title)
    else:
        body = _default_lacune_body(title)

    content = frontmatter + "\n" + body + "\n"

    try:
        path.write_text(content, encoding="utf-8")
        logger.success(f"Note lacune créée : {path.name}")
    except OSError as exc:
        logger.error(f"create_obsidian_lacune_note: {exc}")
        return False, "", ""

    uri = WeakPointsSyncService._build_uri(path, vault)
    return True, obs_path, uri


def _default_lacune_body(title: str) -> str:
    """Corps de secours si le template Obsidian est absent."""
    return (
        f"# {title}\n\n"
        f"## 1. Mon erreur\n\n- \n\n---\n\n"
        f"## 2. Pourquoi je me suis trompé\n\n- \n\n---\n\n"
        f"## 3. Correction\n\n- \n\n---\n\n"
        f"## 4. Règle EDN à retenir\n\n> \n\n---\n\n"
        f"## 5. Cours liés\n\n- [[ ]]\n\n---\n\n"
        f"## 6. Concepts liés\n\n- [[ ]]\n"
    )


def move_obsidian_lacune_file(obsidian_path: str, new_status: str) -> str:
    """
    Déplace le fichier lacune dans le sous-dossier correspondant au nouveau statut.

    Retourne le nouveau chemin absolu (slash), ou l'original si déjà au bon endroit.
    """
    if not obsidian_path:
        return obsidian_path

    path = Path(obsidian_path.replace("/", "\\"))
    if not path.exists():
        logger.warning(f"move_obsidian_lacune_file: fichier introuvable : {obsidian_path}")
        return obsidian_path

    vault_path_str = settings.obsidian_vault_path
    if not vault_path_str:
        return obsidian_path

    vault    = Path(vault_path_str)
    subfolder = _STATUS_TO_FOLDER.get(new_status, "Actives")
    target_dir = vault / "08 - Lacunes" / subfolder
    target_dir.mkdir(parents=True, exist_ok=True)

    new_path = target_dir / path.name
    if new_path.resolve() == path.resolve():
        return obsidian_path  # déjà au bon endroit

    if new_path.exists():
        stem, suffix, i = path.stem, path.suffix, 2
        while new_path.exists():
            new_path = target_dir / f"{stem} ({i}){suffix}"
            i += 1

    try:
        import shutil as _shutil
        _shutil.move(str(path), str(new_path))
        logger.info(f"Lacune déplacée → {subfolder}/{new_path.name}")
        return str(new_path.absolute()).replace("\\", "/")
    except Exception as exc:
        logger.error(f"move_obsidian_lacune_file: {exc}")
        return obsidian_path


def write_obsidian_reviewed_at(obsidian_path: str, date_iso: str) -> bool:
    """
    Écrit `last_reviewed_at` dans le frontmatter YAML d'une lacune Obsidian.
    Retourne True si succès, False sinon.
    """
    from backend.core.obsidian.sync import vault_sync_service

    path = Path(obsidian_path)
    if not path.exists():
        logger.warning(f"write_obsidian_reviewed_at: fichier introuvable : {obsidian_path}")
        return False

    try:
        vault_sync_service._write_frontmatter_fields(path, {"last_reviewed_at": date_iso})
        logger.debug(f"last_reviewed_at mis à jour : {path.name} → {date_iso}")
        return True
    except Exception as exc:
        logger.error(f"write_obsidian_reviewed_at échoué pour {path.name}: {exc}")
        return False


def delete_obsidian_lacune_file(obsidian_path: str) -> bool:
    """
    Supprime physiquement le fichier .md d'une lacune Obsidian.
    Retourne True si supprimé, False si introuvable ou erreur.
    """
    path = Path(obsidian_path.replace("/", "\\"))
    if not path.exists():
        logger.warning(f"delete_obsidian_lacune_file: fichier introuvable : {obsidian_path}")
        return False
    try:
        path.unlink()
        logger.info(f"Lacune Obsidian supprimée : {path.name}")
        return True
    except Exception as exc:
        logger.error(f"delete_obsidian_lacune_file: impossible de supprimer {path.name}: {exc}")
        return False


# ── Singleton ─────────────────────────────────────────────────────────────────

weak_points_sync_service = WeakPointsSyncService()
