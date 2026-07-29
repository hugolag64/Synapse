# Routage économique des modèles IA — Design

## Objectif

Centraliser le choix du modèle IA selon la nature de la tâche médicale :
Gemini 2.5 Flash-Lite pour les tâches courtes et fréquentes, Gemini 2.5 Flash
pour les raisonnements cliniques et les validations complexes, et Synapse seul
pour les calculs déterministes.

## Périmètre

Le routage couvre les familles suivantes :

| Tâche | Modèle par défaut | Règle |
|---|---|---|
| OIC / QCM simple | Flash-Lite | Génération courte, explication factuelle, correction locale quand possible |
| ECOS simple | Flash-Lite | Patient simulé, relances et feedback court |
| DP / KFP | Flash | Génération, correction, embranchements et raisonnement clinique |
| ECOS complexe | Flash | Analyse détaillée, feedback structuré et contrôle de cohérence |
| Extraction complexe d’une grille | Flash | Validation humaine obligatoire avant utilisation |
| Score, niveau, seuils, progression | Aucun modèle | Calculé par le code métier Synapse |

Les fonctionnalités DP/KFP/ECOS qui ne disposent pas encore d’un appel LLM
doivent recevoir la façade de routage sans inventer de nouveau parcours UI dans
ce changement. La façade doit être directement réutilisable quand ces parcours
seront branchés.

## Architecture retenue

Créer une façade `AIService` indépendante du fournisseur, avec un enum de
tâches (`OIC`, `QCM`, `ECOS`, `DP`, `KFP`, `EXTRACTION_GRILLE`) et une politique
de routage pure. Le client Gemini reçoit explicitement le modèle choisi et
retourne le texte ainsi que les métadonnées d’usage disponibles. Le client
AnythingLLM reste disponible comme transport RAG pour les appels OIC existants,
mais le choix de modèle doit être explicite et testable au niveau de la façade.

La première intégration conserve la connaissance documentaire actuelle : le
service OIC continue d’utiliser le workspace AnythingLLM pour récupérer le
contexte. Les tâches directes Gemini utilisent le client Gemini avec un prompt
fourni par le domaine appelant. Aucun score ne doit être déduit par le LLM.

## Configuration

Ajouter dans `.env.example` et `Settings` :

- `GEMINI_API_KEY` ;
- `GEMINI_LITE_MODEL=gemini-2.5-flash-lite` ;
- `GEMINI_FLASH_MODEL=gemini-2.5-flash` ;
- `GEMINI_TIMEOUT_SECONDS=60`.

Les clés ne doivent jamais apparaître dans les logs, exceptions ou tests.
L’absence de clé Gemini doit produire une erreur explicite et permettre le
repli vers AnythingLLM lorsque le parcours le prévoit.

## Contrat de service

`AIService.generate(task, prompt, *, context=None, response_format="text")`
choisit le modèle selon la tâche, appelle le transport configuré et retourne
`AIResponse(text, model, input_tokens, output_tokens)`. Les tâches de score ne
passent pas par ce service.

Le parsing JSON, la validation de schéma et les bornes numériques restent dans
les services métier (`evaluator`, QCM, DP/KFP). Une réponse IA invalide doit
être signalée comme erreur de contrat, jamais transformée silencieusement en
score nul.

## Sécurité et coût

Le routage Lite/Flash est une optimisation de coût et de latence, pas une
garantie de validité médicale. Les corrections DP/KFP et les extractions
complexes restent soumises à validation humaine ou à des règles métier.
Les métadonnées de modèle et de tokens sont journalisées sans contenu médical
ni secret afin de permettre le suivi de consommation.

## Tests d’acceptation

1. Chaque famille de tâche sélectionne le modèle attendu.
2. Une tâche inconnue est refusée explicitement.
3. Une clé absente produit une erreur non sensible.
4. Les appels transmettent le modèle choisi et le format de réponse demandé.
5. Le parsing OIC existant reste compatible.
6. Les calculs de score existants ne déclenchent aucun appel IA.
7. Les tests ne font aucun appel réseau réel.

