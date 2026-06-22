"""
MedicalSearchIndex — Synapse
-----------------------------
Index de recherche locale ultra-rapide basé sur rapidfuzz.

Spécificités médicales :
  - Priorité aux numéros ITEM (ITEM 228 > "insuffisance")
  - Expansion d'abréviations médicales : "ic" → "insuffisance cardiaque"
  - Insensible aux accents via rapidfuzz default_process
  - Correction typo : "pnumonie" → "Pneumonie" (WRatio > 60)

Usage :
    from backend.core.search.service import search_index

    # Construire/reconstruire après sync Notion
    search_index.build(data_store.cours)

    # Rechercher
    hits = search_index.search("ic aigue", limit=8)
    # → [(Cours, score), ...]
"""
from __future__ import annotations

from rapidfuzz import fuzz, process
from rapidfuzz.utils import default_process

from backend.core.notion.models import Cours


class MedicalSearchIndex:
    """Index fuzzy médical avec expansion d'abréviations et priorité ITEM."""

    MEDICAL_ABBREVS: dict[str, str] = {
        "ic":   "insuffisance cardiaque",
        "irc":  "insuffisance rénale chronique",
        "ira":  "insuffisance rénale aiguë",
        "oap":  "oedème aigu pulmonaire",
        "ep":   "embolie pulmonaire",
        "fa":   "fibrillation auriculaire",
        "bpco": "bronchopneumopathie chronique obstructive",
        "avc":  "accident vasculaire cérébral",
        "iam":  "infarctus aigu du myocarde",
        "hta":  "hypertension artérielle",
        "dm":   "diabète",
        "sep":  "sclérose en plaques",
        "mii":  "maladie inflammatoire intestin",
        "rch":  "rectocolite hémorragique",
        "mch":  "maladie de crohn",
        "ins":  "insuffisance",
        "ira":  "insuffisance rénale aiguë",
        "iag":  "insuffisance aortique",
        "im":   "insuffisance mitrale",
        "ht":   "hypertension",
    }

    def __init__(self) -> None:
        # [(search_key, display_label, Cours)]
        self._index: list[tuple[str, str, Cours]] = []
        # Pré-calculé dans build() — {search_key: Cours} — évite O(N) rebuild par appel
        self._choices: dict[str, Cours] = {}
        self._built = False

    def build(self, courses: list[Cours]) -> None:
        """Construit l'index depuis la liste de cours. Appeler après sync Notion."""
        self._index = []
        for c in courses:
            label = c.display_title
            keys = [
                c.title,
                f"item {c.item_number}" if c.item_number else "",
                f"ITEM {c.item_number}" if c.item_number else "",
                " ".join(c.college) if c.college else "",
            ]
            for key in filter(None, keys):
                self._index.append((key, label, c))
        # Pré-construire le dict pour search() — une seule fois au lieu de N fois
        self._choices = {s: c for s, _, c in self._index}
        self._built = True

    def search(
        self,
        query: str,
        limit: int = 10,
        score_cutoff: int = 60,
    ) -> list[tuple[Cours, int]]:
        """
        Retourne [(cours, score)] triés par pertinence décroissante.

        Priorité :
          1. Match exact numéro ITEM → score forcé 100
          2. Expansion abréviation médicale
          3. Token sort ratio (insensible à l'ordre des mots)
        """
        if not self._built:
            from backend.state.store import data_store
            self.build(data_store.cours)

        q = query.strip().lower()
        if not q:
            return []

        results: dict[str, tuple[Cours, int]] = {}

        # 1. Match ITEM exact : "228" ou "item 228"
        item_query = q.replace("item", "").strip()
        if item_query.isdigit():
            for _, _, c in self._index:
                if c.item_number and c.item_number.strip() == item_query:
                    results[c.id] = (c, 100)
            if results:
                return sorted(results.values(), key=lambda x: -x[1])[:limit]

        # 2. Expansion abréviation médicale
        expanded = self.MEDICAL_ABBREVS.get(q, q)

        # 3. Recherche fuzzy token sort (agnostique à l'ordre)
        token_matches = process.extract(
            expanded,
            list(self._choices.keys()),
            scorer=fuzz.token_sort_ratio,
            limit=limit * 3,
            score_cutoff=score_cutoff,
            processor=default_process,
        )

        for match_str, score, _ in token_matches:
            c = self._choices[match_str]
            cid = c.id
            if cid not in results or results[cid][1] < score:
                results[cid] = (c, int(score))

        return sorted(results.values(), key=lambda x: -x[1])[:limit]

    def invalidate(self) -> None:
        """Force un rebuild au prochain appel search()."""
        self._built = False
        self._index = []
        self._choices = {}


# Singleton global
search_index = MedicalSearchIndex()
