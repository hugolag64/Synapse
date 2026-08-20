# Roadmap — Planning & charge de travail

> Document vivant, fil dédié à la programmation des items (lecture JX + consolidation) et au
> pilotage de la charge de travail. Né de la session du 20 août 2026 sur la logique de
> programmation des items de collèges validés. Distinct de `docs/ROADMAP_BACKEND_ALGOS.md`
> (fil algorithmes IA/EDN, sujets différents).

**Dernière mise à jour** : 2026-08-20 — chantier clos, cf. §4bis.

---

## 1. Fait dans cette session (20 août 2026)

| Sujet | Ce qui a changé | Où |
|---|---|---|
| **Bruit sur les bootstraps de reprise** | `deploy/reprise_historique_consolidation.py` étalait toutes les dates dues d'un lot sur le même jour (`anchor = START_DATE - interval`, identique pour tous). `anchor_jitter_days()` étale désormais sur ~2 semaines. Script exécuté en `--apply` le 20/08 : 175 items concernés, 29 nouvelles chaînes, réparties du 20/08 au 07/09. | `deploy/reprise_historique_consolidation.py` |
| **Plafond de maîtrise sur l'intervalle** | L'intervalle SM-2 de la boucle de consolidation ne dépendait que de l'autoéval (1-5). Un item objectivement faible pouvait partir sur un intervalle long si la confiance déclarée était haute. `mark_consolidation_done()` plafonne désormais l'intervalle selon `mastery_level` (critique 10j → à entraîner 45j, maîtrisé illimité). | `backend/core/reviews/local_store.py`, branché depuis les deux points d'entrée (`consolidation.complete_consolidation_task`, `validation.complete_review`) |
| **Charge allégée le week-end** | Nouveau réglage on/off (Paramètres → Planification EDN) : samedi/dimanche, le plafond de consolidation du Dashboard "Aujourd'hui" descend de 6→2 items/jour et 2→1 par collège. Lectures J1-J30 non concernées. Défaut désactivé. | `backend/core/reviews/consolidation.py` (`daily_caps`), `backend/core/planning/service.py` (`plan_consolidation`), `frontend/pages/settings_cockpit.py` |

Specs correspondantes : `docs/superpowers/specs/2026-08-20-consolidation-mastery-cap-design.md`,
`docs/superpowers/specs/2026-08-20-weekend-light-consolidation-design.md`.

---

## 2. Constat structurel — deux mécanismes de charge non synchronisés (résolu, cf. §4bis)

Découverte au fil de cette session : Synapse avait **deux systèmes de plafonnement de charge indépendants**, qui ne se parlaient pas.

| | Dashboard "Aujourd'hui" | Page Planning (vue semaine) |
|---|---|---|
| Fonction | `PlanningService.plan_consolidation()` → `consolidation.select_daily()` | `consolidation.get_due_consolidation_tasks()` (brut) fusionné dans `plan_day()` |
| Mécanisme | Plafond explicite : N items/jour, M par collège (diversité) | Budget minutes total (`target_for_day` → `planning_capacity_minutes`), sans notion de diversité par collège |
| Réglages exposés | `daily_budget_min` (préférence lue dans `_cockpit_today.py`, **mais aucune UI dans Paramètres ne la fixe** — trouvé lors de l'audit du 20/08, à vérifier si c'est un oubli) | Slider "Capacité quotidienne" (3-12h) + "Mode vacances" (`planning_cockpit.py`), fonctionnel |
| Le réglage "charge allégée WE" du §1 s'applique-t-il ? | Oui | **Non** — hors périmètre de ce chantier, confirmé avec l'utilisateur |

Conséquence concrète (à l'époque) : régler la capacité dans Planning ne changeait rien au Dashboard, et inversement. Le toggle week-end n'agissait que sur le Dashboard. **Résolu par le chantier du §4bis** — Planning applique désormais le même plafond diversité-par-collège que le Dashboard, dans un modèle waterfall commun.

## 3. Vision exprimée par l'utilisateur pour Planning (20 août 2026)

> "Planning doit me permettre de voir les futurs items à bosser (les lectures JX et à consolider) + piloter facilement la charge de travail. Actuellement c'est pas ouf."

Deux besoins distincts à l'intérieur de cette phrase :

1. **Visibilité** : une vue claire des items à venir, lecture ET consolidation confondues, sur l'horizon proche (pas seulement la grille 7 jours actuelle).
2. **Pilotage de charge simple** : aujourd'hui il faut connaître l'existence de deux réglages séparés (capacité Planning en heures, budget Dashboard en minutes, et maintenant le toggle week-end limité au Dashboard) pour comprendre ce qui va réellement s'afficher un jour donné. Pas un pilotage "facile" au sens où l'utilisateur l'entend.

**Réalisé — cf. §4bis.** L'horizon reste la grille 7 jours (navigation semaine par semaine, confirmé avec l'utilisateur plutôt qu'un horizon étendu) ; la fiabilité de ce qui s'y affiche et le pilotage de charge ont été traités.

## 4. Chantiers ouverts, non priorisés (historique — tous traités, cf. §4bis)

- ~~**Unifier `select_daily` et `get_due_consolidation_tasks` brut**~~ — fait.
- ~~**Unifier `daily_budget_min` (minutes, Dashboard) et `planning_capacity_minutes` (minutes, Planning)**~~ — fait.
- ~~**Étendre "charge allégée le week-end" à Planning**~~ — fait.
- ~~**Vérifier l'UI de `daily_budget_min`**~~ — confirmé mort (aucune UI ne l'écrivait), supprimé.
- ~~**Redesign Planning** pour la vision du §3~~ — fait.

## 4bis. Redesign Planning — implémenté (20 août 2026, suite de session)

Chantier unique regroupant l'unification (§2) et le redesign visuel (§3), brainstormé et implémenté dans la foulée. Décisions clés :

- **Waterfall temporel** : la voie Lecture (cycle J1-J30 + prépa fac, cf. ci-dessous) consomme la capacité du jour en premier (retards jamais coupés) ; la Consolidation reçoit ce qu'il reste, triée par urgence, avec le même plafond diversité-par-collège que le Dashboard (`consolidation.select_daily`/`daily_caps`, appelé avec la date du jour affiché — donc la charge allégée week-end s'applique désormais aussi à Planning sur les semaines futures). Le plafond dur de 5 tâches est retiré ; tout item écarté est compté dans un badge `+N en attente` au lieu de disparaître silencieusement.
- **Prépa fac visible dans Planning** : le module `backend/core/prep/` (détection des cours à J+1/J+2 dans le calendrier fac, déjà en prod mais invisible hors Dashboard) alimente désormais un bloc agrégé par cours dans la grille — c'était la vraie cause du "je ne vois pas ce qui arrive" sur les semaines futures, plus que le manque de plafond partagé.
- **Charge unifiée** : capacité globale accessible depuis Paramètres *et* Planning (même préférence `planning_capacity_minutes`) + override par jour (clic sur l'en-tête d'une case, écrit `planning_targets`). `daily_budget_min` supprimé : la projection Sprint EDN lit désormais la vraie capacité (avant, figée à un facteur 1.0 avec un défaut de 60 min jamais réglable) ; le tronquage de la liste Dashboard reste désactivé par choix explicite (l'activer aurait reproduit le même bug de disparition silencieuse, sans le badge que Planning a maintenant).
- **Perf** : un seul appel Calendar par semaine (`get_events_for_range`) au lieu de sept séquentiels — probable cause de la lenteur perçue.

Spec : `docs/superpowers/specs/2026-08-20-planning-redesign-design.md`. Plan et implémentation (9 tâches, TDD) : `docs/superpowers/plans/2026-08-20-planning-redesign.md`. 23 nouveaux tests, aucune régression (1802 tests passent, un seul échec pré-existant sans rapport côté jobs de rang UNESS). Vérifié en local : groupes Lecture/Consolidation et badge de surplus rendus correctement, consolidation visible sur les semaines futures, un seul appel Calendar confirmé dans les logs.

Hors périmètre, non traité : migration du composant `course_prep_task_row.py` vers les tokens Linear (classes Tailwind `amber-*` brutes, mentionné dans le spec comme non bloquant).

## 5. Prochaine étape

Aucune connue. Le chantier "Planning & charge de travail" tel que scopé dans ce document est clos. S'il faut le rouvrir, point de départ possible : migrer `course_prep_task_row.py` vers les tokens Linear (cf. §4bis, hors périmètre).
