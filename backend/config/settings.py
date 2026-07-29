import zoneinfo

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# ── Fuseau horaire applicatif ──────────────────────────────────────────────────
APP_TIMEZONE = zoneinfo.ZoneInfo("Indian/Reunion")

# ── Noms des propriétés Notion ─────────────────────────────────────────────────
# Source de vérité unique — extraits des screenshots de la DB Notion.
# NE JAMAIS écrire un nom de propriété Notion en dur ailleurs dans le code.
class NotionProps:
    # ── Identifiants / navigation ──────────────────────────────────────────
    COURS_TITLE            = "Cours"
    ITEM                   = "ITEM"
    ITEM_LIE               = "ITEM lié"
    COLLEGE                = "Collège"
    SEMESTRE               = "Semestre"
    UE                     = "UE"
    STATUT_COURS           = "Statut cours"
    FICHE_EDN              = "Fiche EDN"            # Rollup dans la DB cours
    FICHE_EDN_ALT          = "Agrégation FICHE EDN" # Nom alternatif (ancienne DB)

    # ── Collège ────────────────────────────────────────────────────────────
    URL_PDF_COLLEGE        = "URL PDF COLLEGE"
    RAPPEL_COLLEGE         = "Rappel fait collège"
    DATE_LECTURE_COLLEGE   = "Date 1ère lecture collège"
    LECTURE_J3_COLLEGE     = "Lecture J3 collège"
    LECTURE_J7_COLLEGE     = "Lecture J7 collège"
    LECTURE_J14_COLLEGE    = "Lecture J14 collège"
    LECTURE_J30_COLLEGE    = "Lecture J30 collège"
    NB_LECTURES_COLLEGE    = "Nombre lecture college"   # ← sans accent (confirmé Notion)
    ANKI_COLLEGE           = "Anki collège"
    RESUME_COLLEGE         = "Résumé collège"
    QCM_COLLEGE            = "QCM collège"
    CHATGPT_COLLEGE        = "Chatgpt collège"

    # ── UE / Semestre ──────────────────────────────────────────────────────
    URL_PDF_UE             = "URL PDF"
    RAPPEL_UE              = "Rappel fait"
    DATE_LECTURE_UE        = "Date 1ère lecture"
    LECTURE_J3_UE          = "Lecture J3"
    LECTURE_J7_UE          = "Lecture J7"
    LECTURE_J14_UE         = "Lecture J14"
    LECTURE_J30_UE         = "Lecture J30"
    NB_LECTURES_UE         = "Nombre lecture"           # ← propriété UE
    ANKI_UE                = "Anki"
    RESUME_UE              = "Résumé"
    QCM_FAIT               = "QCM fait"                 # ancienne propriété (legacy)
    CHATGPT_UE             = "Chatgpt"

    # ── Obsidian ───────────────────────────────────────────────────────────
    OBSIDIAN               = "Obsidian"

    # ── Daily Follow-Up ────────────────────────────────────────────────────
    DAILY_NAME             = "Name"
    DAILY_DATE             = "Date"
    DAILY_STATUS           = "Status"


NOTION_PROPS = NotionProps()


class NotionSettings(BaseSettings):
    token: str = Field(..., alias='NOTION_TOKEN')
    cours_db_id: str = Field(..., alias='DATABASE_COURS_ID')
    item_db_id: str = Field(default="1c9b9fc3-1e69-81dd-a626-e622d9ac878c", alias='DATABASE_ITEM_ID')
    daily_db_id: str = Field(default="1c9b9fc31e69816fb29fdc0006d36308", alias='DATABASE_DAILY_ID')
    ue_db_id: str = Field(default="", alias='DATABASE_UE_ID')

    model_config = SettingsConfigDict(env_file='.env', env_file_encoding='utf-8', extra='ignore')

class Settings(BaseSettings):
    notion: NotionSettings = Field(default_factory=NotionSettings)
    log_level: str = "INFO"
    medicine_dir: str = Field("", alias='MEDICINE_DIR')
    fac_dir: str = Field("", alias='FAC_DIR')
    obsidian_vault_path: str = Field("", alias='OBSIDIAN_VAULT_PATH')
    obsidian_vault_name: str = Field("", alias='OBSIDIAN_VAULT_NAME')
    # IDs Google Calendar supplémentaires, séparés par des virgules
    google_calendar_ids: str = Field("", alias='GOOGLE_CALENDAR_IDS')
    lisa_cookie: str = Field("", alias='LISA_COOKIE')
    lisa_username: str = Field("", alias='LISA_USERNAME')
    lisa_password: str = Field("", alias='LISA_PASSWORD')
    anythingllm_url: str = Field("http://localhost:3001", alias='ANYTHINGLLM_URL')
    anythingllm_api_key: str = Field("", alias='ANYTHINGLLM_API_KEY')
    gemini_api_key: str = Field("", alias='GEMINI_API_KEY')
    gemini_lite_model: str = Field("gemini-3.1-flash-lite", alias='GEMINI_LITE_MODEL')
    gemini_flash_model: str = Field("gemini-3-flash-preview", alias='GEMINI_FLASH_MODEL')
    gemini_timeout_seconds: float = Field(60.0, alias='GEMINI_TIMEOUT_SECONDS')

    model_config = SettingsConfigDict(env_file='.env', extra='ignore')

    def get_calendar_ids(self) -> list[str]:
        """Retourne la liste des calendar IDs configurés (sans duplicates ni vides)."""
        raw = self.google_calendar_ids or ""
        seen, result = set(), []
        for cid in raw.split(","):
            cid = cid.strip()
            if cid and cid not in seen:
                seen.add(cid)
                result.append(cid)
        return result

settings = Settings()
