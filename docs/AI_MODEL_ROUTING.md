# Routage des modèles IA

Synapse utilise deux niveaux Gemini selon la complexité de la tâche :

| Parcours | Modèle |
|---|---|
| OIC, QCM, ECOS simple | `gemini-3.1-flash-lite` |
| DP, KFP, ECOS complexe | `gemini-2.5-flash` |
| Extraction complexe de grille | `gemini-2.5-flash`, validation humaine obligatoire |
| Score, seuil, niveau, progression | Code Synapse |

## Configuration

Ajouter ces variables dans `.env` :

```dotenv
GEMINI_API_KEY=...
GEMINI_LITE_MODEL=gemini-3.1-flash-lite
GEMINI_FLASH_MODEL=gemini-3-flash-preview
GEMINI_TIMEOUT_SECONDS=60
```

Les appels directs utilisent `backend.core.ai.tasks`. Les services métier
doivent fournir des prompts structurés et demander une réponse JSON lorsqu’un
parsing est prévu :

```python
from backend.core.ai.tasks import generate_dp, generate_qcm

qcm = generate_qcm(prompt)
dp = generate_dp(prompt)
```

Le score ne doit pas être demandé au modèle. Le code métier valide les réponses,
applique les bornes et calcule la progression.

## Sessions rejouables

Les sessions IA de l'ITEM sont persistées localement dans SQLite. Une question
générée devient immuable ; les nouvelles tentatives réutilisent exactement le même
énoncé, les mêmes choix, la même correction et la même explication. Chaque réponse
est conservée séparément afin de comparer l'évolution et de créer des ancrages.

OIC, QCM, DP et KFP acceptent un nombre total de questions ainsi qu'une répartition
entre questions ouvertes et fermées. Les questions et réponses restent consultables
depuis le Cockpit de l'ITEM.

Lorsqu'une tentative fermée est notée, son score agrégé est transmis une seule fois
au service d'évaluation commun. Il alimente alors la maîtrise de l'ITEM comme une
évaluation QCM/DP/KFP classique. Les réponses ouvertes restent historisées mais
ne sont intégrées à la maîtrise qu'après validation.

## Banques QCM / DP / KFP importées

La vue QCM et le Cockpit ITEM proposent aussi l'import d'une banque JSON de QCM/DP/KFP
préparée en amont. L'import est local, dédupliqué et sans appel API. Les cas sont
rattachés aux ITEM déclarés dans le fichier ; les associations introuvables sont
placées dans une file de vérification.

Une discussion ChatGPT peut également être importée en texte, Markdown, HTML ou
JSON. Synapse extrait les questions/réponses/explications, propose les ITEM repérés
avec confirmation, conserve la discussion source et rend les questions disponibles
dans la banque locale, en tirage aléatoire ou via un ancrage volontaire.

## OIC et AnythingLLM

Le dialogue OIC conserve le workspace AnythingLLM afin de garder la recherche
dans les documents du collège. La sélection du modèle de ce workspace doit être
réglée sur Flash-Lite pour les OIC. En cas d’AnythingLLM indisponible, l’erreur
reste typée et affichable par le dialogue.

## Validation humaine

Les corrections DP/KFP complexes et les extractions de grille ne sont pas des
preuves médicales autonomes. Une validation humaine est requise avant de
publier une grille extraite ou d’utiliser une correction complexe comme source
de vérité.
