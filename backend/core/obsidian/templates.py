"""
Génère le contenu Markdown d'une note de cours Obsidian.

Priorité :
  1. Lire 90 - Template/Template - Cours.md depuis le vault.
     - Frontmatter du template → fusionné avec les données Synapse.
     - Body du template        → tags Templater remplacés/nettoyés.
  2. Sinon : frontmatter Synapse + body de secours intégré.
"""
from __future__ import annotations

import datetime
import re
from pathlib import Path
from typing import Optional

from loguru import logger

# Regex Templater : <% ... %>  (capture aussi <%* ... %>)
_TEMPLATER_TAG = re.compile(r"<%[*+-]?\s*[\s\S]*?\s*[+-]?%>", re.DOTALL)

# ── Template de secours ───────────────────────────────────────────────────────

_FALLBACK_BODY = """\
## 1. Idée centrale

> En une phrase : ce cours sert à reconnaître / comprendre / traiter quoi ?

## 2. À savoir absolument

-
-
-

## 3. Diagnostic

### Clinique

-

### Signes de gravité

-

### Terrain à risque

-

## 4. Examens complémentaires

-

## 5. Traitement / conduite à tenir

-

## 6. Pièges EDN

- ⚠️
- ⚠️
- ⚠️

## 7. Liens vers concepts

- [[ ]]
- [[ ]]
- [[ ]]

## 8. Lacunes liées

- [[ ]]

## 9. Questions à revoir

- [ ]
- [ ]

## 10. Résumé ultra-court

- ⭐
"""

# ── Données Synapse pour un cours ─────────────────────────────────────────────

def _synapse_values(course) -> dict:
    """Retourne les valeurs Synapse connues pour le frontmatter."""
    return {
        "type":           "cours",
        "synapse_id":     course.id,
        "notion_id":      course.id,
        "item":           getattr(course, "display_item_number", "") or "",
        "college":        (course.college[0] if course.college else "") or "",
        "title":          course.title or "",
        "statut":         getattr(course, "course_status", "À lire") or "À lire",
        "pdf":            getattr(course, "url_pdf", "") or getattr(course, "url_pdf_ue", "") or "",
        "date_creation":  datetime.date.today().isoformat(),
    }

# ── Parsing du frontmatter YAML (simple, sans dépendance PyYAML) ──────────────

def _split_frontmatter(text: str):
    """
    Sépare (frontmatter_raw, body) depuis un fichier Markdown.
    frontmatter_raw : contenu entre les deux --- (sans les ---)
    body            : tout ce qui suit le second ---
    Retourne ("", text) si pas de frontmatter.
    """
    if not text.startswith("---"):
        return "", text
    end = text.find("\n---", 3)
    if end == -1:
        return "", text
    fm_raw = text[4:end]          # entre premier --- et second ---
    body = text[end + 4:].lstrip("\n")
    return fm_raw, body


def _parse_fm_lines(fm_raw: str) -> list[tuple[str, str | list]]:
    """
    Parse le frontmatter ligne par ligne.
    Retourne une liste ordonnée de (clé, valeur) où valeur est str ou list[str].
    Les tags Templater sont nettoyés des valeurs.
    """
    result: list[tuple[str, str | list]] = []
    current_key: str | None = None
    current_list: list[str] | None = None

    for line in fm_raw.splitlines():
        # Ligne vide → ignore
        if not line.strip():
            continue

        # Élément de liste indentée (  - item)
        if line.startswith("  ") or line.startswith("\t"):
            stripped = line.strip()
            if stripped.startswith("- ") and current_key is not None:
                item = stripped[2:].strip()
                item = _TEMPLATER_TAG.sub("", item).strip()
                if current_list is None:
                    # Convertir la clé précédente en liste
                    current_list = []
                    # Remplacer la dernière entrée
                    if result and result[-1][0] == current_key:
                        result[-1] = (current_key, current_list)
                    else:
                        result.append((current_key, current_list))
                if item:
                    current_list.append(item)
            continue

        # Réinitialiser la liste en cours
        current_list = None

        # Ligne clé: valeur
        if ":" in line:
            key, _, val = line.partition(":")
            key = key.strip()
            val = _TEMPLATER_TAG.sub("", val).strip().strip('"').strip("'")
            current_key = key
            result.append((key, val))

    return result


def _rebuild_fm(fields: list[tuple[str, str | list]], overrides: dict) -> str:
    """
    Reconstruit le bloc frontmatter YAML en appliquant les overrides Synapse.
    Préserve l'ordre des champs du template.
    """
    lines = ["---"]
    seen_keys: set[str] = set()

    for key, val in fields:
        seen_keys.add(key)
        actual = overrides.get(key, val)  # Synapse override si dispo

        if isinstance(actual, list):
            lines.append(f"{key}:")
            for item in actual:
                lines.append(f"  - {item}")
        else:
            # Ajouter quotes seulement si la valeur contient des caractères spéciaux
            safe = str(actual).strip()
            if safe and any(c in safe for c in ':#{}[]|>&*!,?'):
                lines.append(f'{key}: "{safe}"')
            else:
                lines.append(f"{key}: {safe}" if safe else f"{key}:")

    # Champs Synapse absents du template → ajoutés à la fin
    for key, val in overrides.items():
        if key not in seen_keys:
            if isinstance(val, list):
                lines.append(f"{key}:")
                for item in val:
                    lines.append(f"  - {item}")
            else:
                safe = str(val).strip()
                lines.append(f'{key}: "{safe}"' if safe else f"{key}:")

    # Tags par défaut si absents
    if "tags" not in seen_keys and "tags" not in overrides:
        lines.extend(["tags:", "  - cours", "  - edn"])

    lines.append("---")
    return "\n".join(lines) + "\n"


# ── Remplacement des tags Templater dans le body ──────────────────────────────

def _apply_templater(text: str, heading: str) -> str:
    """
    Remplace les tags Templater dans le body :
      <% tp.file.title %>  →  heading
      autres tags          →  supprimés
    """
    def _replace(m: re.Match) -> str:
        return heading if "tp.file.title" in m.group(0) else ""

    return _TEMPLATER_TAG.sub(_replace, text)


# ── API publique ──────────────────────────────────────────────────────────────

def build_template(course, vault_path: str = "") -> str:
    """
    Retourne le contenu complet (frontmatter + body) de la note de cours.

    Avec vault_path :
      - Frontmatter = champs du template disque fusionnés avec données Synapse.
      - Body        = body du template disque, tags Templater nettoyés.

    Sans vault_path (ou template introuvable) :
      - Frontmatter = champs Synapse hardcodés.
      - Body        = template de secours intégré.
    """
    item = getattr(course, "display_item_number", "") or ""
    title = course.title or ""
    heading = f"{item} - {title}" if item else title

    overrides = _synapse_values(course)

    if vault_path:
        template_file = Path(vault_path) / "90 - Template" / "Template - Cours.md"
        if template_file.exists():
            try:
                raw = template_file.read_text(encoding="utf-8")
                fm_raw, body = _split_frontmatter(raw)
                fields = _parse_fm_lines(fm_raw)
                frontmatter = _rebuild_fm(fields, overrides)
                body = _apply_templater(body, heading)
                logger.info(
                    f"Template disque utilisé : {template_file} "
                    f"({len(fields)} champs, body {len(body)} chars)"
                )
                return frontmatter + "\n" + body
            except OSError as exc:
                logger.warning(f"Lecture template disque échouée ({exc}), fallback intégré")
        else:
            logger.warning(f"Template introuvable : {template_file} — fallback intégré")
    else:
        logger.warning("vault_path vide — fallback intégré")

    # ── Fallback ──────────────────────────────────────────────────────────────
    fm_fields = [
        ("type",          "cours"),
        ("synapse_id",    overrides["synapse_id"]),
        ("notion_id",     overrides["notion_id"]),
        ("item",          overrides["item"]),
        ("college",       overrides["college"]),
        ("title",         overrides["title"]),
        ("statut",        overrides["statut"]),
        ("pdf",           overrides["pdf"]),
        ("date_creation", overrides["date_creation"]),
        ("tags",          ["cours", "edn"]),
    ]
    frontmatter = _rebuild_fm(fm_fields, {})
    body = f"# {heading}\n\n{_FALLBACK_BODY}"
    return frontmatter + "\n" + body
