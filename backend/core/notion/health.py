"""
Notion Health Check
-------------------
Vérifie que le token Notion est valide et que la base de données Cours
contient bien les propriétés attendues par Synapse.

Usage:
    from backend.core.notion.health import notion_health
    result = await notion_health.check()
    # result = HealthResult(ok=True/False, checks=[...])
"""

from dataclasses import dataclass, field
from typing import List
from loguru import logger
from backend.config.settings import settings
from backend.core.notion.client import notion_client

# ── Propriétés obligatoires ──────────────────────────────────────────────────
REQUIRED_PROPERTIES: List[str] = [
    "Cours",                        # Titre principal
    "ITEM",                         # Numéro ITEM (Number)
    "Collège",                      # Multi-select
    "Semestre",                     # Select
    "URL PDF COLLEGE",              # URL PDF lié au collège
    "Rappel fait collège",          # Checkbox rappels faits
    "Date 1ère lecture collège",    # Date première lecture collège
    "Nombre lecture collège",       # Compteur lectures
    "Anki",                         # Checkbox Anki
]

# ── Propriétés optionnelles (avertissement si absentes) ────────────────────
OPTIONAL_PROPERTIES: List[str] = [
    "URL PDF",                      # PDF UE/Fac
    "Rappel fait",                  # Checkbox rappels UE
    "Date 1ère lecture",            # Date première lecture UE
    "Agrégation FICHE EDN",         # Lien fiche EDN
    "Fiche EDN",
    "ITEM lié",                     # Relation vers DB Items
    "UE",                           # Relation vers DB UE
    "Statut cours",                 # Status / Select statut
    "QCM fait",                     # Checkbox QCM
]


@dataclass
class HealthCheck:
    name: str
    ok: bool
    message: str
    optional: bool = False

    @property
    def icon(self) -> str:
        if self.ok:
            return "✅"
        return "⚠️" if self.optional else "❌"

    def __str__(self) -> str:
        return f"{self.icon} {self.name} — {self.message}"


@dataclass
class HealthResult:
    ok: bool = True
    checks: List[HealthCheck] = field(default_factory=list)
    db_name: str = ""
    error: str = ""

    def add(self, check: HealthCheck):
        self.checks.append(check)
        if not check.ok and not check.optional:
            self.ok = False

    @property
    def required_checks(self):
        return [c for c in self.checks if not c.optional]

    @property
    def optional_checks(self):
        return [c for c in self.checks if c.optional]


class NotionHealthService:
    """Service de diagnostic de la configuration Notion."""

    async def check(self) -> HealthResult:
        result = HealthResult()

        # ── 1. Token valide ? ────────────────────────────────────────────────
        token_ok = await self._check_token(result)
        if not token_ok:
            return result  # Inutile de continuer sans token

        # ── 2. Base de données accessible ? ─────────────────────────────────
        props = await self._check_database(result)
        if props is None:
            return result  # Inutile de continuer sans DB

        # ── 3. Propriétés obligatoires ───────────────────────────────────────
        self._check_properties(result, props, REQUIRED_PROPERTIES, optional=False)

        # ── 4. Propriétés optionnelles ───────────────────────────────────────
        self._check_properties(result, props, OPTIONAL_PROPERTIES, optional=True)

        return result

    # ── Méthodes internes ────────────────────────────────────────────────────

    async def _check_token(self, result: HealthResult) -> bool:
        """Vérifie que le token Notion répond correctement."""
        try:
            if not settings.notion.token:
                result.add(HealthCheck(
                    name="Token Notion",
                    ok=False,
                    message="NOTION_TOKEN absent ou vide dans l'environnement",
                ))
                return False

            # Appel léger : retrieve the bot user
            me = await notion_client.client.users.me()
            bot_name = me.get("bot", {}).get("owner", {}).get("user", {}).get("name", "Bot")
            result.add(HealthCheck(
                name="Token Notion",
                ok=True,
                message=f"Authentifié en tant que « {bot_name} »",
            ))
            return True
        except Exception as e:
            result.add(HealthCheck(
                name="Token Notion",
                ok=False,
                message=f"Erreur d'authentification : {e}",
            ))
            return False

    async def _check_database(self, result: HealthResult) -> dict | None:
        """Vérifie l'accès à la base de données Cours et retourne ses propriétés."""
        db_id = settings.notion.cours_db_id
        if not db_id:
            result.add(HealthCheck(
                name="Base de données Cours",
                ok=False,
                message="DATABASE_COURS_ID absent dans l'environnement",
            ))
            return None

        try:
            db = await notion_client.client.databases.retrieve(database_id=db_id)
            name = db.get("title", [{}])[0].get("plain_text", db_id)
            result.db_name = name
            result.add(HealthCheck(
                name="Base de données Cours",
                ok=True,
                message=f"Accessible : « {name} » ({db_id[:8]}…)",
            ))
            return db.get("properties", {})
        except Exception as e:
            result.add(HealthCheck(
                name="Base de données Cours",
                ok=False,
                message=f"Impossible d'accéder à la DB ({db_id[:8]}…) : {e}",
            ))
            return None

    def _check_properties(
        self,
        result: HealthResult,
        db_props: dict,
        prop_names: List[str],
        optional: bool,
    ):
        """Vérifie la présence de chaque propriété dans la DB."""
        for name in prop_names:
            found = name in db_props
            prop_type = db_props[name].get("type", "?") if found else "—"
            result.add(HealthCheck(
                name=f"Propriété « {name} »",
                ok=found,
                message=f"type={prop_type}" if found else "Colonne introuvable dans la DB",
                optional=optional,
            ))


# ── Singleton ────────────────────────────────────────────────────────────────
notion_health = NotionHealthService()
