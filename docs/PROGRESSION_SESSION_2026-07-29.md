# Progression Synapse — 29 juillet 2026

## Fonctionnalités livrées

- Routage Gemini : Flash-Lite pour QCM/OIC/QROC simples ; Flash Preview pour DP/KFP et cas complexes.
- Historique immuable des questions IA, réponses, corrections, explications et tentatives.
- Rejeu exact d'une session et alimentation du score de maîtrise pour les réponses fermées.
- Réglage visuel des sessions : sliders pour le nombre total et la répartition ouvert/fermé.
- QCM multi-réponses avec cases à cocher.
- Barème EDN documenté comme cible : QRU, QRM, QRP, QRP longues et QROC ; QZP exclues ; TCS séparé.
- Import local de banques JSON QCM/DP/KFP.
- Import de discussions ChatGPT en `.txt`, `.md`, `.html` ou JSON exporté.
- Extraction locale des blocs question/réponse/explication, conservation de la discussion source et déduplication.
- Détection des ITEM mentionnés, confirmation manuelle des associations et conservation de plusieurs ITEM par cas.
- Tirage local aléatoire par ITEM, lancement d'un cas importé et ajout aux ancrages.

## Modèles et coût de référence

- `gemini-3.1-flash-lite` : QCM, OIC, QROC simples.
- `gemini-3-flash-preview` : DP, KFP, corrections ou raisonnements complexes.
- Les scores sont calculés par le code Synapse, pas par Gemini.
- Les documents passent par RAG : seuls les extraits récupérés sont envoyés au modèle.
- Les questions locales et les rejouées ne coûtent aucun appel API.
- Estimation de travail : environ 2–3 $/mois en usage normal et 8–12 $/mois en usage intensif, selon le volume de DP/KFP et la taille du contexte RAG.

## Import ChatGPT — mode opératoire

1. Dans ChatGPT, demander une discussion structurée avec les marqueurs `Question`, `Réponse` et `Explication`, et mentionner explicitement les ITEM.
2. Copier/exporter la discussion en `.txt`, `.md`, `.html` ou JSON.
3. Depuis la vue QCM ou le Cockpit ITEM, cliquer sur `Importer QCM / DP / KFP`.
4. Vérifier les ITEM proposés ; décocher ou compléter les ITEM si nécessaire.
5. Importer. Les cas sont conservés dans la banque locale.
6. Depuis le Cockpit ITEM, utiliser `S'entraîner`, `Tirer au hasard` ou `Ancrer`.

Une discussion contenant plusieurs ITEM est placée en vérification tant que les
associations n'ont pas été confirmées. Une correction importée reste une proposition
pédagogique et doit être relue avant de devenir une référence médicale.

## Tests automatisés

- `pytest tests/test_practice_importer.py tests/test_practice_importer_ui.py -q` : couvre le JSON, le texte, HTML, JSON ChatGPT, QCM, DP, KFP, multi-ITEM, déduplication, source, tirage et ancrage.
- `pytest -q` : suite complète du projet.
- Les tests utilisent une base SQLite temporaire et aucun appel Gemini ou réseau.
