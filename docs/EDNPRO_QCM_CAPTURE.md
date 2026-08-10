# Capture QCM EDNpro

La capture se fait avec un Chromium visible sur l'ordinateur où tu travailles.
Synapse n'automatise aucune réponse : l'agent observe une correction déjà
affichée, puis l'envoie au serveur quand tu cliques sur « Arrêter et importer ».

## Installation unique sur Windows

Depuis le dépôt Synapse, dans PowerShell :

~~~powershell
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\ednpro\install_capture_agent.ps1
~~~

Le script :

1. demande le token EDNPRO_CAPTURE_TOKEN sans l'afficher uniquement lors de la
   première installation ;
2. crée un profil Chromium dédié ;
3. installe l'agent dans les tâches Windows au démarrage de ta session ;
4. lance l'agent immédiatement.

La première fois, Chromium s'ouvre avec ce profil dédié : connecte-toi
normalement à EDNpro. La session de connexion sera conservée dans ce profil.
Le fichier de configuration est local et protégé pour ton compte Windows.
Pour remplacer le token, relance le script avec `-ReplaceToken`.

## Utilisation normale

1. Dans Synapse, ouvre QCM.
2. Choisis « Capturer une session EDNpro ».
3. Chromium s'ouvre automatiquement sur EDNpro et la capture démarre.
4. Fais ta session et affiche la correction après chaque réponse.
5. Clique sur « Arrêter et importer » dans Synapse.

Les questions corrigées sont importées, dédoublonnées par leur identifiant
EDNpro et reliées aux tentatives, résultats, rangs et statistiques. Une question
déjà présente n'est jamais écrasée ; une nouvelle tentative est conservée.

La question actuellement non corrigée au moment de l'arrêt est ignorée. Si
aucune correction n'est affichée, aucune session utile ni statistique n'est
créée.

## Dépannage

L'agent écoute uniquement sur http://127.0.0.1:8876. Dans PowerShell, le
diagnostic non sensible est :

~~~powershell
Invoke-WebRequest http://127.0.0.1:8876/status -UseBasicParsing |
  Select-Object -ExpandProperty Content
~~~

Si Synapse indique que le relais est indisponible, relance une fois le script
d'installation. Le mode CDP manuel reste disponible pour le diagnostic avancé,
mais il n'est plus nécessaire au fonctionnement normal.
