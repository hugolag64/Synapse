# Chantier B3 — Polish créatif

**Date** : 2026-08-07
**Statut** : design validé (direction A retenue via visual companion), prêt pour plan d'implémentation

## Contexte

Suite du chantier B2 (les deux wizards, terminé — 3 commits, 1137 tests). Voir
[docs/UI_REFONTE_ETAT_DES_LIEUX.md](../../UI_REFONTE_ETAT_DES_LIEUX.md) pour la vue d'ensemble.

B3 couvre les deux derniers points « visuels » signalés par l'utilisateur qui ne sont pas de simples
corrections de tokens : l'animation d'expansion des collèges (« trop brute ») et le caractère peu
engageant de la page Prépa (« suite de liens, pas ludique »).

Trois directions visuelles pour Prépa ont été présentées via le visual companion (relief au survol +
récents / identité de couleur par plateforme / mouvement seul) — l'utilisateur a choisi la première,
qui évite d'introduire une couleur non-sémantique tout en rendant la page plus vivante.

## Objectif

Rendre l'ouverture d'un collège visuellement fluide dans les limites de l'architecture existante, et
donner à Prépa une hiérarchie et un mouvement qui la distinguent d'une simple liste de liens — sans
toucher à la logique métier ni introduire de couleur décorative.

## Périmètre

### 1. Animation d'ouverture des collèges — `frontend/pages/colleges_cockpit.py`

**Contrainte technique confirmée.** `_toggle_expand` (ligne 529) appelle `_render()`, qui refait
`_compute()` et redessine **toute** la liste des collèges via `_draw_list` → `_draw_row` pour chaque
ligne visible. Le conteneur `.cg-items` (ligne 439) n'est donc jamais mis à jour en place : à chaque
bascule, l'ancien nœud disparaît et un nouveau est créé si le collège est développé. Une transition
CSS classique (`max-height`, `transition` sur un état qui change) est impossible ici puisqu'il n'y a
jamais de node persistant dont l'état change — il n'existe qu'un mount ou une absence.

**Décision — animation d'entrée rejouée à chaque montage.** Comme `.ans-view-animated` dans
`annales.py` (`@keyframes ansFadeIn`), on ajoute une classe dont le `@keyframes` joue automatiquement
à chaque fois que l'élément est monté dans le DOM — ce qui arrive précisément à chaque ouverture,
puisque le nœud est neuf. La fermeture reste instantanée (le nœud est simplement retiré) ; c'est une
limite assumée de l'architecture à reconstruction complète, pas un défaut du design.

Nouvelle règle CSS dans `_CSS` (`frontend/pages/colleges_cockpit.py`), à ajouter après la règle
`.cg-items` existante ligne 105 :
```css
@keyframes cgItemsEnter {
  0% { opacity: 0; transform: translateY(-8px); }
  100% { opacity: 1; transform: translateY(0); }
}
.cg-items-enter { animation: cgItemsEnter var(--duration-base) var(--ease-standard) both; }
```
La classe `cg-items-enter` est ajoutée à la classe existante du conteneur `.cg-items` (ligne 439) :
`ui.element("div").classes("cg-items cg-items-enter")` au lieu de `ui.element("div").classes("cg-items")`.

**Hors périmètre.** Aucun changement à `_toggle_expand`, `_compute`, `_render` ni à la structure de
la grille d'items à l'intérieur d'un collège développé — uniquement l'ajout de la classe d'animation
sur le conteneur englobant.

### 2. Section « Récemment consulté » — `backend/core/prep/catalog.py` + `frontend/pages/prepa.py`

**Donnée déjà disponible, jamais relue.** `record_prep_access(shortcut_id)`
(`backend/core/prep/catalog.py:85`) écrit déjà `last_used` à chaque clic sur un raccourci — mais
aucune fonction ne relit cette colonne. Aucune migration nécessaire.

**Décision.** Nouvelle fonction dans `catalog.py`, à la suite de `record_prep_access` :
```python
def list_recent_prep_shortcuts(limit: int = 5) -> list[dict]:
    _ensure_table()
    with local_store._conn() as con:
        rows = con.execute(
            "SELECT * FROM prep_shortcuts WHERE enabled=1 AND last_used IS NOT NULL "
            "ORDER BY last_used DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(row) for row in rows]
```

Dans `prepa.py`, une section « Récemment consulté » est insérée entre le fil d'ariane et la liste des
plateformes, **seulement si `list_recent_prep_shortcuts()` retourne au moins une ligne** — pas de
section vide ni de faux état « aucun récent ». Chaque tuile affiche le titre du raccourci et un
horodatage relatif (« à l'instant », « il y a Nh », « hier », « il y a Nj »), calculé localement à
partir de `last_used` (ISO 8601 UTC, comme écrit par `record_prep_access`). Cliquer une tuile déclenche
la même paire `record_prep_access(id)` + navigation (`ui.link(..., new_tab=True)`) qu'un raccourci
normal de la liste principale — pas de chemin de clic différent.

### 3. Relief au survol des tuiles — `frontend/pages/prepa.py`

**Décision.** La règle `.prep-shortcut:hover` (ligne 23) gagne un léger soulèvement et une ombre,
sur la transition déjà déclarée à la ligne 22 :
```css
.prep-shortcut { border:1px solid var(--border); border-radius:8px; padding:13px 14px; background:var(--bg-alt);
  transition:border-color .12s, background .12s, transform .12s, box-shadow .12s; }
.prep-shortcut:hover { border-color:var(--accent); background:var(--surface); transform:translateY(-2px); box-shadow:var(--shadow-popover); }
```

### 4. Apparition échelonnée au chargement — `frontend/pages/prepa.py`

**Décision.** Chaque section `.prep-provider` (2 à 3 selon les plateformes actives — voir
`_PROVIDERS` dans `catalog.py`) reçoit une animation d'entrée avec un délai croissant par position,
en CSS pur (pas de JS, pas de variable dynamique — le nombre de sections est petit et fixe) :
```css
@keyframes prepProviderEnter {
  0% { opacity: 0; transform: translateY(8px); }
  100% { opacity: 1; transform: translateY(0); }
}
.prep-provider { animation: prepProviderEnter var(--duration-base) var(--ease-standard) both; }
.prep-provider:nth-of-type(1) { animation-delay: 0ms; }
.prep-provider:nth-of-type(2) { animation-delay: 60ms; }
.prep-provider:nth-of-type(3) { animation-delay: 120ms; }
```

## Hors périmètre du chantier B3

- Aucun changement à `list_prep_providers`, `list_prep_shortcuts`, `build_prepa_view` — la donnée et
  son agrégation restent identiques, seule leur présentation évolue.
- Direction B (identité de couleur par plateforme), écartée par l'utilisateur : aucune couleur de
  wayfinding par plateforme n'est introduite.
- Déplacement du bloc Tuteur DP → **B4**.
- Toute autre page du cockpit (revue, stats, etc.) n'est pas concernée par ce chantier.

## Risques

- **Animation des collèges** : comme la fermeture reste instantanée par construction, un utilisateur
  qui ouvre puis referme rapidement plusieurs collèges verra une asymétrie (ouverture douce,
  fermeture nette). C'est un compromis assumé plutôt qu'un défaut à corriger — le corriger
  proprement demanderait de réécrire `_toggle_expand` pour ne redessiner qu'une ligne, hors
  périmètre de ce chantier visuel.
- **Section Récemment consulté** : si `last_used` est `NULL` pour tous les raccourcis (base neuve ou
  utilisateur n'ayant jamais cliqué), la section ne doit apparaître nulle part — à vérifier
  explicitement, car un oubli produirait un titre de section sans contenu.

## Tests

- Test de présence de la règle `@keyframes cgItemsEnter` et de la classe `cg-items-enter` sur le
  conteneur `.cg-items` dans `colleges_cockpit.py`.
- Tests unitaires pour `list_recent_prep_shortcuts()` : base vide → liste vide ; raccourcis avec et
  sans `last_used` → seuls ceux avec `last_used` renseigné sont retournés, triés du plus récent au
  plus ancien ; respect de `limit`.
- Test que la section « Récemment consulté » n'est pas rendue quand `list_recent_prep_shortcuts()`
  est vide, et qu'elle l'est quand elle ne l'est pas.
- Test de présence des règles CSS de survol (`transform`, `box-shadow`) et d'apparition échelonnée
  (`animation-delay` par `nth-of-type`) dans `prepa.py`.
- Suite complète (`pytest -q`) avant/après pour confirmer l'absence de régression.
