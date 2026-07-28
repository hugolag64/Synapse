# Synapse — audit initial de reconnexion et des algorithmes

Date : 27 juillet 2026  
Périmètre : lecture du dépôt et de l’historique ; aucune modification fonctionnelle.

## Décision de phase

Ne pas lancer de refonte métier. Le code à récupérer est substantiel, mais le cockpit est aujourd’hui le chemin principal et ne propose pas la parité du parcours classic. La première livraison doit être une reconnexion sûre, fondée sur des tests de caractérisation et une couche métier unique.

## État de la base

| Fonction | État | Code existant | Interface effective | Action d’audit |
|---|---|---|---|---|
| Révisions J3/J7/J14/J30 et consolidation | OK mais flux dupliqués | `backend/core/reviews/{service,consolidation,local_store}.py` | Dashboard, planning, todo, focus | Caractériser puis centraliser la validation dans un service. |
| Auto-évaluation de fin de séance | Partiel | `frontend/pages/dashboard/_dialogs.py:open_session_feedback_dialog` ; `study_sessions` | Dashboard/planning/todo/focus | Réutiliser ce wizard : il ne faut pas le recréer. Distinguer « révision validée » de « item terminé ». |
| Auto-évaluation via Focus cockpit | Cassé | `focus_mode_cockpit.py` et callbacks dashboard | Fiche item cockpit → Focus | Les champs `qcm_result`, `weak_category`, `weak_detail` sont saisis, puis perdus avant persistance. Corriger après test de caractérisation. |
| Saisie QCM et proposition de lacune | OK en classic, partiel cockpit | `frontend/pages/qcm.py`, `course_quick_actions.py`, `local_store.add_qcm_session_full` | QCM classic ; cockpit analytique | Rebrancher le workflow complet dans le cockpit ; les raccourcis doivent nourrir le même pipeline de lacunes. |
| Lacunes | OK mais pipelines multiples | `weak_points`, `ai_qcm/lacunes.py`, `reviews/lacune_adapter.py` | Classic complet ; cockpit liste seulement | Cartographier les producteurs et normaliser le statut/événement avant évolution d’algorithme. |
| OIC LiSA + IA locale | Présent mais non rebranché et baseline rouge | `lisa/{scraper,evaluator,anythingllm_client}.py`, `oic_eval_dialog.py`, `oic_attempts` | Accessible depuis les cartes classic ; absent de la fiche cockpit | Stabiliser le contrat LiSA, puis ajouter l’entrée fiche item cockpit vers le service existant. |
| Maîtrise | Présent, heuristique | `reviews/mastery.py`, `knowledge/service.py` | Badges et vues cockpit | Documenter les entrées réelles avant tout nouveau score. Ne pas remplacer sans décision Hugo. |
| Obsidian | Présent | `backend/core/obsidian/` | Lien depuis fiche cockpit | Tester les pannes et l’idempotence avec SQLite/Notion. |
| Anki | Partiel | champs/indicateurs utilisés par la maîtrise | Pas de connecteur identifié | Conserver comme besoin à concevoir, non comme reconnexion. |
| Planning manuel / vacances / ECOS / UNESS conforme | Manquant ou exploratoire | aucun socle métier fiable identifié | — | Hors reconnexion ; ne pas implémenter avant le socle événementiel et une décision produit. |

## Cartographie des sources de vérité

| Domaine | Stockage existant | Observation |
|---|---|---|
| Cours/items/préférences | Notion + `data_cache.json` via `backend/state/store.py` | Deux sources opérationnelles ; attention aux données orphelines après renommage/suppression. |
| Révisions et séances | SQLite : `review_history`, `study_sessions` | Les champs nécessaires à l’auto-évaluation existent déjà. |
| QCM | SQLite : `qcm_results`, `qcm_sessions` | Deux formats historiques, à unifier par contrat avant extensions DP/KFP. |
| Lacunes | SQLite : `weak_points`, `pending_gap_proposals` | Alimentées par plusieurs parcours, dont certains sans la détection de répétition. |
| OIC | SQLite : `lisa_oic`, `oic_attempts` | LiSA fournit le référentiel, AnythingLLM aide à l’évaluation ; aucun Ollama direct n’a été trouvé. |
| État déclaré | SQLite : `college_status`, `item_state` | Déjà séparé de la maîtrise calculée ; à préserver dans les futures décisions. |

## Constats prioritaires vérifiés

1. **Régression d’interface majeure :** `ui_mode=cockpit` est le chemin visible par défaut, mais laisse côté classic les actions rapides QCM, LiSA/OIC, suivi et plusieurs assistants. La fiche cockpit (`frontend/pages/course_detail_cockpit.py`) expose Réviser/PDF/Obsidian, pas l’OIC ni la saisie QCM.
2. **Données d’auto-évaluation perdues :** le wizard collecte QCM et erreur EDN ; le callback Focus cockpit ne transmet que activité, durée, confiance et difficulté. Une lacune peut donc ne jamais être créée depuis le parcours principal.
3. **Pas de commande métier unique :** dashboard, focus, todo et planning réimplémentent diverses combinaisons de `mark_done`, `add_study_session`, consolidation et synchronisation externe. C’est le risque principal de divergence entre vues.
4. **OIC existant mais contrat externe instable :** le scraper est maintenant API MediaWiki, alors que quatre tests attendent encore le scraper HTML historique. L’UI ne doit pas être reconnectée avant d’avoir figé le comportement d’erreur/authentification et les fixtures API.
5. **Maîtrise incomplète :** la formule actuelle prend surtout lectures, cases Notion, reports et retour de séance. Les scores QCM détaillés, lacunes actives et résultats OIC ne déterminent pas directement le score global. Les badges de couverture OIC ne constituent pas une intégration de maîtrise.
6. **Concurrence SQLite et synchronisations :** une connexion SQLite globale avec `check_same_thread=False` est utilisée depuis UI et tâches de fond sans verrou applicatif identifié. Les imports EDN Pro et certaines écritures de cache sont aussi dupliqués ou non sérialisés.

## Baseline de non-régression

`python -m pytest -q` : **437 réussites, 4 échecs, 1 avertissement**.

Les échecs sont tous dans `tests/test_lisa_scraper.py` (lignes 48, 59, 70 et 94) : ils décrivent l’ancien contrat HTML/404 et ne correspondent plus au scraper API. Ils bloquent toute affirmation que l’évaluation OIC est réutilisable telle quelle.

## Ordre de travail proposé

1. Figer la matrice « point d’entrée → commande métier → écritures → vues mises à jour » pour les parcours : valider une révision, terminer un item, enregistrer un QCM, créer/résoudre une lacune, évaluer un OIC.
2. Écrire les tests de caractérisation de ces cinq parcours, y compris le passage Focus cockpit et les échecs réseau LiSA/AnythingLLM/Notion/Obsidian.
3. Rendre la baseline LiSA verte en choisissant explicitement le contrat API (sans restaurer implicitement l’ancien HTML).
4. Créer ensuite une commande transactionnelle unique d’enregistrement d’un événement d’apprentissage ; reconnecter chaque vue à cette commande, une par une.
5. Seulement après mesure des données réellement produites, préparer la note de décision sur la maîtrise : score unique ou dimensions séparées (connaissances, raisonnement, durabilité, confiance).

## Décisions à demander avant les changements de produit

- Le cockpit doit-il atteindre la parité puis remplacer le classic, ou le classic doit-il rester un mode permanent ?
- « Terminer un item » signifie-t-il une première étude, une validation de séance, ou un statut pédagogique distinct ?
- Autorisons-nous un événement métier unique (`learning_event` ou équivalent) comme interface commune des vues ?
- Pour les OIC, quelle règle humaine prévaut sur LiSA/IA et comment l’échec doit-il affecter le niveau dans le temps ?
- La maîtrise doit-elle rester un score simple visible, ou afficher plusieurs dimensions indépendantes ?
- Faut-il créer un onglet dédié ECOS et LCA ? Pas de socle métier identifié pour l'un ou l'autre à ce jour (cf. ligne « Planning manuel / vacances / ECOS / UNESS conforme » ci-dessus) — à rediscuter plus tard, hors périmètre de la reconnexion en cours.

## Risques à traiter avant l’extension des algorithmes

- Ajouter un verrou/une stratégie de connexion SQLite par opération, avec test de stress multi-thread.
- Superviser les tâches async démarrées au startup et les tâches UI : journalisation d’exception, annulation et idempotence.
- Unifier les deux chemins d’import EDN Pro sous un verrou et des tests de déduplication.
- Tester les opérations distribuées avec pannes partielles : Notion, Obsidian, SQLite et fichiers doivent pouvoir être rejoués sans divergence.
