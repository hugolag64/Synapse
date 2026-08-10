# Plan: capture human-in-the-loop des sessions QCM EDNpro

## Objectif

Permettre à l'utilisateur de faire une session EDNpro manuellement dans un Chromium local, puis d'importer uniquement les questions déjà corrigées dans Synapse. Les questions sont dédoublonnées par identifiant externe, les nouvelles questions enrichissent la base QCM, et chaque nouvelle tentative alimente les statistiques et la maîtrise par item/rang.

## Contraintes de sécurité et de comportement

- Chromium reste visible et piloté par l'utilisateur ; aucun clic de réponse ni automatisation de session.
- L'agent local observe seulement les questions/corrections affichées et communique avec Synapse via une API locale/authentifiée.
- La question en cours au moment de « Arrêter et importer » n'est pas importée si elle n'a pas été corrigée.
- Une session sans correction importée ne crée aucune statistique.
- Une question déjà connue n'est jamais écrasée ; seule la nouvelle tentative est enregistrée.
- Les tentatives sont idempotentes pour éviter les doublons en cas de retransmission.

## Découpage TDD

1. **Contrats et normalisation**
   - Ajouter des dataclasses/types pour une observation EDNpro corrigée et un résumé de session.
   - Tester la normalisation des réponses, explications, rangs, score et identifiants externes.
2. **Stockage SQLite et import idempotent**
   - Ajouter les tables dédiées aux questions EDNpro, sessions et tentatives, avec contraintes d'unicité.
   - Tester le dédoublonnage question, la conservation du contenu existant et l'unicité des tentatives.
   - Tester l'abandon d'une observation non corrigée à l'arrêt.
3. **Statistiques et maîtrise**
   - Agréger les tentatives corrigées par item et rang.
   - Relier les résultats au service d'évaluation existant sans créer de session partielle visible.
   - Tester le calcul correct/incorrect/partiel et les compteurs de rang A/B.
4. **Agent Chromium local**
   - Ajouter un protocole local start/stop/import et un adaptateur Playwright/CDP sans accès aux secrets.
   - Tester le protocole avec des fixtures de pages corrigées ; laisser les sélecteurs isolés dans l'adaptateur.
5. **Interface QCM**
   - Ajouter le bouton « Capturer une session EDNpro », l'état de capture et l'action « Arrêter et importer ».
   - Tester les libellés et le raccordement au pont local, sans lancer Chromium depuis le serveur distant.
6. **Vérification et déploiement**
   - Exécuter les tests ciblés puis la suite complète.
   - Vérifier la migration sur une base SQLite de test et documenter la commande de lancement local.

## Décisions techniques

- Les tables de capture sont séparées de `ai_practice_*` : elles conservent la provenance EDNpro et permettent de ne pas mélanger contenu importé et contenu généré.
- Le serveur Synapse ne tente pas de lancer le navigateur de l'ordinateur de l'utilisateur. Un petit agent Windows local, limité à `127.0.0.1`, sert de pont entre le bouton et Chromium.
- L'import est une opération transactionnelle : session, nouvelles questions et tentatives sont validées ensemble, puis les agrégats de maîtrise sont mis à jour.
