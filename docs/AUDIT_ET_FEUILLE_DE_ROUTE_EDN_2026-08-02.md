# Synapse — Audit du Codebase & Feuille de Route d'Excellence EDN

**Date** : 2 août 2026  
**Objectif** : Analyse complète du logiciel Synapse et définition des améliorations et nouvelles fonctionnalités nécessaires pour maximiser la préparation à l'EDN (Examen Dématérialisé National).

---

## 1. Vue d'Ensemble et Objectifs

Synapse est l'orchestrateur central de révisions médicales. Il combine la répétition espacée, le suivi de maîtrise, la prise de notes sous Obsidian, la base de cours Notion et l'entraînement QCM/Annales UNESS.

Pour garantir le **meilleur classement possible aux EDN**, le système doit répondre à 3 exigences fondamentales :
1. **Sécuriser à 100% le Rang A (Connaissances Indispensables)** pour éliminer tout risque de perte de points basiques.
2. **Exceller sur le Rang B (Spécialités)** pour se démarquer sur le classement national.
3. **Maîtriser les 3 épreuves clés de l'EDN** :
   - **Épreuve 1** : Questions Isolées (QI / QCM / QROC).
   - **Épreuve 2** : Dossiers Progressifs (DP) & Key Feature Problems (KFP).
   - **Épreuve 3** : Examens Cliniques Objectifs Structurés (ECOS - 30% du score final).

---

## 2. Audit Technique & Architecture du Codebase

### 🟢 Forces de l'Architecture Actuelle
- **Découplage Métier (`backend/core/`)** : La logique d'évaluation, le moteur d'espacement SM-2 (`reviews/sm2.py`), la mesure de rétention (`knowledge/retention.py`) et la synchronisation SQLite sont indépendants du frontend.
- **Double Persistance Réactive** :
  - **Notion API** : Source de vérité pour la structure des cours et métadonnées.
  - **SQLite local (`data/synapse_local.db`)** : Stockage ultra-rapide sans latence de l'historique des révisions, des sessions d'entraînement et des lacunes.
- **Évaluation Multi-Preuves de la Maîtrise (`mastery.py`)** : Fusion des seeds déclarées (anciens collèges), révisions Anki, QCM/DP réels et annales UNESS.
- **Liaison Obsidian Bidirectionnelle** : Conservation du vault Markdown personnel avec intégration via `frontmatter` (`notion_id`, `synapse_id`).

### ⚠️ Points de Vigilance et Dette Technique
1. **Coexistence Cockpit vs Vues Historiques** :
   - Présence simultanée de pages standard et `_cockpit` (`todo.py` / `todo_cockpit.py`, `planning.py` / `planning_cockpit.py`).
   - *Action requise* : Unifier définitivement le routage et nettoyer les composants doublons.
2. **Enforcement de la Canonicalité des Items (CONTEXT.md)** :
   - Un Item EDN canonique (ex: *Item 221 - Asthme*) peut apparaître dans plusieurs collèges (Pneumologie, Pédiatrie).
   - *Action requise* : Veiller à ce que l'ensemble des tentatives QCM, lacunes et notes Obsidian soient rattachés à l'identifiant canonique de l'Item.
3. **Résilience et Quotas Notion** :
   - Prévoir un mode dégradé 100% offline à partir du cache SQLite si l'API Notion est indisponible ou limitée en quota.

---

## 3. Amélioration des Fonctionnalités Existantes

### A. Dédoublement de la Maîtrise : Rang A vs Rang B
- **Problème** : Le score de maîtrise actuel (0-100) mélange toutes les notions d'un cours.
- **Détection Automatique du Rang (Annales, QCM AI, OIC, Obsidian)** :
  1. **Annales UNESS Officielles** : Extraction du rang (A ou B) depuis les métadonnées officielles des questions ou classification automatique par rapprochement avec l'intitulé LiSA/OIC de Rang A.
  2. **QCM / DP / KFP Générés par IA** : Le moteur de génération IA accepte une consigne de rang (ex: `"Mode Rang A strict"` ou `"Mode Rang B approfondi"`) et étiquette chaque question générée avec son rang exact.
  3. **Balises Obsidian & Callouts** : Parsing Regex des notes Markdown (`> [!RANG-A]`, `> [!RANG-B]`, `#rangA`, `#rangB`).
- **Solution** : Splitter la mesure de maîtrise dans `mastery.py` :
  - **Score Rang A (%)** : Objectif strict = 100% (Verrouillage de sécurité).
  - **Score Rang B (%)** : Indicateur de compétition.
- **Règle algorithmique** : Le moteur de recommandation priorise les révisions Rang A tant que ce dernier est jugé *fragile* ou *critique*.

### B. Algorithme de Rétention Hybride (SM-2 + FSRS-4.5)
- Ajustement dynamique de la stabilité et de la répétition espacée en fonction du nombre de jours restant avant la date du concours EDN.
- Resserrement automatique des fenêtres de révision à l'approche du Jour J (Mode Sprint).

### C. Diagnostic Fin & Historique des Erreurs dans la Vue ITEM (QCM, DP & Annales)
- **Détection & Classification Automatique** : Lors de la correction d'une Annale ou d'un QCM/DP, le système catégorise automatiquement l'erreur (et permet un ajustement rapide) :
  - 🛑 **Erreur de Rang A (Signal Rouge)** : Inconnaissance d'un indispensable / Zéro à la question.
  - ⚠️ **Erreur de lecture / Piège classique** : Confusion 1ère intention vs 2nde intention, contre-indication.
  - 🔍 **Lacune de diagnostic différentiel**.
  - ⏱️ **Erreur de gestion du temps**.
- **Centralisation dans la Vue Cockpit ITEM** :
  - Ajout d'une section dédiée **"🎯 Historique Pédagogique & Typologie des Erreurs"** dans la page ITEM.
  - Consultation et filtrage de tout l'historique d'entraînement (QCM, DP, Annales UNESS) par type d'erreur et par rang (A vs B).
  - Possibilité de rejouer en 1 clic uniquement les questions ratées pour cause de *Piège* ou d'*Erreur de Rang A*.

### D. Synchronisation Obsidian Enrichie (Extraction, Images & Édition Directe)
- **Extraction Automatique** : Affichage des blocs d'ancrage issus des notes Obsidian (`> [!MNEMO]`, `## 6. Pièges EDN`, `> [!ALGO]`) dans le viewer de fiches et la modale de feedback.
- **Édition Directe & Support des IMAGES depuis Synapse** :
  - Boutons d'action rapide `+ Moyen Mnémotechnique`, `+ Piège EDN` ou `+ Schéma / Image`.
  - **Prise en charge des Images** : Glisser-déposer, collage depuis le presse-papier ou sélection d'image (ECG, radio, schéma, tableau).
  - Synapse copie automatiquement l'image dans le dossier de pièces jointes du Vault Obsidian (ex: `99 - Pièces jointes/`) et insère la syntaxe `![[image.png]]` directement dans la section du fichier `.md`.
  - Rendu visuel immédiat dans le viewer Synapse et synchronisation fluide dans Obsidian.

---

## 4. Nouvelles Fonctionnalités Majeures EDN

### 1. ⏱️ Simulateur d'Épreuves Blancs & Mode Examen SNE / UNESS
- **Objectif** : Préparation mentale et stratégique aux conditions réelles.
- **Caractéristiques** :
  - **Dossiers Progressifs (DP)** de 15 à 20 questions à déroulement séquentiel.
  - **Règle d'Anti-Retour** : Une fois la question suivante affichée, impossible de modifier la réponse précédente.
  - **Barème EDN Officiel** :
    - 1 point (Toutes réponses exactes).
    - 0.5 point (1 erreur/omission).
    - 0.2 point (2 erreurs/omissions).
    - 0 point (3 erreurs ou omission d'une réponse indispensable).
  - **Gestion du Temps** : Chronomètre strict par dossier et analyse du rythme de réponse.

### 2. 🗣️ Module ECOS (Examens Cliniques Objectifs Structurés)
- **Contexte** : Épreuve pratique comptant pour **30% du score final de l'EDN**.
- **Caractéristiques** :
  - **Mode Station Chronométrée (8 minutes)** : 7 min de station + 1 min de retour/synthèse.
  - **Grilles d'Évaluation Officielle** :
    - Station Anamnèse / Interrogatoire.
    - Station Examen Physique.
    - Station Annonce Diagnostique / Communication.
    - Station Prise en Charge d'Urgence.
    - Station Éducation Thérapeutique.
  - **Module Audio & Playback** : Possibilité de simuler la station avec tuteur vocal IA (Patient simulé / Évaluateur) et auto-évaluation sur la grille de critères.

### 3. 🎯 Matrice Radar 30 Spécialités & EDN Score Predictor
- **Visualisation** : Graphique en radar couvrant les 30 collèges/spécialités médicales.
- **Score Prédit** : Estimation du centile / rang potentiel basé sur le pourcentage de validation du Rang A et des performances sur les annales UNESS.
- **Index de Rendement ("High-Yield Priority")** : Algorithme identifiant les 5 items dont la révision immédiate procurera le **plus grand gain de points à l'EDN** (items à fort poids à l'examen avec faible niveau de maîtrise actuel).

### 4. ⚡ Flash-Pièges Quotidiens ("Morning Flash-Zero Quiz")
- Quiz de 5 minutes au réveil / début de session.
- 10 questions ultra-rapides ciblant exclusivement :
  - Les contre-indications absolues.
  - Les zéros aux dossiers.
  - Les bilans initiaux systématiques.

### 5. 🤖 Tuteur Virtuel IA & Générateur de Cas Cliniques sur Lacunes
- Génération dynamique de cas cliniques et DP par IA ciblés sur les lacunes actives de l'étudiant enregistrées dans SQLite (`lacunes`).
- Débriefing personnalisé expliquant la physiopathologie et la justification des recommandations officielles.

### 6. 📅 Mode "Sprint Countdown EDN"
- Reconfiguration dynamique de l'interface et du calendrier selon le compte à rebours EDN :
  - **J-180 à J-90** : Apprentissage & Fichage (Focus Obsidian + SM-2).
  - **J-90 à J-30** : Entraînement Intensif (Annales UNESS + DP/KFP + ECOS).
  - **J-30 à J-0** : Révisions d'Urgence Rang A + Flash-Pièges + Épreuves Blancs.

---

## 5. Feuille de Route d'Implémentation

| Étape | Module | Description | Priorité |
|---|---|---|---|
| **Phase 1** | **Socle & Rang A/B** | Split de la maîtrise Rang A / Rang B + Nettoyage Cockpit routing | 🔴 Haute |
| **Phase 2** | **Simulateur d'Épreuves** | Mode examen DP/QI avec anti-retour et barème officiel UNESS | 🔴 Haute |
| **Phase 3** | **Module ECOS** | Entraînement aux 8 min de station ECOS avec grilles d'évaluation | 🟠 Moyenne |
| **Phase 4** | **Radar & Predictor** | Radar 30 spé, score prédictif EDN et Yield Index | 🟠 Moyenne |
| **Phase 5** | **Tuteur IA & Flash-Pièges** | Quiz matin 5 min et générateur de DP sur lacunes récurrentes | 🟢 Progressive |

---
*Ce document sert de référence officielle pour les évolutions du projet Synapse dans le cadre de la préparation à l'EDN.*
