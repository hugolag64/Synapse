# Caractérisation des workflows de reconnexion

Document de suivi — caractérisation initiale complétée et état réévalué le
28 juillet 2026.

| Parcours | Entrée actuelle | Écriture principale | Rafraîchissement | Risque vérifié |
|---|---|---|---|---|
| Valider une révision depuis le dashboard cockpit | `frontend/pages/dashboard/_cockpit_today.py` | Wizard partagé → `complete_review()` → `record_evaluation()` | Rebuild du dashboard puis synchronisation Notion asynchrone | Workflow métier désormais commun ; synchronisation externe non bloquante à surveiller. |
| Valider depuis dashboard classic | `frontend/pages/dashboard/_reviews.py` + `_dialogs.py` | Wizard partagé puis callback de validation | Invalidation/rebuild du dashboard | Parcours historique conservé ; parité métier couverte par la façade d’évaluation. |
| Valider depuis Focus | `frontend/components/focus_mode_cockpit.py` | `open_session_feedback_dialog` → callback → `complete_review()` | Rebuild fourni par l’état | Les champs QCM/lacune sont maintenant transmis et persistés. |
| Valider depuis planning/todo | `frontend/pages/planning.py`, `frontend/pages/todo.py`, `todo_cockpit.py` | `complete_review()` ; consolidation via le même point d’entrée | Reload/rebuild local | Workflow métier commun ; variantes de rafraîchissement selon la vue. |
| Enregistrer une session QCM | `frontend/pages/qcm.py` / `course_quick_actions.py` | `add_qcm_session_full` → `qcm_sessions`, proposition éventuelle de lacune | Refresh de la vue QCM | Les raccourcis de session ne suivent pas toujours le pipeline QCM complet. |
| Créer une lacune | Dialogs dashboard, QCM, fiche item, command palette | `add_weak_point` ou `add_weak_point_full` → `weak_points` | Refresh local | Formats et origines multiples ; détection de répétition à caractériser. |
| Évaluer un OIC | `lisa_dialog.py` → `oic_eval_dialog.py` et onglet OIC cockpit | `oic_attempts`, évaluation, niveau OIC, cache LiSA | Refresh de la fiche concernée | Entrée cockpit reconnectée ; contrat LiSA/AnythingLLM à distinguer d’une intégration Ollama directe. |
| Ouvrir une note Obsidian | `obsidian.service.open_course_note` depuis plusieurs vues | URI/chemin du cours, éventuellement frontmatter | Rechargement selon action | Liaison au niveau `course_id`, alors que plusieurs cours peuvent représenter le même item. |

## Écarts de parité cockpit restant à surveiller

- Le planning cockpit (`frontend/pages/planning_cockpit.py`) reste principalement une
  vue d’affichage/export ; les actions de validation sont portées par le planning
  principal et la vue todo.
- La vue QCM cockpit expose désormais l’enregistrement et Anki, mais les filtres
  avancés et certains parcours historiques restent dans la vue classic.
- La vue Lacunes cockpit permet la lecture, la synchronisation et les actions
  principales, mais la couverture exacte doit encore être comparée à classic.
- Les callbacks utilisent le même workflow métier, mais les synchronisations
  Notion/Obsidian et les stratégies de rafraîchissement restent différentes.

## Cas Obsidian item 75

Le cas réel confirme une différence de modèle, pas seulement un défaut cosmétique : trois `Course` distincts portent le même item 75, alors qu’Obsidian doit n’avoir qu’une note canonique pour cet item. La note existante est title-only dans le dossier Psychiatrie ; elle doit pouvoir être affichée depuis les trois contextes Synapse. Le frontmatter contient actuellement un identifiant correspondant à un alias de cours (Pneumologie). La synchronisation actuelle indexe par item seul et peut écraser les doublons ; `note_exists` peut aussi considérer une URI non vérifiée comme valide.

Le test de caractérisation doit donc imposer une liaison canonique au niveau de l’item, puis vérifier que cette note est visible depuis chaque alias collège. Une correspondance ambiguë entre plusieurs items canoniques ne doit pas être attribuée automatiquement ; plusieurs collèges pour un même item ne constituent pas une ambiguïté.

## Tests de caractérisation déjà couverts ou à compléter

1. **Couvert :** `complete_review()` produit une session et une évaluation
   cohérentes pour les révisions, consolidations et lacunes.
2. **Couvert :** les champs `qcm_result`, `weak_category` et `weak_detail` du
   wizard Focus sont persistés.
3. **Couvert :** l’enregistrement passe par la façade `record_evaluation()`.
4. **Couvert :** Anki déduplique ses preuves et alimente la maîtrise.
5. **Couvert :** l’item 75 utilise une liaison Obsidian canonique malgré ses
   relations de collège.
6. **Partiellement couvert :** les actions rapides refusent l’écriture SQLite
   lorsque Notion échoue et affichent un avertissement explicite lorsque Notion
   réussit mais que SQLite échoue (`tests/test_robustness.py`). `complete_review()`
   persiste maintenant la session avant le statut de révision ; si cette
   première écriture échoue, la tâche reste en attente. L’échec de la
   transition métier déclenche maintenant une compensation de la session pour
   les parcours révision, consolidation et lacune.
7. **À compléter :** comparer les rafraîchissements et les synchronisations
   externes après validation depuis chaque vue.

## Risque prioritaire identifié — atomicité de `complete_review()`

Le workflow commun effectue deux écritures successives. La persistance de la
session via `record_evaluation()` intervient désormais avant la mise à jour de
`review_history`. Cette inversion élimine le cas où l’historique indique une
tâche terminée alors que la session d’évaluation manque.

Les trois parcours compensent désormais une exception levée par leur transition
de statut en supprimant la session qu’ils viennent de créer. Cette garantie
couvre les échecs avant validation de l’écriture métier ; une exception après
une écriture partielle interne nécessitera toujours une transaction SQLite
commune ou une stratégie d’idempotence plus forte.

## Règle de suite

Ne pas modifier `mastery.py` pour traiter un problème de parité UI. Les prochains
tests doivent porter sur les effets observables des synchronisations et des
rafraîchissements ; toute divergence métier nouvelle doit être corrigée dans
`complete_review()` ou dans la façade d’évaluation, pas dans une page isolée.
