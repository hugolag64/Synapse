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

## Premier lancement

Depuis la racine du projet :

```powershell
python scripts/ednpro/collector.py --start-year 2023
```

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
