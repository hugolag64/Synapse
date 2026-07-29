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
GEMINI_FLASH_MODEL=gemini-2.5-flash
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
