# Capture QCM EDNpro

La capture se fait avec un Chromium visible sur l'ordinateur où tu travailles.
Synapse n'automatise aucune réponse : l'agent observe une correction déjà
affichée, puis l'envoie au serveur quand tu cliques sur « Arrêter et importer ».

## Première configuration

1. Générer un jeton long, puis l'ajouter dans le fichier .env du serveur :

       EDNPRO_CAPTURE_TOKEN=une-valeur-secrete-longue

   Après modification, reconstruire/recréer le conteneur Synapse pour que la
   variable soit chargée.

2. Sur le PC Windows, lancer un Chrome visible avec le débogage local. Utiliser
   un profil séparé pour ne pas perturber le Chrome habituel :

       & "$env:ProgramFiles\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222 --user-data-dir="$env:LOCALAPPDATA\Synapse\ednpro-chrome"

3. Dans ce Chrome, ouvrir EDNpro et se connecter normalement.

4. Depuis le dépôt Synapse, lancer l'agent local :

       .\.venv\Scripts\python.exe scripts\ednpro\qcm_capture_agent.py --synapse-url https://synapse.home.arpa --token "une-valeur-secrete-longue" --cdp-url http://127.0.0.1:9222

   Le port de contrôle local est 8876 pour ne pas entrer en conflit avec
   AnkiConnect (8765).

## Utilisation

Dans Synapse, ouvrir QCM, choisir « Capturer une session EDNpro », puis
« Démarrer la capture ». Faire la session manuellement dans Chromium et
afficher la correction après chaque réponse. Quand tu veux terminer, cliquer
« Arrêter et importer ».

La question actuellement non corrigée est ignorée. Les questions corrigées
sont dédoublonnées par leur identifiant EDNpro ; une question déjà présente
n'est pas remplacée, mais sa nouvelle tentative est conservée. Les résultats
par item sont envoyés au moteur QCM/maîtrise quand Synapse retrouve le cours
correspondant.
