from pydantic import BaseModel, Field, field_validator, model_validator
from typing import List, Optional, Any
from datetime import date, datetime
from backend.config.settings import NOTION_PROPS as P

class NotionProperty(BaseModel):
    """Helper methods to extract data from raw Notion properties."""
    
    @staticmethod
    def extract_title(prop: dict) -> str:
        """Extract text from a Title property."""
        if not prop or "title" not in prop or not prop["title"]:
            return "Untitled"
        return "".join([t["plain_text"] for t in prop["title"]])

    @staticmethod
    def extract_rich_text(prop: dict) -> str:
        """Extract text from a Rich Text property."""
        if not prop or "rich_text" not in prop or not prop["rich_text"]:
            return ""
        return "".join([t["plain_text"] for t in prop["rich_text"]])

    @staticmethod
    def extract_select(prop: dict) -> Optional[str]:
        """Extract value from a Select property."""
        if not prop or "select" not in prop or not prop["select"]:
            return None
        return prop["select"]["name"]

    @staticmethod
    def extract_multi_select(prop: dict) -> List[str]:
        """Extract values from a Multi-Select property."""
        if not prop or "multi_select" not in prop or not prop["multi_select"]:
            return []
        return [item["name"] for item in prop["multi_select"]]

    @staticmethod
    def extract_relation(prop: dict) -> List[str]:
        """Extract IDs from a Relation property."""
        if not prop or "relation" not in prop:
            return []
        return [rel["id"] for rel in prop["relation"]]

    @staticmethod
    def extract_number(prop: dict) -> Optional[float]:
        """Extract value from a Number property."""
        if not prop or "number" not in prop:
            return None
        return prop["number"]

    @staticmethod
    def extract_checkbox(prop: dict) -> bool:
        """Extract value from a Checkbox property."""
        if not prop or "checkbox" not in prop:
            return False
        return prop["checkbox"]

    @staticmethod
    def extract_date(prop: dict) -> Optional[date]:
        """Extract start date from a Date property."""
        if not prop or "date" not in prop or not prop["date"]:
            return None
        return datetime.fromisoformat(prop["date"]["start"]).date()
    
    @staticmethod
    def extract_url(prop: dict) -> Optional[str]:
        """Extract value from a URL property."""
        if not prop or "url" not in prop:
            return None
        return prop["url"]

    @staticmethod
    def extract_rollup_number(prop: dict) -> Optional[float]:
        """Extract number value from a Rollup property."""
        if not prop or "rollup" not in prop:
            return None
        
        rollup = prop["rollup"]
        # Notion rollup can be 'number', 'array' (helper), etc.
        # Assuming simple aggregation like 'max', 'min', 'sum' which returns a number
        # Or 'show original' which returns array. 
        # Checking for 'number' first which is common for aggregations
        if rollup.get("type") == "number":
             return rollup.get("number")
        
        # If it's an array of numbers (e.g. show original)
        if rollup.get("type") == "array" and rollup.get("array"):
             # We take the first one found ? Or assume it's unique ? 
             # Logic said: "si propriété nombre ITEM est remplie... same number". 
             # Let's take the first non-null number
             for item in rollup["array"]:
                 if item.get("type") == "number":
                     return item.get("number")
        
        return None

    @staticmethod
    def extract_rollup_content(prop: dict) -> Optional[str]:
        """
        Extract content from a Rollup property (URL or Relation id -> constructed URL).
        Prioritizes URL, then Relation, then Rich Text link.
        """
        if not prop or "rollup" not in prop:
            return None
        
        rollup = prop["rollup"]
        if rollup.get("type") != "array" or "array" not in rollup:
             return None
             
        for item in rollup["array"]:
             # Case 1: Direct URL
             if item.get("type") == "url" and item.get("url"):
                 return item.get("url")
             
             # Case 2: Relation (construct URL)
             if item.get("type") == "relation" and item.get("relation"):
                 page_id = item["relation"].get("id")
                 if page_id:
                     return f"https://www.notion.so/{page_id.replace('-', '')}"
            
             # Case 3: Rich Text (with link) - detected in debug logs
             if item.get("type") == "rich_text" and item.get("rich_text"):
                 for rt in item["rich_text"]:
                     if rt.get("href"):
                         return rt.get("href")
                     if rt.get("text") and rt["text"].get("link"):
                         return rt["text"]["link"].get("url")
        
        return None

    @staticmethod
    def extract_formula_string(prop: dict) -> Optional[str]:
         """Extract string from a Formula property."""
         if not prop or "formula" not in prop:
             return None
         formula = prop["formula"]
         if formula.get("type") == "string":
             return formula.get("string")
         return None

    @staticmethod
    def extract_status(prop: dict) -> Optional[str]:
        """Extract value from a Status property."""
        if not prop or "status" not in prop or not prop["status"]:
            return None
        return prop["status"]["name"]

class Cours(BaseModel):
    id: str
    title: str
    item_number: Optional[str] = None
    item_lie: Optional[str] = None
    college: List[str] = []
    semestre: Optional[str] = None
    ue_id: Optional[str] = None
    created_time: datetime

    # Champs Collège
    url_pdf: Optional[str] = None
    rappel_done: bool = False
    date_1ere_lecture: Optional[date] = None
    lecture_j3_college: Optional[date] = None
    lecture_j7_college: Optional[date] = None
    lecture_j14_college: Optional[date] = None
    lecture_j30_college: Optional[date] = None
    agregation_fiche_edn: Optional[str] = None
    nb_lectures: int = 0
    anki: bool = False

    # Champs UE/Semestre
    url_pdf_ue: Optional[str] = None
    rappel_ue_done: bool = False
    date_1ere_lecture_ue: Optional[date] = None
    lecture_j3_ue: Optional[date] = None
    lecture_j7_ue: Optional[date] = None
    lecture_j14_ue: Optional[date] = None
    lecture_j30_ue: Optional[date] = None
    nb_lectures_ue: int = 0

    # Statut et QCM
    course_status: str = "À lire"
    qcm_done: bool = False
    resume_done: bool = False
    chatgpt_done: bool = False

    # Obsidian — URI obsidian:// écrit par Synapse après création/sync de note
    obsidian_uri: Optional[str] = None

    def __hash__(self):
        return hash(self.id)

    @model_validator(mode="after")
    def _union_of_college_sources(self):
        """Complète les collèges Notion par celui du référentiel EDN.

        Un item comme « Tuberculose de l'adulte et de l'enfant » est enseigné en
        Pédiatrie *et* en Infectiologie. Notion n'en portait qu'un, le référentiel
        l'autre, et l'écart — 289 cours — était lu comme une contradiction. C'est
        une double appartenance légitime : chaque liste de collège doit être
        complète vis-à-vis du programme officiel, sans écraser l'organisation de
        l'utilisateur, qui reste en tête de liste.

        Le validateur porte sur le modèle et non sur la lecture Notion : il
        s'applique donc aussi aux cours reconstruits depuis le cache disque.
        """
        from backend.core.qcm.items_mapping import resolve

        raw = str(self.item_number or "").strip()
        if not raw:
            return self
        try:
            number = int(float(raw))
        except (TypeError, ValueError):
            return self
        _title, referential_college = resolve(number)
        if not referential_college:
            return self

        colleges = [str(c).strip() for c in (self.college or []) if str(c).strip()]
        if not any(referential_college in c or c in referential_college for c in colleges):
            colleges.append(referential_college)
            object.__setattr__(self, "college", colleges)
        return self

    @property
    def display_item_number(self) -> str:
        """Numéro ITEM formaté depuis item_number uniquement — jamais item_lie (UUID Notion)."""
        raw = (self.item_number or "").strip()
        if not raw:
            return ""
        try:
            f = float(raw)
            return str(int(f)) if f.is_integer() else str(f)
        except (ValueError, TypeError):
            return ""

    @property
    def display_title(self) -> str:
        """Titre complet : 'ITEM X – Titre' ou 'Titre' si pas de numéro ITEM valide."""
        item = self.display_item_number
        return f"ITEM {item} – {self.title}" if item else self.title

    @classmethod
    def from_notion(cls, page: dict):
        props = page.get("properties", {})

        # Fiche EDN : essaie les deux noms possibles (migration DB)
        f_edn_prop = props.get(P.FICHE_EDN) or props.get(P.FICHE_EDN_ALT)

        # Anki : propriété UE ("Anki") — fallback collège ("Anki collège")
        anki_prop = props.get(P.ANKI_UE) or props.get(P.ANKI_COLLEGE)
        anki_checked = False
        if anki_prop and anki_prop.get("type") == "checkbox":
            anki_checked = anki_prop.get("checkbox", False)

        return cls(
            id=page["id"],
            title=NotionProperty.extract_title(props.get(P.COURS_TITLE)),
            item_number=str(NotionProperty.extract_number(props.get(P.ITEM))) if NotionProperty.extract_number(props.get(P.ITEM)) is not None else "",
            item_lie=(lambda x: x[0] if x else "")(NotionProperty.extract_relation(props.get(P.ITEM_LIE))),
            college=NotionProperty.extract_multi_select(props.get(P.COLLEGE)),
            semestre=NotionProperty.extract_select(props.get(P.SEMESTRE)),
            ue_id=(lambda x: x[0] if x else None)(NotionProperty.extract_relation(props.get(P.UE))),
            created_time=datetime.fromisoformat(page["created_time"].replace('Z', '+00:00')),

            url_pdf=NotionProperty.extract_url(props.get(P.URL_PDF_COLLEGE)),
            rappel_done=NotionProperty.extract_checkbox(props.get(P.RAPPEL_COLLEGE)),
            date_1ere_lecture=NotionProperty.extract_date(props.get(P.DATE_LECTURE_COLLEGE)),
            lecture_j3_college=NotionProperty.extract_date(props.get(P.LECTURE_J3_COLLEGE)),
            lecture_j7_college=NotionProperty.extract_date(props.get(P.LECTURE_J7_COLLEGE)),
            lecture_j14_college=NotionProperty.extract_date(props.get(P.LECTURE_J14_COLLEGE)),
            lecture_j30_college=NotionProperty.extract_date(props.get(P.LECTURE_J30_COLLEGE)),

            url_pdf_ue=NotionProperty.extract_url(props.get(P.URL_PDF_UE)),
            rappel_ue_done=NotionProperty.extract_checkbox(props.get(P.RAPPEL_UE)),
            date_1ere_lecture_ue=NotionProperty.extract_date(props.get(P.DATE_LECTURE_UE)),
            lecture_j3_ue=NotionProperty.extract_date(props.get(P.LECTURE_J3_UE)),
            lecture_j7_ue=NotionProperty.extract_date(props.get(P.LECTURE_J7_UE)),
            lecture_j14_ue=NotionProperty.extract_date(props.get(P.LECTURE_J14_UE)),
            lecture_j30_ue=NotionProperty.extract_date(props.get(P.LECTURE_J30_UE)),

            agregation_fiche_edn=(
                NotionProperty.extract_rollup_content(f_edn_prop) or
                NotionProperty.extract_formula_string(f_edn_prop) or
                (lambda x: f"https://www.notion.so/{x[0].replace('-', '')}" if x else None)(
                    NotionProperty.extract_relation(f_edn_prop)
                ) or
                NotionProperty.extract_url(f_edn_prop)
            ),

            nb_lectures=int(NotionProperty.extract_number(props.get(P.NB_LECTURES_COLLEGE)) or 0),
            nb_lectures_ue=int(NotionProperty.extract_number(props.get(P.NB_LECTURES_UE)) or 0),
            anki=anki_checked,

            course_status=(
                NotionProperty.extract_status(props.get(P.STATUT_COURS))
                or NotionProperty.extract_select(props.get(P.STATUT_COURS))
                or "À lire"
            ),
            qcm_done=NotionProperty.extract_checkbox(props.get(P.QCM_COLLEGE)),
            resume_done=NotionProperty.extract_checkbox(props.get(P.RESUME_COLLEGE)),
            chatgpt_done=NotionProperty.extract_checkbox(props.get(P.CHATGPT_COLLEGE)),

            obsidian_uri=NotionProperty.extract_rich_text(props.get(P.OBSIDIAN)) or None,
        )

class DailyFollowUp(BaseModel):
    id: str
    title: str
    date: Optional[date]
    status: Optional[str] = "À faire"
    checkboxes: dict[str, bool] = {}
    dynamic_checkboxes: dict[str, dict] = {} # {block_id: {"text": str, "checked": bool}}

    @classmethod
    def from_notion(cls, page: dict):
        props = page.get("properties", {})
        
        # ... (static checkboxes logic) ...
        # Define the specific checkbox keys we track
        checkbox_keys = [
             "🧠 Révision matin",
             "🧠 Révision après-midi",
             "✅ QCM",
             "🥗 Alimentation saine",
             "💧 Hydratation",
             "👊 Sport",
             "🧘 Mobilité",
             "😴 Sommeil de qualité",
             "📅 Planification rapide du lendemain",
             "📅 Planification lendemain",
             "📚 Lecture"
        ]

        # Only extract keys that actually exist in the page properties
        extracted_checkboxes = {}
        for key in checkbox_keys:
            if key in props:
                extracted_checkboxes[key] = NotionProperty.extract_checkbox(props.get(key))

        return cls(
            id=page["id"],
            title=NotionProperty.extract_title(props.get("Name")), # Title is "Name"
            date=NotionProperty.extract_date(props.get("Date")),
            status=NotionProperty.extract_status(props.get("Status")) or "À faire",
            checkboxes=extracted_checkboxes,
            dynamic_checkboxes={} # Will be populated by service fetching blocks
        )
