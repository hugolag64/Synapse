# Chantier D — Calendriers Google configurables depuis Paramètres

**Date** : 2026-08-09
**Statut** : design validé, prêt pour plan d'implémentation

## Contexte

Dernier chantier de la feuille de route (voir `docs/UI_REFONTE_ETAT_DES_LIEUX.md` section 6).
Périmètre initial du grief utilisateur (7 août 2026) : « pas de vue semaine réelle (cours fac +
cours Synapse), seulement plannif du jour/passé. » L'utilisateur ne se souvenait plus du détail
exact du grief au moment de reprendre ce chantier (2026-08-09).

**Investigation** : la vue semaine réelle existe déjà. `frontend/pages/planning_cockpit.py`
(construite en `42fd8b1`, avant même la revue du 7 août) affiche une grille 7/3/1 jours navigable
avec les tâches Synapse **et** les événements Google Calendar (bord pointillé) côte à côte, jour par
jour. Le mécanisme multi-calendriers existe aussi côté backend :
`Settings.get_calendar_ids()` (`backend/config/settings.py:129-138`) lit `GOOGLE_CALENDAR_IDS`
depuis `.env` (liste séparée par virgules), et
`GoogleCalendarService.get_events_for_day()` (`backend/core/google/calendar_service.py:121-190`)
interroge `["primary"] + configured_ids` en parallèle — avec même un correctif codé en dur pour un
ID de calendrier spécifique (`dm1rlvvim8vemcspm4momjq8f7qfqc3g@import.calendar.google.com`, tagué
« Agenda FAC » en commentaire, +4h car Google renvoyait les horaires 4h en avance).

**Le vrai trou** : aucune UI ne permet de gérer ces IDs. Il faut éditer `.env` à la main puis
redémarrer l'app (les `Settings` Pydantic ne se rechargent qu'au démarrage). L'utilisateur confirme
(2026-08-09) : pas de cours de fac actuellement visibles (période de vacances, donc rien à tester
en ce moment), et demande explicitement : « pouvoir juste mettre dans paramètre des ID de calendrier
à rajouter ».

Décisions actées avec l'utilisateur avant la spec :
- Gestion **sans redémarrage** (comme les autres préférences planning déjà en base — capacité,
  vacances), pas une simple UI d'écriture dans `.env`.
- Les événements affichent la **source** (label du calendrier) dans la grille, pas seulement un
  bord pointillé générique.

## Objectif

Depuis Paramètres, ajouter/retirer des IDs de calendrier Google avec un label, effet immédiat sur la
grille Planning (aucun redémarrage), événements étiquetés par leur source.

## Périmètre

### 1. Stockage — préférence `planning_calendar_sources`

Nouvelle clé dans `data_store.preferences`, liste de `{"id": str, "label": str}`, même mécanisme que
`planning_capacity_minutes`/`planning_vacation` déjà lus/écrits dans `planning_cockpit.py` via
`data_store.set_preference(...)`. Le `.env` (`GOOGLE_CALENDAR_IDS`, donc aussi l'ID « Agenda FAC »
déjà en dur) reste lu en plus, sans changement — les deux sources coexistent et se combinent.

Fonctions ajoutées (nouveau module `backend/core/planning/calendar_sources.py`, cohérent avec les
autres modules de `backend/core/planning/` déjà spécialisés — `policy.py`, `focus.py`,
`calendar_actions.py`, `cockpit_schedule.py`) :

```python
def list_calendar_sources(preferences: dict) -> list[dict]:
    """Lit planning_calendar_sources, normalisé (liste vide si absent/invalide)."""

def add_calendar_source(sources: list[dict], calendar_id: str, label: str) -> list[dict]:
    """Retourne une nouvelle liste avec l'entrée ajoutée.
    Rejette (ValueError) un ID vide après strip(). Si l'ID existe déjà, remplace son label
    plutôt que de dupliquer l'entrée."""

def remove_calendar_source(sources: list[dict], calendar_id: str) -> list[dict]:
    """Retourne une nouvelle liste sans l'entrée dont l'ID correspond."""
```

Fonctions pures (liste en entrée/sortie, pas d'accès à `data_store` ni `ui`) — le composant frontend
lit/écrit `data_store.preferences["planning_calendar_sources"]` autour de ces appels, comme
`_open_capacity_dialog` le fait déjà pour `planning_capacity_minutes`.

### 2. Fusion + étiquetage dans `get_events_for_day`

`backend/core/google/calendar_service.py:143-151` fusionne actuellement
`["primary"] + configured_ids` (depuis `.env` seul). Étendu pour inclure aussi les IDs de
`data_store.preferences["planning_calendar_sources"]`, dédupliqués (ordre : primary, `.env`,
préférences — un même ID présent dans `.env` et en préférence n'est interrogé qu'une fois).

Chaque événement retourné par `fetch_calendar(cal_id)` reçoit une clé `_synapse_source_label`
(chaîne vide si `cal_id` ne correspond à aucune entrée `planning_calendar_sources` — donc aucun
changement de comportement pour `primary` ou les IDs `.env` non étiquetés). Le correctif +4h de
l'« Agenda FAC » reste inchangé, indexé par ID littéral, indépendant de la source (env ou
préférence).

### 3. Panneau Paramètres — `frontend/components/calendar_sources_panel.py`

Nouveau composant, même pattern que `dp_coverage_panel.py`/`uness_diagnostic_panel.py` (fonction
`render(container)` + fonctions de données pures testables séparément). Contenu :
- Liste des sources configurées : ID (tronqué, police mono) + label + bouton retirer.
- Formulaire d'ajout : champ ID (`ui.input`), champ Label (`ui.input`), bouton « Ajouter ».
- Validation : ID vide (après `strip()`) → notification d'erreur, pas d'ajout (pas de vérification
  d'existence côté Google API — une erreur de fetch sur un mauvais ID est déjà silencieusement
  absorbée par `fetch_calendar`'s `try/except`, cf. `calendar_service.py:188-190`, donc pas de risque
  de crash). Le label est optionnel : laissé vide, la ligne de la liste affiche l'ID seul et aucun
  préfixe n'apparaît sur les événements dans la grille (même traitement qu'un ID `.env` non étiqueté).

Intégré dans `frontend/pages/settings_cockpit.py`, nouvelle section `ui.label("CALENDRIERS")` (même
convention `.se-label` que CONNEXIONS/APPARENCE/PLANIFICATION EDN), placée juste après la section
CONNEXIONS existante (où le statut Google Calendar est déjà affiché) — cohérence de proximité
thématique.

### 4. Étiquette dans la grille Planning

`planning_cockpit.py::_draw_day` (boucle `for ev in events`, ligne ~458-465) : si
`ev.get("_synapse_source_label")` est non vide, l'affiche en préfixe du titre de l'événement
(ex. `Fac · Cours de sémiologie`) au lieu du seul `summary`. Nouvelle règle CSS mineure si besoin
d'un style de préfixe distinct (à trancher pendant l'implémentation selon rendu réel — pas de
nouvelle couleur décorative, réutilise `var(--text-dim)` déjà utilisé pour les labels secondaires
dans ce fichier).

## Hors périmètre

- Pas de vérification d'existence/validité de l'ID (appel Google API) au moment de l'ajout — la
  validation se fait à l'usage (fetch échoue silencieusement si l'ID est mauvais, comportement déjà
  en place).
- Le correctif +4h « Agenda FAC » codé en dur n'est pas généralisé (pas de champ « décalage horaire »
  par calendrier dans le formulaire) — dette technique déjà identifiée mais hors demande explicite de
  l'utilisateur pour ce chantier.
- Pas de migration automatique des IDs `.env` existants vers `planning_calendar_sources` — les deux
  mécanismes coexistent, l'utilisateur peut ajouter ses IDs `.env` actuels via l'UI s'il veut les
  gérer au même endroit, ou les laisser tels quels.
- Pas de couleur/icône par calendrier au-delà du label texte — pas demandé, ajouté seulement si le
  besoin apparaît après usage réel.

## Risques

- **Double-comptage si un ID figure à la fois dans `.env` et en préférence.** Géré par déduplication
  explicite dans `get_events_for_day` (un seul appel `fetch_calendar` par ID unique, quelle que soit
  la source) — sinon l'événement apparaîtrait deux fois dans la grille.
- **Préférences absentes ou mal formées** (`planning_calendar_sources` absent, ou pas une liste de
  dicts — ex. après une modification manuelle du fichier de préférences) : `list_calendar_sources`
  doit retourner `[]` plutôt que lever une exception, même pattern défensif que `_target_for`
  (`planning_cockpit.py:170-173`) qui vérifie déjà `isinstance(value, dict)`.
- **ID dupliqué ajouté deux fois via le formulaire** : `add_calendar_source` remplace l'entrée
  existante (par ID) plutôt que d'ajouter un doublon.

## Tests

- `list_calendar_sources` / `add_calendar_source` / `remove_calendar_source` : liste vide par défaut ;
  ajout normal ; ajout avec ID déjà présent remplace le label sans dupliquer ; ajout avec ID vide/
  espaces seuls lève `ValueError` ; retrait d'un ID absent ne lève pas d'erreur (liste inchangée) ;
  préférence mal formée (pas une liste, ou entrées sans clé `id`) traitée comme vide plutôt que de
  planter.
- `get_events_for_day` (extension du pattern `FakeService`/`FakeEvents` de
  `tests/test_planning_calendar_actions.py`) : un ID présent uniquement en préférence est bien
  interrogé ; un ID présent à la fois en `.env` et en préférence n'est interrogé qu'une fois ; les
  événements d'un calendrier étiqueté portent `_synapse_source_label` correct ; les événements de
  `primary` ou d'un ID `.env` non étiqueté ont `_synapse_source_label` vide (pas de régression sur le
  comportement actuel).
- Rendu de la grille (fonction extraite si besoin, ex. `event_display_title(ev) -> str`, même esprit
  que `block_target` déjà extrait dans `planning_cockpit.py:67-79`) : événement avec label →
  préfixe affiché ; événement sans label → titre seul, identique au comportement actuel.
- Suite complète (`./.venv/Scripts/python.exe -m pytest -q`) avant la première tâche et après la
  dernière.
