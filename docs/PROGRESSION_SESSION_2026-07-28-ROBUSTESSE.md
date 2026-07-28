# Etat robustesse — 28 juillet 2026

## Mise à jour de clôture

- Le cockpit Planning et son lancement local ont été stabilisés après
  intégration des actions par journée et des consolidations futures.
- Le reloader NiceGUI est désactivé dans `launch_synapse.bat` afin de conserver
  le même interpréteur `.venv` entre le processus parent et le serveur.
- Vérification finale de la session : **582 tests passés, 1 avertissement**.

## Termine

- Les ecritures SQLite concurrentes sont serialisees par verrou reentrant.
- Une exception Notion apres mise a jour optimiste declenche un rollback.
- Un double declenchement d'une action rapide est coalesce.
- Une panne SQLite apres succes Notion est signalee a l'utilisateur.
- Une erreur de writeback Obsidian apres upsert SQLite remonte comme avertissement
  de synchronisation.
- Les migrations SQLite existantes restent compatibles.

## Verification

- Tests de robustesse et synchronisation : 5 passes.
- Suite complete : **500 tests passes**, 2 avertissements preexistants.

## Reste

Le socle de robustesse est couvert. Ne pas modifier `mastery.py` avant une
decision produit explicite sur son evolution.

## Integration Anki native

- Le paquet `Fiches EDN Notion` est lu via AnkiConnect.
- Le mapping deck -> item gere les sous-paquets mono-item et multi-items.
- Les preuves de revision Anki sont stockees de facon idempotente dans SQLite.
- Le bridge `synapseAnswerCard` utilise le scheduler natif Anki.
- Le mode de revision Synapse propose Again, Hard, Good et Easy.
- Les revisions Anki alimentent la maitrise des connaissances, sans remplacer les QCM/DP/KFP.
- Un paquet present ou une connexion indisponible ne penalise pas le score.
- Anki doit etre redemarre pour charger l'action ajoutee a AnkiConnect.

## Cloture de session — 28 juillet 2026

- Les cockpits Points faibles, Colleges et Planning ont ete refondus en vues
  larges et responsives, avec pilotage, priorites et etats actionnables.
- Le Planning propose des vues 1/3/7 jours et des objectifs de charge par date
  en minutes ou en nombre d'items ; les urgences restent prioritaires.
- Le cockpit Aujourd'hui reprend l'objectif de charge du jour.
- Verification finale : **557 tests passes**, compilation Python validee.
