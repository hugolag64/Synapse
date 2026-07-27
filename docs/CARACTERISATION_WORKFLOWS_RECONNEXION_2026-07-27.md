# Caractérisation des workflows de reconnexion

Document de travail — audit uniquement, avant implémentation.

| Parcours | Entrée actuelle | Écriture principale | Rafraîchissement | Risque vérifié |
|---|---|---|---|---|
| Valider une révision depuis le dashboard cockpit | `frontend/pages/dashboard/_cockpit_today.py` | `local_store.mark_done` puis `add_study_session` | Reload/reconstruction du dashboard | Séquence locale distincte du classic ; à couvrir par un test de workflow. |
| Valider depuis dashboard classic | `frontend/pages/dashboard/_reviews.py` + `_dialogs.py` | Wizard partagé puis callback de validation ; SQLite/Notion selon tâche | `review_service.invalidate_cache` + rebuild | Plusieurs callbacks selon type de tâche. |
| Valider depuis Focus | `frontend/components/focus_mode_cockpit.py` | `open_session_feedback_dialog` puis callback Focus | Rebuild fourni par l’état | Les champs QCM/lacune avancés du wizard ne sont pas transmis au callback. |
| Valider depuis planning/todo | `frontend/pages/planning.py`, `frontend/pages/todo.py`, `todo_cockpit.py` | `mark_done`, parfois `add_study_session` ou consolidation | Reload/rebuild local | Logique dupliquée et risque de divergence. |
| Enregistrer une session QCM | `frontend/pages/qcm.py` / `course_quick_actions.py` | `add_qcm_session_full` → `qcm_sessions`, proposition éventuelle de lacune | Refresh de la vue QCM | Les raccourcis de session ne suivent pas toujours le pipeline QCM complet. |
| Créer une lacune | Dialogs dashboard, QCM, fiche item, command palette | `add_weak_point` ou `add_weak_point_full` → `weak_points` | Refresh local | Formats et origines multiples ; détection de répétition à caractériser. |
| Évaluer un OIC | `lisa_dialog.py` → `oic_eval_dialog.py` | `oic_attempts`, niveau OIC, cache LiSA | Refresh de la fiche classic | Entrée absente de la fiche cockpit ; contrat LiSA/API actuellement en échec dans 4 tests. |
| Ouvrir une note Obsidian | `obsidian.service.open_course_note` depuis plusieurs vues | URI/chemin du cours, éventuellement frontmatter | Rechargement selon action | Liaison au niveau `course_id`, alors que plusieurs cours peuvent représenter le même item. |

## Écarts de parité cockpit constatés

- Le planning cockpit (`frontend/pages/planning_cockpit.py`) est actuellement une vue d’affichage/export : aucun callback de validation n’y a été retrouvé.
- La vue QCM cockpit est un roll-up analytique ; le wizard détaillé, les filtres avancés et le pipeline de saisie restent classic.
- La vue Lacunes cockpit permet la synchronisation/lecture, mais pas l’ensemble des actions de résolution et de création présentes dans classic.
- Les callbacks de validation du dashboard, du Focus et de todo ont les mêmes intentions mais des variantes de contexte Notion, consolidation et rafraîchissement.

## Cas Obsidian item 75

Le cas réel confirme une différence de modèle, pas seulement un défaut cosmétique : trois `Course` distincts portent le même item 75, alors qu’Obsidian doit n’avoir qu’une note canonique pour cet item. La note existante est title-only dans le dossier Psychiatrie ; elle doit pouvoir être affichée depuis les trois contextes Synapse. Le frontmatter contient actuellement un identifiant correspondant à un alias de cours (Pneumologie). La synchronisation actuelle indexe par item seul et peut écraser les doublons ; `note_exists` peut aussi considérer une URI non vérifiée comme valide.

Le test de caractérisation doit donc imposer une liaison canonique au niveau de l’item, puis vérifier que cette note est visible depuis chaque alias collège. Une correspondance ambiguë entre plusieurs items canoniques ne doit pas être attribuée automatiquement ; plusieurs collèges pour un même item ne constituent pas une ambiguïté.

## Tests de caractérisation à écrire en premier

1. Une validation depuis dashboard, focus, planning et todo produit les mêmes champs dans `study_sessions` et le même état `review_history`.
2. Les champs `qcm_result`, `weak_category` et `weak_detail` saisis dans le wizard Focus sont persistés.
3. Un QCM avec erreurs répétées produit une proposition de lacune exactement une fois et reste rejouable.
4. Une évaluation OIC réussie et échouée respecte le contrat choisi pour `oic_attempts` et le niveau.
5. L’item 75 retrouve la note Obsidian existante malgré ses trois relations de collège, sans créer de doublon.
6. Une panne partielle Notion/Obsidian/SQLite ne laisse pas une vue indiquant un succès alors que l’écriture métier a échoué.

## Règle de suite

Ne pas ajouter de nouvelle UI ni modifier `mastery.py` avant que ces tests décrivent les comportements actuels et que les divergences entre points d’entrée soient explicitement acceptées ou corrigées.
