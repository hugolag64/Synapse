# Progression — refonte visuelle complète (juillet 2026)

## Contexte

Suite de la refonte UI/UX de la page QCM (`frontend/pages/qcm.py`, juillet 2026) qui a introduit un hero banner, des KPI cards avec sparklines, un ring donut, et une palette unifiée sur les tokens `--s-*` de `static/synapse.css`. La page Progression (`frontend/pages/stats.py`, route `/stats`, libellé nav "Progression") accuse maintenant un retard de finition visuelle par rapport à QCM.

Confirmé avec l'utilisateur : la motivation est **purement visuelle** (le design est daté), pas un manque de données ou une mauvaise architecture d'info. L'architecture actuelle (3 onglets : Activité / À retravailler / Objectifs, mêmes données sous-jacentes) est conservée. Une seule addition fonctionnelle est incluse : une barre de répartition de maîtrise globale, validée explicitement par l'utilisateur.

## 0. Renommage des classes CSS partagées (préalable)

Les classes introduites pour QCM sont génériques dans leur usage (tokens `--s-*`) mais nommées avec le préfixe `qcm-`, ce qui n'a plus de sens dès qu'une 2ᵉ page les utilise. Renommage dans `static/synapse.css` et dans les deux pages appelantes :

| Ancien nom | Nouveau nom |
|---|---|
| `.qcm-hero` | `.synapse-hero` |
| `.qcm-kpi-card` | `.synapse-kpi-card` |
| `.qcm-ring` / `.qcm-ring-label` | `.synapse-ring` / `.synapse-ring-label` |

`frontend/pages/qcm.py` est mis à jour pour utiliser les nouveaux noms (recherche/remplacement direct, aucun changement de style). Toute règle CSS `body.body--dark .qcm-*` suit le même renommage.

## 1. Hero banner

Remplace le bloc titre actuel (`stats_page()`, lignes ~627-638) par `.synapse-hero` (dégradé bleu léger, bordure gauche accent `--s-primary-600`) :
- Titre "Ma Progression" (`text-2xl font-extrabold`)
- Sous-titre "Historique d'apprentissage · tendances · objectifs" (inchangé)

## 2. Rangée de 4 KPI cards

Nouvelle rangée sous le hero, au-dessus des onglets, visible sur les 3 onglets (calculée une fois avec la période sélectionnée dans l'onglet Activité — 7j/30j/Tout — via le sélecteur existant `_rebuild_period_row`).

Cards `.synapse-kpi-card` (bordure gauche `--card-accent`, sparkline SVG à droite comme QCM `_sparkline_svg`) :

1. **Temps d'étude** — `local_store.get_weekly_study_stats(days)["total_minutes"]`, formaté via `_fmt_minutes`. Sparkline : minutes par jour sur la période (nouveau calcul, groupby date sur `get_recent_study_sessions`).
2. **Séances** — `stats["session_count"]`. Sparkline : nombre de séances par jour.
3. **Score de maîtrise moyen** — moyenne de `get_course_mastery(course, ...).score` sur tous les `data_store.cours` ayant un score non-`None` (même filtre que `_get_fragile_courses` : au moins 1 lecture, session, ou QCM fait). Affiché avec un `.synapse-ring` donut coloré (vert ≥80, bleu ≥60, orange ≥40, rouge <40 — mêmes seuils que `mastery.py`). Pas de sparkline (pas d'historique de score dans le temps aujourd'hui) ; à la place, sous-texte "X cours suivis".
4. **Série en cours** — `local_store.get_streak_days()`, icône flamme, sous-texte "jours consécutifs". Pas de sparkline ; couleur accent orange/ambre si streak ≥3 (cohérent avec le badge déjà présent dans `theme.py`).

Calcul factorisé dans une fonction `_compute_kpis(days: int) -> dict` en tête de `stats.py`, appelée par `render()` de l'onglet Activité (évite de dupliquer le calcul du score moyen à chaque re-render des 3 onglets — les KPI cards ne se recalculent que quand la période change ou qu'une séance est validée).

## 3. Barre de répartition de maîtrise

Nouveau composant `_render_mastery_distribution()`, placé entre les KPI cards et les onglets. Barre horizontale unique, segments empilés proportionnels au nombre de cours dans chacun des 8 niveaux de `mastery.py` (`à préparer`, `à lire`, `en construction`, `à consolider`, `à entraîner`, `fragile`, `critique`, `maîtrisé`), couleurs = `PROGRESSION_COLORS` existant (pas de nouvelle couleur).

- Hauteur 10px, coins arrondis, chaque segment `min-width: 2%` si non-zéro (pour rester visible même avec peu de cours).
- Au survol d'un segment : tooltip "N cours · Niveau".
- Clic sur un segment : `ui.navigate.to("/colleges")` (pas de filtre par niveau côté Collèges aujourd'hui — hors scope d'ajouter ce filtre ici).
- Légende compacte sous la barre : liste horizontale scrollable des niveaux présents avec leur count (`● Fragile (4)`), même style que les labels de `_render_stats_accordion`.
- Calcul : une seule itération de `data_store.cours` (même boucle que `_get_fragile_courses`, réutiliser le même filtre "cours commencé" ; les cours "à préparer"/"à lire" sont comptés séparément puisqu'ils ont `score=None`).

## 4. Onglets — restylage uniquement

### Activité
- Suppression de l'accordéon `_render_stats_accordion` (les 4 stats qu'il contenait sont maintenant dans le hero KPI row — temps, séances, confiance moyenne et pièges notés ne sont pas repris tels quels : confiance moyenne et pièges notés restent uniquement visibles via la timeline, pas de perte d'info car ils apparaissent déjà par événement).
- Timeline (`_render_timeline`, `_render_session_row`, `_render_weak_row`) : inchangée dans sa logique, seules les classes de couleur passent des couleurs Tailwind ad hoc (`bg-blue-100 text-blue-700...`) aux tokens `--s-*` là où un équivalent existe déjà (fond de card, bordures) ; les couleurs sémantiques par type d'activité (`_ACT` dict) restent en classes Tailwind car elles encodent une info (type d'activité), pas un token de thème.

### À retravailler
- Cards fragiles (`_render_fragile_card`) migrées vers le style `.synapse-kpi-card`-like : bordure gauche accent (rouge si critique, orange si fragile — déjà le cas via `LEVEL` dict), `border-radius` et `box-shadow` alignés sur les tokens `--s-r-xl` / `--s-shadow-sm`.
- Bandeau `_render_fragile_banner` : même traitement de bordure/fond que `.synapse-hero` mais coloré rouge/orange selon `is_crit` (garder la logique actuelle, changer uniquement les valeurs de radius/shadow pour matcher les tokens).

### Objectifs
- `_render_semaine_tab` : les tuiles métriques et le bloc "Progression des objectifs" passent des classes `bg-{color}-50 dark:bg-{color}-900/10` etc. vers les tokens `--s-*` où c'est un fond neutre ; les couleurs sémantiques par métrique (indigo=séances, bleu=temps, violet=QCM, vert=lacunes) restent inchangées (même logique que `_ACT`, ce sont des couleurs porteuses de sens, pas des tokens de thème).
- Bloc "Belle semaine !" / badge de progression : radius et shadow alignés `--s-r-2xl` / `--s-shadow-sm`.

## 5. Données — aucune nouvelle fonction backend

Tout se calcule côté `stats.py` à partir de fonctions déjà existantes :
- `local_store.get_weekly_study_stats(days)`
- `local_store.get_recent_study_sessions(limit)` (pour le regroupement par jour des sparklines)
- `local_store.get_streak_days()`
- `data_store.cours` + `mastery.get_course_mastery()` + `local_store.get_sessions_by_course()` / `get_postpone_counts()` (même pattern que `_get_fragile_courses`, à factoriser en une fonction commune `_get_all_mastery_snapshots()` réutilisée par la distribution ET par le score moyen, pour ne parcourir `data_store.cours` qu'une fois par render).

## 6. Vérification

Lancement de l'app en local (`main.py`), contrôle visuel dans le navigateur en light et dark mode sur `/stats`, vérification que les 3 onglets fonctionnent toujours (changement de période, ouverture séance rapide, résolution de piège, navigation semaine) sans régression de comportement. Pas de tests automatisés pour les pages UI dans ce projet (convention existante).

## Hors scope

- Pas de changement à la page QCM au-delà du renommage des classes CSS partagées (aucun changement visuel sur QCM).
- Pas de filtre par niveau de maîtrise sur `/colleges` déclenché par un clic sur la barre de répartition — navigation simple vers la page, sans query param.
- Pas d'historique temporel du score de maîtrise moyen (pas de sparkline sur cette KPI) — nécessiterait de stocker un snapshot quotidien, hors scope de cette refonte visuelle.
- Pas de changement à la logique de calcul de maîtrise (`mastery.py`), aux seuils, ou aux couleurs `PROGRESSION_COLORS`.
- Pas de changement à `local_store.py` (aucune nouvelle fonction, aucune migration).
