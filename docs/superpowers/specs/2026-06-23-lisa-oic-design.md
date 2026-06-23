# Spec — Objectifs de Connaissance LiSA (OIC)

**Date :** 2026-06-23  
**Statut :** validé  

---

## Contexte

Les cours EDN sont structurés en **Objectifs de Connaissance (OIC)** classés Rang A et Rang B. Le Rang A conditionne la validation de l'EDN (seuil 14/20). Le Rang B différencie les candidats aux spécialités. Ces données sont publiquement disponibles sur les fiches LiSA (`livret.uness.fr/lisa/2026/{titre}`), dont l'URL est déjà construite dans `course_card.py:104-105`.

L'objectif est d'afficher et de suivre les OIC par cours, avec une progression indépendante Rang A / Rang B.

---

## Architecture

Trois nouveaux éléments, une modification mineure de `course_card.py` :

```
backend/core/lisa/
    __init__.py
    scraper.py              ← fetch HTML LiSA + parse table OIC

backend/core/reviews/
    local_store.py          ← +table lisa_oic, +3 fonctions CRUD

frontend/components/
    lisa_dialog.py          ← dialog OIC, checkboxes, barres de progression
```

`course_card.py` : ajout d'un item "📋 Objectifs (OIC)" dans le menu `⋯`, juste après "Fiche LISA".

---

## Scraper (`backend/core/lisa/scraper.py`)

**Entrée :** `course_title: str`, `item_number: str`  
**Sortie :** `list[dict]` — liste des OIC parsés

**Flux :**
1. Construit l'URL : même logique que `course_card.py:104` — `urllib.parse.quote(title.replace(" ", "_"), safe="_-()")`  
   → `https://livret.uness.fr/lisa/2026/{slug}`
2. `requests.get(url, timeout=10)` — `requests` déjà installé dans le projet
3. Parse avec `html.parser` (stdlib, aucune dépendance supplémentaire)
4. Cible la table HTML contenant les colonnes Intitulé / Rang / Rubrique / Ordre
5. Extrait le code OIC depuis l'intitulé via regex : `OIC-{item}-{ordre:02d}-{rang}`

**Format de retour :**
```python
[
  {
    "oic_code":  "OIC-223-01-A",
    "intitule":  "Connaître l'évaluation du risque cardiovasculaire global",
    "rang":      "A",
    "rubrique":  "Définition",
    "ordre":     1,
  },
  ...
]
```

**Gestion d'erreurs :**
- Timeout ou réseau KO → lève `LisaFetchError` (exception custom)
- Page introuvable (404) → retourne `[]`
- Table absente (structure HTML inattendue) → retourne `[]` + log warning

---

## SQLite (`local_store.py`)

### Table `lisa_oic`

```sql
CREATE TABLE IF NOT EXISTS lisa_oic (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    course_id   TEXT    NOT NULL,
    oic_code    TEXT,
    intitule    TEXT    NOT NULL,
    rang        TEXT    NOT NULL,    -- "A" ou "B"
    rubrique    TEXT,
    ordre       INTEGER,
    mastered    INTEGER NOT NULL DEFAULT 0,  -- 0/1
    fetched_at  TEXT    NOT NULL             -- ISO date du dernier scrape
);
CREATE INDEX IF NOT EXISTS idx_lisa_oic_course ON lisa_oic(course_id);
```

### Fonctions CRUD

**`get_lisa_oic(course_id: str) -> list | None`**  
- Retourne `None` si aucune ligne pour ce cours (= jamais fetché)  
- Retourne `[]` si fetché mais LiSA n'a rien retourné  
- Retourne la liste des rows sinon  

**`upsert_lisa_oic(course_id: str, oics: list[dict]) -> None`**  
- Supprime les anciennes lignes du cours  
- Ré-insère toutes les nouvelles  
- Préserve les `mastered` existants via match sur `oic_code`  
- Met à jour `fetched_at` avec la date du jour  

**`toggle_lisa_oic_mastery(oic_id: int) -> bool`**  
- Bascule `mastered` 0↔1  
- Retourne le nouvel état (`True` = maîtrisé)  

---

## Frontend (`frontend/components/lisa_dialog.py`)

### Point d'entrée

Fonction `open_lisa_dialog(course)` appelée depuis `course_card.py`.

### Comportement à l'ouverture

```
cache SQLite présent ?
  oui → affiche directement
  non → spinner "Chargement depuis LiSA…"
         → asyncio.to_thread(scrape_oic)
         → upsert_lisa_oic
         → affiche
         → erreur réseau → message + bouton "Réessayer"
```

### Layout du dialog

```
┌─────────────────────────────────────────────────┐
│  ITEM 223 — Dyslipidémies                  [↺]  │
│  Rang A : ████████░░  6/9 maîtrisés             │
│  Rang B : ███░░░░░░░  3/8 maîtrisés             │
├───────────────────┬─────────────────────────────┤
│  RANG A           │  RANG B                     │
│  ───────────────  │  ───────────────            │
│  ☑ Connaître l'  │  ☐ Connaître les relations  │
│    [Définition]   │    [Physiopathologie]        │
│  ☐ Connaître les │  ☐ …                        │
│    [Définition]   │                             │
│  …               │                             │
└───────────────────┴─────────────────────────────┘
```

**Détails UI :**
- Deux barres de progression indépendantes (Rang A / Rang B)
- Chaque OIC : `ui.checkbox` + intitulé complet + chip rubrique (gris, petit)
- `[↺]` = bouton "Actualiser depuis LiSA" → re-scrape + preserve mastered
- Toggle checkbox → `toggle_lisa_oic_mastery` → recalcul barres en temps réel (optimistic update)
- Les deux colonnes scrollent indépendamment si liste longue

### Intégration `course_card.py`

Dans le menu `⋯`, après l'item "Fiche LISA" :

```python
ui.menu_item(
    "📋 Objectifs (OIC)",
    on_click=lambda c=course: open_lisa_dialog(c),
).classes("text-xs")
```

---

## Ce que ce design ne fait PAS

- Pas de pré-chargement au démarrage (on-demand seulement, cache SQLite après)
- Pas de lien automatique OIC → lacune (hors scope)
- Pas de suivi agrégé multi-cours (hors scope pour cette version)
- Pas de gestion du changement d'année LiSA (URL hardcodée sur 2026)

---

## Fichiers modifiés

| Fichier | Type de changement |
|---|---|
| `backend/core/lisa/__init__.py` | Nouveau (vide) |
| `backend/core/lisa/scraper.py` | Nouveau |
| `backend/core/reviews/local_store.py` | +table +3 fonctions |
| `frontend/components/lisa_dialog.py` | Nouveau |
| `frontend/components/course_card.py` | +1 item menu |
