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

### E. Intégration du Podcast « L'Externe » dans la Vue ITEM

- **Source** : flux RSS `https://anchor.fm/s/db4f429c/podcast/rss` — podcast **« L'EXTERNE »**, un épisode par item ECN/EDN.
- **Format des titres (vérifié sur le flux réel)** : `Episode {N} - {Titre du sujet} (item {numéro})`, ex. *"Episode 122 - Addiction au tabac (item 75)"*. Le numéro d'item est donc directement extractible par regex (`\(item (\d+)\)`), et le titre du sujet correspond de près à l'intitulé canonique EDN de l'item (utilisable pour une vérification/fuzzy-match de confiance via le même mécanisme que `item_title()` / `difflib.SequenceMatcher` déjà utilisé pour le rapprochement Obsidian et la dédup de cours dans `backend/state/store.py::_deduplicate_cours`).
- **Objectif** : à l'ouverture d'une fiche ITEM, si un épisode correspondant existe, l'afficher (lecteur audio intégré + lien direct) — sans navigation supplémentaire, sur le même principe que l'onglet **OIC** déjà présent dans `frontend/pages/course_detail_cockpit.py` (onglets actuels : Vue d'ensemble · Note · Révisions · Entraînement · Lacunes · OIC · Historique). Un nouvel onglet **« Podcast »** est le point d'insertion naturel — chargé à la demande comme l'onglet OIC, pas au chargement initial de la fiche.
- **Approche technique envisagée** (à valider, pas d'implémentation immédiate) :
  1. Récupérer et parser le flux RSS périodiquement (le podcast progresse épisode par épisode ; un cache local avec rafraîchissement peu fréquent suffit — pas besoin de temps réel).
  2. Construire un index `item_number → episode` (titre, date, lien audio direct `<enclosure>`, lien de page) au lieu de re-parser le flux à chaque affichage de fiche.
  3. Cas à gérer explicitement : plusieurs épisodes pour le même item (rediffusion/mise à jour — garder le plus récent ou lister les deux), item sans épisode correspondant (ne rien afficher, pas d'erreur), item multi-collèges (l'épisode se rattache à l'item canonique, pas à un collège précis — cohérent avec la règle de liaison canonique déjà en place pour Obsidian).
  4. Le titre du sujet extrait de l'épisode peut servir de garde-fou : si le fuzzy-match avec l'intitulé canonique de l'item est trop faible, signaler le rapprochement comme incertain plutôt que l'appliquer aveuglément (même logique que les "matchs douteux" du scan Obsidian dans `frontend/pages/settings.py`).

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
| **Phase 1bis** | **Podcast « L'Externe »** | Onglet Podcast dans la fiche ITEM, indexé depuis le flux RSS par numéro d'item | 🟢 Rapide à faible risque |
| **Phase 2** | **Simulateur d'Épreuves** | Mode examen DP/QI avec anti-retour et barème officiel UNESS | 🔴 Haute |
| **Phase 3** | **Module ECOS** | Entraînement aux 8 min de station ECOS avec grilles d'évaluation | 🟠 Moyenne |
| **Phase 4** | **Radar & Predictor** | Radar 30 spé, score prédictif EDN et Yield Index | 🟠 Moyenne |
| **Phase 5** | **Tuteur IA & Flash-Pièges** | Quiz matin 5 min et générateur de DP sur lacunes récurrentes | 🟢 Progressive |

---
*Ce document sert de référence officielle pour les évolutions du projet Synapse dans le cadre de la préparation à l'EDN.*

Audit technique & produit — 2 août 2026
Synapse, état des lieux
Lecture complète du dépôt (backend, frontend, pipeline UNESS) et pistes pour renforcer la préparation aux EDN. Deux angles : la fiabilité du code qui porte tes données de révision, et les fonctionnalités qui manquent encore pour couvrir l'examen.

51 140
lignes de Python (backend + frontend + scripts)
121
fichiers de tests · 956 tests passants au 1ᵉʳ août
~3 590
lignes de code mort mesurées (pages legacy)
13,5 Mo
synapse_local.db — aucune sauvegarde
01
Le plus gros chantier : purger les pages « legacy »
La refonte cockpit (sessions 0 à 15) a laissé chaque ancienne page en place comme coquille : elle délègue à la vue cockpit puis return — mais tout le code de l'ancienne interface reste écrit juste après, inatteignable. Vérifié fichier par fichier :

Fichier	Lignes totales	Point de return	Code mort
frontend/pages/qcm.py	1 993	915	1 078
frontend/pages/settings.py	945	178	767
frontend/pages/weak_points.py	670	85	585
frontend/pages/colleges.py	524	129	395
frontend/pages/planning.py	716	392	324
frontend/pages/semestres.py	153	19	134
frontend/pages/externat.py	567	437	130
frontend/pages/stats.py	877	776	101
frontend/pages/todo.py	800	726	74
Total			≈ 3 588
Ce n'est pas cosmétique : c'est 7 % du code Python du projet qui n'exécute jamais rien, concentré dans les fichiers que tu (et moi) rouvrons le plus souvent. Chaque lecture de qcm.py pour un futur changement oblige à distinguer visuellement la vraie logique (15 premières lignes) du reste. Le risque concret : modifier par erreur un bloc mort en pensant corriger le comportement réel.

Action recommandée : une fois la vue cockpit confirmée stable sur chaque page (ce qui semble être le cas), supprimer tout ce qui suit le return. Mécanique, sans risque fonctionnel, et ça fait disparaître d'un coup near 3 600 lignes.

02
Fiabilité des données
Revue approfondie de reviews/ (maîtrise & SRS), notion/, obsidian/, lisa/ et state/store.py — les modules qui décident ce que tu dois réviser et qui portent ton historique.

Critique
backend/state/store.py:248-331
Tes préférences repartent à zéro après 12h sans ouvrir l'app. load_from_disk() retourne False avant d'avoir rien lu — y compris preferences — dès que le cache dépasse 12h. Le rechargement qui suit (refresh()) ne restaure que les cours, jamais les préférences.

Concrètement : mode sombre, durées Pomodoro, semestre actuel, capacité de planning, panneau agenda — réinitialisés aux valeurs par défaut à chaque fois que tu n'ouvres pas Synapse pendant une nuit + une journée. Les révisions déjà validées mais pas encore migrées vers SQLite (done_review_ids) subissent le même sort et disparaissent silencieusement.

Important
backend/core/reviews/service.py:268-281
Le score de maîtrise affiché peut être périmé toute la journée. Le cache mastery n'est vidé qu'au changement de date, jamais après une validation. Seuls 6 écrans sur l'ensemble de l'app appellent invalidate_cache() — valider une révision depuis le dashboard ou le cockpit ne le fait pas. Résultat : le collège, la fiche item et le dashboard peuvent afficher trois maîtrises différentes pour le même cours après une validation.

Important
backend/core/obsidian/weak_points_sync.py:263-336
Une lacune renommée dans Obsidian peut se dupliquer en base. L'identifiant stable d'une lacune est un hash MD5 du chemin absolu du fichier. Le hash n'est écrit dans le frontmatter qu'après coup ; si le fichier est déplacé ou renommé avant cette écriture, le scan suivant calcule un nouveau hash et crée une nouvelle ligne SQLite au lieu de mettre à jour l'existante — statut et historique dupliqués sans avertissement.

Important
backend/core/obsidian/weak_points_sync.py — sync()
Sync Obsidian ↔ Synapse sans détection de conflit. Les deux sens d'écriture (frontmatter → SQLite et SQLite → frontmatter) s'écrasent mutuellement sans verrou ni horodatage de version. Si un scan tourne juste après un changement de statut côté UI (ou l'inverse), le dernier écrivain gagne en silence.

Important
backend/core/notion/client.py:23-136
Aucun retry sur les appels Notion. Un simple rate-limit (429) ou un blip réseau fait échouer directement l'opération sur ta source de vérité — sans nouvelle tentative. Sur le point de sync le plus sollicité de l'app, ça mérite un backoff.

Mineur
backend/core/reviews/local_store.py
Un module de 4 385 lignes / 165 fonctions qui mélange historique SRS, sessions QCM, banque de questions IA, annales UNESS, points faibles, cache PDF et planning manuel. Ça reste fonctionnel, mais chaque nouvelle fonctionnalité qui y touche augmente le risque de collision.

Mineur
sm2.py · mastery.py · knowledge/retention.py
Trois échelles de « maîtrise » cohabitent (intervalle SM-2, score additif, courbe d'oubli exponentielle) sans test d'intégration bout-en-bout qui vérifie qu'elles racontent la même histoire à l'utilisateur.

Positif
La façade validation.complete_review() est bien conçue : en cas d'échec de transition, la session créée et les propositions de lacune associées sont annulées plutôt que laissées incohérentes. L'API QCM protège correctement contre le path-traversal. Les appels bloquants vers LISA/AnythingLLM sont déchargés via asyncio.to_thread — pas de gel de l'event loop NiceGUI.

03
Risque opérationnel : la base locale n'est jamais sauvegardée
data/synapse_local.db pèse aujourd'hui 13,5 Mo et contient l'historique complet des QCM, l'évidence de maîtrise datée et les lacunes — des mois de préparation EDN. Aucun mécanisme de copie, versionnement ou export automatique n'existe dans le dépôt. Une corruption de fichier, un disque qui lâche ou une suppression accidentelle efface cet historique sans recours, alors que les cours (Notion) et les notes (Obsidian) ont chacun leur propre copie de sécurité de fait.

Action recommandée : une copie horodatée quotidienne (tâche de fond existante type daily_routine.py, ou une simple copie vers le vault Obsidian déjà synchronisé ailleurs) suffirait — coût d'implémentation faible pour le risque couvert.

04
Fonctionnalités — ce qui manque encore pour les EDN
Le document interne docs/synapse_audit_reconnexion_algorithmes.md couvre déjà en profondeur l'onglet Évaluation transverse, le mode Vacances, les connecteurs QCM externes et un prototype ECOS — je ne les redétaille pas ici, ils restent la bonne feuille de route pour ces chantiers. Ce qui suit, ce sont des angles qui n'y figurent pas encore.

Spécifique au format EDN
Module LCA (Lecture Critique d'Article)nouveau
Aucune trace de LCA dans le code (biostats, méthodologie, niveau de preuve) alors que c'est une composante à part entière de l'épreuve. Un mini-générateur d'exercices LCA (question de méthodo + article court + QRM) serait un axe totalement absent aujourd'hui, avec son propre suivi de maîtrise séparé du reste — c'est une compétence différente de la restitution de connaissance.
Tableau de bord « items orphelins »nouveau
Détecter automatiquement les items sans aucune évidence récente — zéro QCM, zéro carte Anki, zéro note Obsidian, zéro auto-évaluation — même quand le score de maîtrise affiché paraît correct grâce à d'anciennes données. Pour un examen exhaustif comme les EDN, les angles morts silencieux sont plus dangereux que les items déjà identifiés comme faibles.
Calibration de la confiance (score de Brier)nouveau
La roadmap interne mentionne déjà l'idée sans l'avoir conçue. Concrètement : à chaque QCM, demander un niveau de confiance, puis afficher une courbe de calibration (confiance annoncée vs taux de réussite réel) dans l'onglet Évaluation. Une sur-confiance systématique sur certains collèges est un signal correcteur puissant que le score de maîtrise seul ne capture pas.
Compte à rebours J-EDN avec replanification dynamiquenouveau
L'algorithme de planification (section 15 de la roadmap) priorise déjà bien au jour le jour, mais rien ne recalcule automatiquement les objectifs quotidiens en fonction du temps réellement restant avant la date d'épreuve. Un simple ajustement de la charge cible à mesure que J-EDN approche, avec alerte si la couverture du programme ne suit pas le rythme nécessaire.
Expérience de révision
Relance socratique sur les erreurs QCMnouveau
L'infrastructure Gemini/LISA existe déjà. Sur une réponse fausse, au lieu d'afficher directement la correction, une question de relance ciblée (« qu'est-ce qui, dans l'énoncé, excluait cette réponse ? ») avant de révéler l'explication — aligné avec l'axe « raisonnement clinique » déjà identifié comme prioritaire dans la roadmap interne.
Entraînement entrelacé (interleaving) explicite
La sélection de consolidation quotidienne pondère déjà par semestre avec un plafond de diversité — la base existe. La rendre visible et pilotable (« aujourd'hui, mélange 3 collèges » vs bloc unique) exploiterait plus consciemment l'effet d'entrelacement, documenté comme supérieur au bachotage bloqué pour la rétention à long terme.
Mode révision mobile / hors-ligne pour l'externat
Les créneaux de révision réels d'un externe sont souvent entre deux patients, sur téléphone. Une vue allégée (QCM rapides + Anki, sans le cockpit complet) fonctionnant hors connexion comblerait un usage que l'architecture desktop-first actuelle ne couvre pas.
Déjà scopé, pas commencé — rappel
Pour mémoire, sans reprendre le détail déjà écrit dans la roadmap interne.
Onglet Évaluation transverse (QCM, DP, KFP, OIC, Anki, lacunes dans une vue filtrable unique) — partiellement câblé par item, pas encore comme vue globale.
Mode Vacances — existe en configuration/planning, gestion complète des reports et de la reprise progressive à valider.
Connecteurs de sources QCM externes au-delà de l'UNESS (architecture à prévoir dès le départ pour ne pas dépendre d'une seule plateforme).
Prototype ECOS — station chronométrée, patient simulé, grille d'évaluation ; explicitement à concevoir avec toi avant tout développement.
05
Par où commencer
1
Corriger la perte de préférences après 12h
store.py — un seul point de défaillance, affecte l'usage quotidien dès la deuxième session.
Petit
2
Sauvegarde automatique de synapse_local.db
Copie horodatée quotidienne — coût minime, risque couvert important.
Petit
3
Invalider le cache mastery à chaque validation
Brancher invalidate_cache() dans complete_review() plutôt que dans 6 écrans séparément.
Petit
4
Supprimer le code mort des pages legacy
≈ 3 600 lignes, mécanique une fois le cockpit confirmé stable partout.
Moyen
5
Clé de liaison Obsidian stable + verrou de sync
Écrire le hash canonique avant tout renommage possible ; horodater les deux sens de sync.
Moyen
6
Retry/backoff sur le client Notion
Absorbe les 429 et blips réseau sur la source de vérité.
Moyen
7
Tableau de bord items orphelins + calibration
Les deux idées EDN à plus fort effet de levier pour la suite, une fois la base assainie.