# Spécification — capture EDNpro en un clic

## Objectif

Depuis Synapse, un clic sur « Capturer une session EDNpro » doit ouvrir un
Chromium visible sur le PC Windows, utiliser le profil EDNpro déjà connecté et
démarrer la capture. Un clic sur « Arrêter et importer » doit arrêter la
capture et importer les questions corrigées vers Synapse sur Ubuntu.

## Architecture retenue

Le serveur Synapse reste responsable de la persistance et du traitement :

- SQLite et les tables de questions EDNpro ;
- dédoublonnage des questions ;
- tentatives, résultats, rangs A/B et statistiques ;
- calcul de maîtrise ;
- endpoint authentifié d’import.

Un relais local Windows reste nécessaire car le navigateur est affiché sur le
PC de l’utilisateur. Il est lancé automatiquement au démarrage de Windows et
écoute uniquement sur `127.0.0.1`. Il est responsable de :

- lancer ou réutiliser un Chromium dédié avec un profil persistant ;
- ouvrir l’URL EDNpro demandée ;
- observer les corrections déjà affichées ;
- arrêter l’observation et transmettre la session au serveur.

Le relais ne répond jamais aux QCM et ne simule aucun comportement humain.

## Cycle utilisateur

1. Le bouton Synapse vérifie la présence du relais local.
2. Le relais ouvre Chromium EDNpro avec le profil dédié et passe en capture.
3. L’utilisateur répond et consulte les corrections normalement.
4. Le bouton « Arrêter et importer » demande l’arrêt local.
5. Le relais attend le dernier état stable, importe uniquement les questions
   corrigées, puis expose le résultat d’import à Synapse.
6. Synapse affiche le nombre de nouvelles questions, de nouvelles tentatives et
   les éventuelles erreurs.

Une question non corrigée au moment de l’arrêt est ignorée. Une question déjà
présente est conservée ; seule la nouvelle tentative est ajoutée.

## Configuration persistante

La première configuration crée un profil Chromium dédié et enregistre le token
du relais dans un fichier local protégé par les permissions de l’utilisateur.
L’utilisateur se connecte une fois à EDNpro dans ce profil. Les lancements
suivants sont automatiques et ne demandent ni token dans PowerShell, ni CDP
manuel.

Le serveur continue de vérifier le token côté API. Le relais ne l’affiche pas
dans son interface ni dans ses logs.

## États et erreurs

Les états visibles sont : `indisponible`, `prêt`, `capture active`, `arrêt en
cours`, `import terminé` et `erreur`.

Les erreurs doivent distinguer :

- relais non lancé ;
- profil Chromium impossible à ouvrir ;
- connexion EDNpro à faire ;
- session sans correction ;
- token ou serveur Synapse invalide ;
- import partiellement refusé.

Un arrêt sans question corrigée ne crée ni session utile, ni tentative, ni
statistique.

## Tests d’acceptation

- Le clic « Capturer une session EDNpro » lance le relais et ouvre Chromium.
- Le clic « Arrêter et importer » importe une session corrigée sans commande
  terminal.
- Une session interrompue avant correction n’ajoute aucune donnée.
- Une question déjà importée n’est pas écrasée et reçoit seulement une nouvelle
  tentative.
- Le relais absent produit une erreur explicite et actionnable.
- Le token n’apparaît ni dans l’URL, ni dans les logs, ni dans le DOM Synapse.
- Le protocole existant `/start`, `/stop`, `/status` reste compatible pendant la
  transition.
