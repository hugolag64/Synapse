# Import EDNpro dans Synapse

## Principe

EDNpro est traité comme une source externe fiable, mais non officielle. Les
corrections sont donc étiquetées `EDNpro` et `official: false` dans le JSON et
dans la base Synapse.

Le collecteur :

1. ouvre un profil Chromium persistant visible ;
2. attend la connexion Google faite manuellement par l'utilisateur ;
3. récupère les sessions EDN disponibles à partir de 2023 ;
4. génère la correction JSON avec le routage IA existant ;
5. écrit puis relit un JSON canonique dans `data/uness/verified/` ;
6. importe la session dans les annales et le QCM Synapse.

Les vidéos ne sont pas téléchargées. Synapse conserve uniquement leur URL de
page, leur titre et leurs éventuels numéros d'item. Cela évite de stocker des
médias ou des URLs CDN temporaires et permet de les afficher dans la vue item.

### Structure EDNpro utilisée

EDNpro ne suit pas le même parcours que le catalogue UNESS : les cartes visibles
sur `/annales` ouvrent une session React sous la forme
`/annales/{identifiant}?mode=consultation`. Le collecteur écoute les réponses
JSON authentifiées de cette session et assemble les tables `annales_sessions`,
`annales_dossiers`, `annales_questions`, `annales_propositions` et
`annales_question_oic`. Une session sans question est refusée avant toute
création d'annale locale ; cela évite les lignes `0/0 sous-parties`.

Les dossiers sont ensuite conservés dans le JSON canonique avec leur type,
numéro et contexte patient. À l'import, chaque dossier devient une sous-partie
de la même annale Synapse ; les questions sans dossier restent dans une
sous-partie complémentaire. Les explications déjà présentes dans EDNpro sont
archivées intégralement, puis condensées dans la correction affichée. Si les
explications par proposition sont complètes, aucune nouvelle correction IA
n'est demandée ; l'IA Lite ne sert que de repli.

Les vidéos liées aux items sont indexées depuis les lignes `learning_videos`
(`item_edn`, titre, URL), avec un repli HTML pour les anciennes versions du
site. Les liens sont ensuite visibles dans le panneau **Ressources** de la fiche
item après l'import.

## Premier lancement

Depuis la racine du projet :

```powershell
python scripts/ednpro/collector.py --start-year 2023
```

### Si Google refuse le navigateur automatisé

Google peut refuser la connexion dans le Chromium lancé par Playwright avec
`accounts.google.com/.../signin/rejected` et le message indiquant que le
navigateur est contrôlé par un logiciel de test. Ce refus vient de Google, pas
des identifiants EDNpro. Il ne faut pas tenter de le contourner avec un mode
furtif.

Utiliser alors un Chrome normal lancé avec un port de débogage local, se
connecter à EDNpro dans ce Chrome, puis lancer la collecte en s'y attachant :

```powershell
& "C:\Program Files\Google\Chrome\Application\chrome.exe" `
  --remote-debugging-port=9222 `
  --user-data-dir="C:\Users\<utilisateur>\AppData\Local\Synapse\ednpro-chrome" `
  "https://ednpro.app/auth"

python scripts/ednpro/collector.py --start-year 2023 `
  --cdp-url http://127.0.0.1:9222
```

La connexion Google doit être faite dans le Chrome normal avant la collecte.
Le mode CDP n'exporte ni cookie, ni token, ni identifiant ; il observe les
pages et les réponses nécessaires à la collecte dans le navigateur déjà ouvert.

Une fenêtre Chromium s'ouvre. Faire la connexion Google dans cette fenêtre,
puis laisser le collecteur poursuivre. Les fichiers de suivi sont dans
`data/ednpro/artifacts/` ; le `manifest.json` indique les sessions importées
ou celles à reprendre.

Pour capturer sans appeler l'IA :

```powershell
python scripts/ednpro/collector.py --start-year 2023 --no-ai
```

La correction texte utilise la tâche `UNESS_CORRECTION` déjà routée vers le
modèle Lite. Les éventuelles questions visuelles ne doivent être envoyées à un
modèle plus coûteux que si des images sont réellement collectées.

## Depuis l'application

La page **Prépa** fournit les raccourcis EDNpro et Hypocampus, ainsi que le
bouton **Importer les EDN**. Le bouton lance le même flux en arrière-plan.
