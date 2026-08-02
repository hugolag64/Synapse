"""
ObsidianService — relie chaque cours Synapse/Notion à une note Obsidian.

Conventions :
  - Les notes de cours sont créées dans :
      {vault}/01 - Collèges/{college}/Cours/{item} - {title}.md
  - Une note existante n'est jamais écrasée.
  - La propriété Notion "Obsidian" est remplie avec l'URI obsidian://
    (ou le chemin local si le nom du vault n'est pas configuré).
"""
from __future__ import annotations

import re
import urllib.parse
import webbrowser
from pathlib import Path
from typing import Optional, Tuple

from loguru import logger

from backend.config.settings import settings, NOTION_PROPS as P
from backend.core.obsidian.models import ObsidianNote
from backend.core.obsidian.templates import build_template

# Caractères interdits dans les noms de fichiers Windows
_WIN_FORBIDDEN = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_TRAILING_DOTS_SPACES = re.compile(r'[\s.]+$')

# ── Mapping Notion → dossier Obsidian ────────────────────────────────────────
# Clé   = nom EXACT du multi_select "Collège" dans Notion (avec emoji).
# Valeur = nom EXACT du dossier sur disque dans 01 - Cours EDN/.
# Source de vérité : noms Notion récupérés via API, dossiers vérifiés sur disque.
COLLEGE_MAPPING: dict[str, str] = {
    # ── Noms Notion → dossier Obsidian ────────────────────────────────────
    "Cardiovasculaire ❤️":                                      "Cardiovasculaire ❤️",
    "Dermatologie 🧴":                                          "Dermatologie 🩹",
    "Endocrinologie - Diabétologie - Maladies métaboliques 🫘": "Endocrinologie - Nutrition 🧬",
    "Hématologie 🩸":                                           "Hématologie 🩸",
    "Hépato-Gastro-entérologie 🧻":                            "Hépato-Gastro-Entérologie 🟤",
    "Infectiologie 🦠":                                         "Infectiologie 🦠",
    "Neurologie 🧠":                                            "Neurologie 🧠",
    "Nutrition 🍔":                                             "Endocrinologie - Nutrition 🧬",
    "Néphrologie 🧑‍🔬":                                      "Néphrologie 🫘",
    "Pneumologie 🫁":                                           "Pneumologie 🫁",
    "Psychiatrie 🧩":                                           "Psychiatrie - Addictologie 🧩",
    "Gynécologie-Obstétrique 👶":                               "Gynécologie - Obstétrique 🤰",
    "Pédiatrie 🚼":                                             "Pédiatrie 👶",
    "Génétique 🧬":                                             "Génétique 🧫",
    "Ophtalmologie 👁️":                                       "Ophtalmologie 👁️",
    "ORL 👂":                                                   "ORL 👂",
    "Médecine physique et réadaptation 🦿":                    "MPR 💪",
    "Médecine générale 🩺":                                    "Médecine Générale 🏥",
    "Gériatrie 👴":                                             "Gériatrie 🧓",
    "Urologie 🚻":                                              "Urologie 💧",
    "Douleur - Soins palliatifs 🕊️":                          "Douleur - Soins Palliatifs 🕊️",
    "Immunologie 💉":                                           "Immunologie - Allergologie 🛡️",
    "Oncologie 🧬":                                             "Cancérologie 🎗️",
    "Anesthésie-Réanimation 💉":                                "Urgences - Réanimation 🚨",
    "Médecine Intensive - Réanimation 🚨":                     "MIR - Urgences 🚨",
    "Orthopédie - Traumatologie 🦴":                           "Orthopédie - Traumatologie 🦴",
    "Chirurgie maxillo-faciale 🦷":                            "Chirurgie Maxillo-Faciale 🦷",
    "Chirurgie digestive 🧵":                                  "Hépato-Gastro-Entérologie 🟤",
    "Rhumatologie 🤲":                                          "Rhumatologie 🤝",
    "Médecine Interne 🏥":                                      "Médecine Interne 🔍",
    "Médecine légale - Santé publique ⚖️":                     "Médecine Légale - Médecine du Travail ⚖️",
    "Thérapeutique 💊":                                         "Thérapeutique 💊",
}



def _resolve_college(notion_name: str) -> str:
    """
    Retourne le nom du dossier Obsidian correspondant au collège Notion.

    Ordre de recherche :
      1. Clé exacte dans COLLEGE_MAPPING (nom Notion avec emoji, ex: "Neurologie 🧠")
      2. Fallback : nom Notion tel quel (crée un dossier ad-hoc si absent du mapping)
    """
    if notion_name in COLLEGE_MAPPING:
        return COLLEGE_MAPPING[notion_name]

    return notion_name


class ObsidianService:

    # ── Utilitaires ───────────────────────────────────────────────────────────

    def sanitize_filename(self, text: str) -> str:
        """Supprime les caractères interdits Windows et nettoie les bords."""
        clean = _WIN_FORBIDDEN.sub("", text)
        clean = _TRAILING_DOTS_SPACES.sub("", clean)
        return clean.strip() or "Sans titre"

    def _vault_path(self) -> Optional[Path]:
        raw = settings.obsidian_vault_path
        if not raw:
            return None
        p = Path(raw)
        return p if p.exists() else p  # on retourne même si absent (création possible)

    # ── Chemin de la note ─────────────────────────────────────────────────────

    def get_course_note_path(self, course) -> Optional[Path]:
        """Retourne le Path absolu attendu pour la note, ou None si config manquante."""
        vault = self._vault_path()
        if vault is None:
            return None

        college_notion = (course.college[0] if course.college else "") or ""
        if not college_notion:
            return None

        # Applique le mapping Notion → dossier Obsidian
        college = _resolve_college(college_notion)

        item = getattr(course, "display_item_number", "") or ""
        title = self.sanitize_filename(course.title or "Sans titre")

        filename = f"{item} - {title}.md" if item else f"{title}.md"
        return vault / "01 - Cours EDN" / college / "Cours" / filename

    def note_exists(self, course) -> bool:
        """
        Vrai si une note Obsidian est liée à ce cours.

        Ordre de vérification :
          1. Propriété Notion "Obsidian" remplie (source de vérité persistante)
          2. Chemin canonique sur disque (note créée via Synapse, nom exact)
          3. Glob fallback {item} - *.md (note créée manuellement, nom légèrement différent)
        """
        # 1. Propriété Notion déjà remplie → note confirmée sans toucher le disque
        return self.find_course_note(course) is not None

    def _find_note_in_vault(self, course) -> Optional[Path]:
        """Cherche la note canonique, y compris dans un autre collège Obsidian."""
        vault = self._vault_path()
        if vault is None:
            return None
        root = vault / "01 - Cours EDN"
        if not root.exists():
            return None

        item = str(getattr(course, "display_item_number", "") or "").strip()
        title = self.sanitize_filename(course.title or "")
        candidates: list[Path] = []
        if item:
            candidates.extend(root.glob(f"*/Cours/{item} - *.md"))
        if title:
            candidates.extend(root.glob(f"*/Cours/{title}*.md"))

        seen: set[Path] = set()
        valid: list[Path] = []
        for candidate in candidates:
            if candidate in seen:
                continue
            seen.add(candidate)
            frontmatter = self.read_frontmatter(candidate)
            fm_item = str(frontmatter.get("item", "") or "").strip()
            if item and fm_item and fm_item != item:
                continue
            valid.append(candidate)

        # Un item canonique ne doit pas être attribué arbitrairement si
        # plusieurs notes concurrentes portent le même numéro.
        return valid[0] if len(valid) == 1 else None

    def find_course_note(self, course) -> Optional[Path]:
        """
        Retourne le Path réel de la note sur disque (canonical ou glob fallback).
        Retourne None si aucun fichier trouvé.
        """
        path = self.get_course_note_path(course)
        if path is None:
            return None
        if path.exists():
            return path
        item = getattr(course, "display_item_number", "") or ""
        if item and path.parent.exists():
            matches = list(path.parent.glob(f"{item} - *.md"))
            if matches:
                return matches[0]
        # Fallback titre seul (vault sans numéros d'item)
        title = self.sanitize_filename(course.title or "")
        if title and path.parent.exists():
            matches = list(path.parent.glob(f"{title}*.md"))
            if matches:
                return matches[0]
        return self._find_note_in_vault(course)

    def get_note_info(self, course) -> Optional[ObsidianNote]:
        """Retourne un ObsidianNote décrivant l'état de la note."""
        canonical_path = self.get_course_note_path(course)
        if canonical_path is None:
            return None
        path = self.find_course_note(course)
        return ObsidianNote(
            course_id=course.id,
            college=(course.college[0] if course.college else ""),
            item_number=getattr(course, "display_item_number", "") or "",
            title=course.title or "",
            path=path or canonical_path,
            exists=path is not None,
        )

    # ── URI Obsidian ──────────────────────────────────────────────────────────

    def build_obsidian_uri(self, path: Path) -> str:
        """Construit l'URI obsidian://open?vault=...&file=... pour un chemin absolu."""
        vault = self._vault_path()
        vault_name = settings.obsidian_vault_name

        try:
            relative = path.relative_to(vault)
            encoded_file = urllib.parse.quote(str(relative).replace("\\", "/"), safe="")
        except ValueError:
            # Si path n'est pas sous vault (ne devrait pas arriver)
            encoded_file = urllib.parse.quote(str(path).replace("\\", "/"), safe="")

        encoded_vault = urllib.parse.quote(vault_name, safe="")
        return f"obsidian://open?vault={encoded_vault}&file={encoded_file}"

    # ── Frontmatter ───────────────────────────────────────────────────────────

    def read_frontmatter(self, path: Path) -> dict:
        """
        Parse le frontmatter YAML d'une note Obsidian.
        Retourne un dict vide si le fichier n'a pas de frontmatter ou est illisible.
        """
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            return {}

        if not text.startswith("---"):
            return {}

        end = text.find("\n---", 3)
        if end == -1:
            return {}

        yaml_block = text[3:end].strip()
        result: dict = {}
        for line in yaml_block.splitlines():
            if ":" in line:
                key, _, value = line.partition(":")
                result[key.strip()] = value.strip().strip('"')
        return result

    # ── Création de note ──────────────────────────────────────────────────────

    async def create_course_note(self, course) -> Tuple[bool, Optional[str]]:
        """
        Crée la note Obsidian pour un cours.

        Retourne (True, chemin) si succès (même si la note existait déjà).
        Retourne (False, message_erreur) en cas de problème.
        Ne jamais écraser une note existante.
        """
        path = self.get_course_note_path(course)
        if path is None:
            return False, "OBSIDIAN_VAULT_PATH non configuré ou collège absent"

        if path.exists():
            logger.info(f"Note déjà existante, pas d'écrasement : {path}")
            return True, str(path)

        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            content = build_template(course, vault_path=settings.obsidian_vault_path)
            path.write_text(content, encoding="utf-8")
            logger.success(f"Note Obsidian créée : {path}")
        except OSError as exc:
            logger.error(f"Impossible de créer la note {path}: {exc}")
            return False, str(exc)

        # Synchronisation Notion (non bloquante sur erreur)
        try:
            await self.sync_obsidian_property_to_notion(course, path)
        except Exception as exc:
            logger.warning(f"sync_obsidian_property_to_notion échoué (non bloquant): {exc}")

        return True, str(path)

    # ── Ouverture de note ─────────────────────────────────────────────────────

    def open_course_note(self, course) -> bool:
        """
        Ouvre la note dans Obsidian.

        Ordre de priorité :
          1. URI obsidian:// stockée dans course.obsidian_uri (source de vérité)
          2. Fichier trouvé sur disque via find_course_note → URI construite à la volée
          3. Fallback os.startfile si vault_name absent
        """
        # 1. URI déjà connue → ouvrir directement sans toucher le disque
        uri = getattr(course, "obsidian_uri", None)
        if uri:
            try:
                webbrowser.open(uri)
                logger.info(f"Ouverture Obsidian URI (stockée) : {uri}")
                return True
            except Exception as exc:
                logger.warning(f"webbrowser.open({uri}) échoué : {exc}")

        # 2. Chercher le fichier sur disque
        path = self.find_course_note(course)
        if not path:
            return False

        vault_name = settings.obsidian_vault_name
        if vault_name:
            uri = self.build_obsidian_uri(path)
            try:
                webbrowser.open(uri)
                logger.info(f"Ouverture Obsidian URI (disque) : {uri}")
                return True
            except Exception as exc:
                logger.warning(f"webbrowser.open({uri}) échoué : {exc}")

        # 3. Fallback : ouvrir le fichier avec l'app par défaut
        try:
            import os
            os.startfile(str(path))
        except Exception as exc:
            logger.error(f"Impossible d'ouvrir {path}: {exc}")
            return False

        return True

    # ── Liste des notes disponibles pour liaison manuelle ─────────────────────

    def list_available_notes(self, course) -> list[Path]:
        """
        Retourne les fichiers .md disponibles dans le dossier Cours du collège,
        pour permettre à l'utilisateur de lier manuellement une note existante.
        """
        vault = self._vault_path()
        if vault is None:
            return []

        college_notion = (course.college[0] if course.college else "") or ""
        if not college_notion:
            return []

        college = _resolve_college(college_notion)
        cours_dir = vault / "01 - Cours EDN" / college / "Cours"
        if not cours_dir.exists():
            return []

        return sorted(cours_dir.glob("*.md"), key=lambda p: p.stem.lower())

    # ── Synchronisation Notion ────────────────────────────────────────────────

    async def sync_obsidian_property_to_notion(self, course, path: Path) -> bool:
        """
        Met à jour la propriété Notion "Obsidian" avec l'URI obsidian://
        (ou le chemin local si vault_name absent).
        """
        from backend.core.notion.service import notion_service
        from backend.core.notion.payloads import rich_text

        vault_name = settings.obsidian_vault_name
        value = self.build_obsidian_uri(path) if vault_name else str(path)

        try:
            ok = await notion_service.update_course(course.id, {P.OBSIDIAN: rich_text(value)})
            if ok:
                logger.success(f"Notion[Obsidian] mis à jour pour {course.id} → {value}")
            return ok
        except Exception as exc:
            logger.error(f"sync_obsidian_property_to_notion échoué : {exc}")
            return False

    def append_mnemonic_or_image(
        self,
        course,
        text_content: str | None = None,
        image_bytes: bytes | None = None,
        image_filename: str | None = None,
        target_section: str = "mnemo",
    ) -> bool:
        """
        Insère un moyen mnémotechnique, un piège ou une image directement dans la note Obsidian du cours.
        Sauvegarde les images dans {vault}/99 - Pièces jointes/ et insère le lien Markdown.
        """
        import datetime
        path = self.get_course_note_path(course)
        if path is None or not path.exists():
            obs = self.get_or_create_course_note(course)
            if obs and obs.local_path:
                path = obs.local_path
            else:
                logger.warning(f"Note Obsidian non trouvée pour le cours {course.id}")
                return False

        vault = self._vault_path()
        image_markdown = ""
        if image_bytes and vault:
            attachments_dir = vault / "99 - Pièces jointes"
            attachments_dir.mkdir(parents=True, exist_ok=True)
            filename = image_filename or f"synapse_{int(datetime.datetime.now().timestamp())}.png"
            img_path = attachments_dir / filename
            img_path.write_bytes(image_bytes)
            image_markdown = f"\n![[{filename}]]"

        lines = path.read_text(encoding="utf-8").splitlines()
        header_target = "## 6. Pièges EDN" if target_section == "piege" else "## 2. À savoir absolument"

        header_idx = -1
        for idx, line in enumerate(lines):
            if line.strip().startswith(header_target) or (target_section == "mnemo" and "mnémo" in line.lower()):
                header_idx = idx
                break

        bullet = ""
        if text_content:
            prefix = "⚠️ " if target_section == "piege" else "💡 "
            bullet = f"- {prefix}{text_content.strip()}"

        insertion = f"{bullet}{image_markdown}".strip()
        if not insertion:
            return True

        if header_idx != -1:
            lines.insert(header_idx + 1, insertion)
        else:
            lines.append(f"\n{header_target}\n\n{insertion}")

        path.write_text("\n".join(lines), encoding="utf-8")
        logger.success(f"Obsidian note {path.name} mise à jour avec l'élément : {insertion[:40]}")
        return True


obsidian_service = ObsidianService()
