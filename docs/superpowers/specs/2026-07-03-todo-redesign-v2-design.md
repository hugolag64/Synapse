# To Do — refonte v2 (hero, strip semaine, panels, utile+++)

## Contexte

La page To Do (`frontend/pages/todo.py`, route `/todo`) a été construite en juin 2026 (spec `2026-06-23-todo-redesign.md`) : navigation par date, 3 blocs (Routine / Ajouté / Note du jour) à bordure colorée, barre de progression globale dans un en-tête sticky. Depuis, les pages QCM et Progression ont introduit un langage visuel commun (`static/synapse.css`) : hero banner en dégradé avec bordure gauche accent, KPI cards, ring de progression `.synapse-ring`, panels neutres `.synapse-panel`. La page To Do accuse un retard de cohérence visuelle par rapport à ces deux pages, et son ergonomie quotidienne peut être améliorée (ajout rapide peu visible, pas d'état vide travaillé, pas de vision semaine, pas de rattrapage en cas d'erreur de validation).

Confirmé avec l'utilisateur : périmètre = **structure visuelle** (hero + strip 7 jours + panels) + **fonctionnel utile+++** (état vide avec CTA, ajout rapide remonté, undo sur validation de cours, signal "reporté d'hier"). Pas de changement de sobriété colorimétrique dédié au-delà de l'adoption des panels standards. Pas de raccourcis clavier dans cette itération.

Décisions prises pendant le brainstorming (à défaut de réponse de l'utilisateur sur la première, choix du plus prudent) :
- **Pas de report automatique de données Notion.** Les tâches non faites de la veille ne sont ni déplacées ni dupliquées automatiquement — uniquement un badge de lecture seule "reporté d'hier" sur les cours manuels non faits, reprogrammation manuelle via `+ Cours`. Ce choix évite tout risque de duplication/perte sur l'API Notion.
- **La strip 7 jours affiche Routine (instantané) + Ajouté (Notion, chargé en arrière-plan)**, pas seulement la routine — validé explicitement par l'utilisateur malgré le coût de 7 appels Notion supplémentaires par affichage de page.
- **Undo limité à la validation de cours dans le bloc Ajouté** — seule action de l'UI actuelle avec effet de bord Notion difficile à annuler manuellement. La Routine reste réversible par simple déclic de case.

## 1. Vue-modèle partagée `_DaySummary`

Nouveau type en tête de `todo.py` :

```python
@dataclass
class _DaySummary:
    routine_done: int
    routine_total: int
    ajoute_done: int
    ajoute_total: int | None = None  # None tant que non chargé (Notion pas encore résolu)
```

Nouvelle fonction `_get_day_summary(date_obj, cache: dict[str, _DaySummary]) -> _DaySummary` :
- Partie routine : synchrone, lecture directe `local_store.get_routine_items()` / `get_routine_checks(date_str)` — toujours disponible immédiatement.
- Partie ajouté : asynchrone, réutilise la même logique que `_load_and_render_network_blocs` (task Notion du jour + `_build_course_list` + dynamic_checkboxes). Résultat écrit dans le cache une fois résolu.
- Le cache est un simple dict tenu dans le state de la page (clé = `date.isoformat()`), réinitialisé à chaque chargement de page (pas de persistance). Le rendu du jour principal et la strip 7 jours partagent ce cache pour ne jamais interroger Notion deux fois pour la même date dans la même session de page.

Le `progress_state` actuel (`{'routine': [t,d], 'ajout': [t,d]}`) est remplacé par la lecture directe du `_DaySummary` du jour courant dans le cache — pas de double comptabilité à maintenir en parallèle.

## 2. Hero banner

Remplace l'en-tête sticky actuel (navigation date + barre de progression, lignes ~397-421) par un bandeau `.synapse-hero` :
- Ligne 1 : date formatée (`_fmt_date`) en `synapse-heading`, boutons Hier/Auj/Demain + flèches ◀▶ conservés tels quels (même logique de state, juste replacés dans le nouveau conteneur), label date cliquable ouvrant le date picker (inchangé).
- Ligne 2 : `.synapse-ring` (% global du jour = `(routine_done+ajoute_done)/(routine_total+ajoute_total)`, gris tant qu'`ajoute_total` est `None`) + flamme streak (`local_store.get_streak_days()`, même style que `theme.py`) + badge "reporté d'hier" si au moins un cours manuel d'hier n'est pas fait (voir section 5).
- Le hero reste sticky (`position: sticky; top: 0`), remplace l'ancien conteneur, conserve le fond translucide + blur existant en le mappant sur les tokens `.synapse-hero`.

## 3. Strip 7 jours

Nouveau composant `_render_week_strip(container, state, cache, on_pick_day)`, sous le hero, au-dessus de la zone de contenu.

- 7 pastilles cliquables (aujourd'hui centré : J-3 à J+3), façon `.college-strip-card` mais compactes (largeur fixe ~48px, pas de scroll horizontal nécessaire à 7 éléments).
- Chaque pastille : jour abrégé (`Lun`, `Mar`...) + quantième, + un indicateur de complétion (anneau fin ou simple remplissage de fond, coloré selon % — réutilise la logique de couleur du `.synapse-ring`).
- Rendu en 2 passes : (1) immédiat avec uniquement `routine_done/routine_total` pour les 7 jours (synchrone, local) ; (2) une tâche async séquentielle (pas `asyncio.gather` — throttle volontaire pour ne pas envoyer 7 requêtes Notion en parallèle) qui résout `ajoute_*` jour par jour via `_get_day_summary` et met à jour la pastille correspondante au fur et à mesure.
- Clic sur une pastille : `on_pick_day(date)` → même chemin que les boutons Hier/Auj/Demain existants (`_render_day`).
- Le jour actif est visuellement distinct (bordure accent), même mécanique que `btn_auj`/`btn_hier` aujourd'hui.

## 4. Panels neutres pour les 3 blocs

`_render_routine_block`, `_render_ajout_block`, `_render_note_block` : le conteneur externe (actuellement `ui.row` avec `ui.element('div')` en guise de bordure colorée sky/violet/amber) devient un `.synapse-panel` (padding interne standard, pas de bordure gauche colorée). Le label de section (`ROUTINE`, `AJOUTÉ`, `NOTE DU JOUR`) passe sur la classe `.synapse-section-label` déjà définie dans `synapse.css` au lieu des classes Tailwind ad hoc actuelles. Aucun changement de contenu ou de logique interne à ces blocs au-delà de ce conteneur.

## 5. Signal "reporté d'hier"

Nouvelle fonction `_get_yesterday_carryover(date_obj) -> list[str]` (lecture seule) :
- Si `date_obj` n'est pas aujourd'hui, retourne `[]` (le badge n'a de sens que sur le jour courant).
- Sinon, récupère la fiche Notion d'hier (`get_daily_task_by_date(yesterday)`), puis `get_daily_manual_revision_courses(page_id)` moins ce qui apparaît dans `get_daily_reviewed_courses` (mêmes titres) → liste des titres de cours manuels non faits hier.
- Le hero affiche un badge "N reporté(s) d'hier" (cliquable → scroll vers le bloc Ajouté) si la liste est non vide. Pas de bouton "reprogrammer en masse" dans cette itération — l'utilisateur reprogramme individuellement via `+ Cours` comme aujourd'hui.

## 6. État vide avec CTA

Dans `_render_ajout_block`, quand `course_items` et `dynamic_tasks` sont vides : remplace le texte italique actuel par un bloc centré (icône `event_available` discrète + texte "Rien de planifié pour ce jour" + bouton `+ Ajouter un cours` qui déclenche directement `_open_add_course_dialog(date_obj, task)` — même dialogue que le bouton `+ Cours` existant, pas de nouveau flux).

## 7. Ajout rapide remonté

La zone de contrôles d'ajout (`+ Cours` + input libre + bouton envoyer, actuellement en bas du bloc Ajouté après la liste, lignes ~211-240) est déplacée en haut du panel, juste sous le label `AJOUTÉ`, avant la liste des cours/tâches. Le bouton `+ Cours` passe de `flat dense` à un style plus affirmé (`unelevated dense rounded`, cohérent avec les CTA primaires ailleurs dans l'app) pour gagner en visibilité. Aucun changement de comportement, uniquement position + poids visuel.

## 8. Undo sur validation de cours

Dans `_render_course_item._validate` : après succès de la validation (incrémentation + marquage Notion), la notification `ui.notify('Validé !', type='positive')` est remplacée par une notification avec action "Annuler" (`ui.notify(..., actions=[{'label': 'Annuler', ...}])`), affichée 5s. Si l'utilisateur clique "Annuler" dans ce délai :
- Décrémente `course.nb_lectures` (inverse de l'incrémentation locale).
- Retire le cours de la liste Notion appropriée : `mark_manual_revision_done` n'a pas d'inverse direct côté service actuel → nécessite une nouvelle fonction `notion_service.unmark_manual_revision_done(page_id, title)` pour le cas `notion_manual`, et une fonction équivalente `remove_course_from_daily_reviewed(page_id, title)` pour le cas `gcal`. Ce sont les deux seules additions à `backend/core/notion/service.py` de cette refonte, symétriques aux fonctions d'ajout existantes (`mark_manual_revision_done`, `add_course_to_daily_reviewed`).
- Réaffiche le bouton de validation (retire l'état "coché").
- Si le clic "Annuler" arrive après expiration du toast (course déjà retiré du cache d'affichage), aucune action — l'utilisateur revalide manuellement si besoin (pas de mécanisme de rattrapage au-delà des 5s, cohérent avec le pattern toast standard).

## 9. Données — additions backend minimales

Seules deux nouvelles fonctions dans `backend/core/notion/service.py`, symétriques à des fonctions existantes :
- `unmark_manual_revision_done(page_id: str, course_title: str) -> bool`
- `remove_course_from_daily_reviewed(page_id: str, course_title: str) -> bool`

Aucune autre fonction backend, aucune migration SQLite, aucun nouveau champ Notion.

## 10. Vérification

Lancement de l'app en local (`main.py`), contrôle visuel light/dark sur `/todo` :
- Navigation par date (flèches, boutons rapides, date picker, clic sur pastille de la strip) sans régression.
- Chargement de la strip : vérifier que les 7 pastilles affichent d'abord la routine puis se complètent progressivement avec Ajouté sans bloquer l'interaction.
- Validation d'un cours → toast avec Annuler → clic Annuler → cours repasse en non-validé, `nb_lectures` redescend.
- État vide (jour sans rien de programmé) → CTA visible et fonctionnel.
- Badge "reporté d'hier" visible uniquement sur le jour courant, seulement s'il y a des cours manuels non faits hier.

Tests unitaires (`tests/`) sur `_get_day_summary` (agrégation, cache hit/miss) et sur `_get_yesterday_carryover` (liste vide, tout fait, partiellement fait) avec mocks des appels Notion — pas de test end-to-end Notion (convention existante du projet).

## Hors scope

- Pas de report automatique / déplacement de données entre jours Notion.
- Pas de raccourci clavier pour l'ajout rapide dans cette itération.
- Pas de restylage colorimétrique des 3 blocs au-delà du passage à `.synapse-panel` (pas de nouvelle palette).
- Pas de bouton "reprogrammer en masse" pour les cours reportés — reprogrammation individuelle uniquement.
- Pas de parallélisation des 7 appels Notion de la strip (throttle volontaire, séquentiel).
- Pas de changement à la Routine (SQLite, `local_store.py`) au-delà de sa lecture par `_DaySummary`.
