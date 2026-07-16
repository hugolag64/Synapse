# Suppression d'un cours depuis une vue collège — Design

**Date :** 2026-07-16
**Statut :** validé en brainstorming, prêt pour le plan d'implémentation

## Problème

Après la réconciliation collège/item de ce matin, certains collèges contiennent des cours en trop (associations erronées, doublons créés par le pipeline de réconciliation). L'utilisateur veut pouvoir les supprimer à la main, directement depuis la vue `/colleges`, sans passer par Notion.

Le modèle de données actuel (voir mémoire `project-college-item-authority`) fait qu'**une page Cours = un couple (item, collège)**. Un `Cours` n'a donc jamais qu'un seul collège dans `course.college`. Supprimer « ce cours de cette vue collège » revient donc simplement à supprimer la page Notion correspondante — aucune logique de découpage par collège n'est nécessaire.

## Périmètre

Dans le périmètre : une action de suppression sur la `CourseCard`, qui supprime la page Notion **et** l'entrée correspondante dans le cache local (`data_store`) en un seul geste.

Hors périmètre : suppression en masse / multi-sélection, undo, et toute suppression qui viserait un item dans **tous** ses collèges à la fois (l'utilisateur a confirmé vouloir uniquement le couple (item, collège) affiché).

## Décisions de conception

**Emplacement :** nouvel item de menu « Supprimer » dans le menu ⋯ existant de `CourseCard` (`frontend/components/course_card.py`), en rouge, dans une nouvelle section séparée en bas du menu — même style que le « Supprimer » déjà présent sur les cartes de lacune (`frontend/components/weak_point_card.py:284`).

**Friction :** aucune boîte de dialogue de confirmation — suppression immédiate + toast, comme pour les lacunes. L'utilisateur va en supprimer plusieurs d'affilée pendant son nettoyage ; on ne rajoute pas de friction pour une action Notion "archive" (récupérable côté Notion, pas une perte définitive).

**Séquence d'exécution** (nouvelle fonction async `_delete_course_action(course, refresh_fn, client)` dans `frontend/components/course_quick_actions.py`, suivant le pattern déjà utilisé par `_create_obsidian_note_action`) :
1. `await notion_client.archive_page(course.id)` — si ça échoue, on s'arrête là : toast d'erreur (`type="negative"`), rien n'est retiré du cache local (pas d'état incohérent entre Notion et le cache).
2. `await data_store.remove_cours(course.id)` — nouvelle méthode sur `DataStore` (`backend/state/store.py`), symétrique de `refresh()`/`merge_cours_delta()` : retire l'entrée sous le `_cours_lock` existant, puis `save_to_disk()`.
3. `ui.notify(..., type="warning", icon="delete")` + `refresh_fn()` pour retirer la carte de la vue immédiatement, sans attendre le prochain cycle de sync (60 min).

**Non traité par ce changement** (accepté, pas bloquant) : les caches dérivés (`semantic_graph`, `search_index`, snapshots analytics) peuvent référencer brièvement un id de cours supprimé jusqu'au prochain refresh complet ; ils ne sont pas invalidés en ligne. Comportement identique à l'existant pour toute autre mutation de `self.cours`.

## Vérification

- Nouveau test unitaire pour `DataStore.remove_cours()` (retire bien l'entrée, no-op si id absent).
- Test manuel : dans `/colleges`, supprimer un cours depuis un collège en excès (ex. mentionné par l'utilisateur), vérifier qu'il disparaît immédiatement de la vue, qu'il n'est plus renvoyé par `scripts/diff_college_mapping.py` côté Notion (page archivée), et qu'il ne réapparaît pas après un rechargement de page (cache local à jour).
