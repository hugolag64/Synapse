# Synapse — Audit du Codebase & Feuille de Route d'Excellence EDN

**Date d'origine** : 2 août 2026  
**Dernière mise à jour** : 2 août 2026  
**Objectif** : Analyse complète du logiciel Synapse, suivi de l'avancement et définition des améliorations nécessaires pour maximiser la préparation à l'EDN (Examen Dématérialisé National).

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
1. **Coexistence Cockpit vs Vues Historiques** : [🟡 PARTIEL]
   - Vues Cockpit actives. Il reste à purger le code mort legacy post-return (~3 600 lignes).
2. **Enforcement de la Canonicalité des Items (CONTEXT.md)** : [🟢 FAIT]
   - Canonicalisation par `item_number` rattachée sur toutes les tentatives QCM, lacunes et notes Obsidian.
3. **Résilience et Quotas Notion** : [🟡 PARTIEL]
   - Cache SQLite réactif opérationnel. Backoff/retry sur client Notion en finition.

---

## 3. État d'Avancement des Améliorations Existantes

### A. Dédoublement de la Maîtrise : Rang A vs Rang B [🟢 FAIT]
- **Mesure dédoublée (`mastery.py`)** : `score_rang_a` (%) et `score_rang_b` (%) calculés et mis à jour.
- **Sécurité Rang A stricte** : Si `score_rang_a < 75%`, l'item est automatiquement bloqué en niveau `fragile` ou `critique`, interdisant le niveau `solide`/`maîtrisé`.
- **Mode "Sprint Rang A" (`service.py`)** : Injection automatique d'un boost de **+35 points de priorité** sur les révisions dont le Rang A est sous 75%.
- **Étiquetage IA des QCM / DP (`tasks.py`)** : Prise en charge des consignes `rank="A"` et `rank="B"` avec obligation pour le modèle de tagger chaque question.
- **Affichage Dual-Rank (`mastery_indicator.py`)** : Composant `dual_rank_badges()` affichant côte à côte `[🛡️ A: XX%]` et `[🎖️ B: YY%]`.

### B. Algorithme de Rétention Hybride (SM-2 + FSRS-4.5) [🟢 FAIT]
- Moteur FSRS/SM-2 hybride opérationnel avec calcul de rétention exponentielle et fenêtres de révision dynamique.

### C. Diagnostic Fin & Historique des Erreurs dans la Vue ITEM [🟢 FAIT]
- Historiographie centralisée des tentatives (`local_store.get_item_pedagogical_history`).
- Tagging et catégorisation des erreurs (*Erreur de Rang A*, *Piège*, *Lecture*, *Temps*).

### D. Synchronisation Obsidian Enrichie (Images & Édition Directe) [🟢 FAIT]
- **Service Obsidian (`service.py`)** : Synchronisation bidirectionnelle, mapping Notion/Vault, liens `obsidian://`.
- **Édition Rapide & Images (`obsidian_quick_edit_dialog.py`)** : Ajout en 1 clic de mnémotechniques (`💡`), pièges EDN (`⚠️`) et upload/collage d'images enregistrées dans `99 - Pièces jointes/`.

### E. Intégration du Podcast « L'Externe » dans la Vue ITEM [🟢 FAIT]
- **Service Backend RSS (`podcast_service.py`)** : Parsing et indexation automatique du flux RSS `https://anchor.fm/s/db4f429c/podcast/rss` par numéro d'item canonique.
- **Onglet Cockpit `🎙️ Podcast`** : Intégré dans `course_detail_cockpit.py` avec chargement asynchrone à l'activation et lecteur audio HTML5 pour écoute directe de l'épisode rattaché.

---

## 4. Nouvelles Fonctionnalités Majeures EDN (Planning)

### 1. ⏱️ Simulateur d'Épreuves Blancs & Mode Examen SNE / UNESS [🔴 À FAIRE / PHASE 2]
- **Dossiers Progressifs (DP)** de 15 à 20 questions à déroulement séquentiel.
- **Règle d'Anti-Retour** : Validation irréversible de la question courante avant passage à la suivante.
- **Barème EDN Officiel** (1pt / 0.5pt / 0.2pt / 0pt + annulation si oubli indispensable Rang A).
- **Chronomètre strict par dossier**.

### 2. 🗣️ Module ECOS (Examens Cliniques Objectifs Structurés) [🔴 À FAIRE / PHASE 3]
- **Mode Station Chronométrée (8 minutes)** : 7 min d'épreuve + 1 min de debrief.
- **Grilles d'Évaluation Officielle** (35 points par station).
- **IA Examinateur / Patient Simulé**.

### 3. 🎯 Matrice Radar 30 Spécialités & EDN Score Predictor [🔴 À FAIRE / PHASE 4]
- Radar interactif des 30 spécialités médicales.
- Score prédictif de classement EDN basé sur les annales et la couverture Rang A.
- **High-Yield Priority Index** (identifiant les 5 items à plus fort gain de points immédiat).

### 4. ⚡ Flash-Pièges Quotidiens ("Morning Flash-Zero Quiz") [🟢 FAIT / PHASE 5]
- Quiz rapide de 5 min au réveil (10 questions ciblées sur les contre-indications absolues et zéros aux dossiers).

### 5. 🤖 Tuteur Virtuel IA sur Lacunes [🟢 FAIT / PHASE 5]
- Génération dynamique de DP sur les lacunes actives enregistrées dans SQLite.

### 6. 📅 Mode "Sprint Countdown EDN" [🟢 FAIT / PHASE 5]
- Reconfiguration dynamique de l'agenda et de la charge selon la proximité de la date J-EDN.

---

## 5. Feuille de Route d'Implémentation Actualisée

| Étape | Module | Description | Statut |
|---|---|---|---|
| **Phase 1** | **Socle & Rang A/B** | Split maîtrise Rang A/B + Verrouillage de sécurité + Badges Dual-Rank | 🟢 **FAIT** |
| **Phase 1** | **Sync & Édit Obsidian** | Service Obsidian + Upload d'images + Modale d'ajout rapide (Mnemo/Piège) | 🟢 **FAIT** |
| **Phase 1bis** | **Podcast « L'Externe »** | Onglet Podcast dans la fiche ITEM, indexé depuis le flux RSS par numéro d'item | 🟢 **FAIT** |
| **Phase 2** | **Simulateur d'Épreuves** | Mode examen DP/QI avec anti-retour et barème officiel UNESS | 🔴 **À FAIRE** |
| **Phase 3** | **Module ECOS** | Entraînement aux 8 min de station ECOS avec grilles d'évaluation (30% EDN) | 🔴 **À FAIRE** |
| **Phase 4** | **Radar & Predictor** | Radar 30 spé, score prédictif EDN et High-Yield Index | 🔴 **À FAIRE** |
| **Phase 5** | **Tuteur IA & Flash-Pièges** | Quiz matin 5 min, générateur de DP sur lacunes et Sprint Countdown J-EDN | 🟢 **FAIT** |


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

---

## Mise à jour du 4 août 2026 — EDNpro, Prépa et ressources externes

### Livré

- **Connecteur EDNpro automatisé** : collecteur Playwright avec profil Chromium persistant et connexion Google réalisée manuellement dans la fenêtre visible. Les sessions EDN à partir de 2023 peuvent être capturées et reprises via un `manifest.json`.
- **Correction IA + import** : chaque session capturée peut être corrigée automatiquement, écrite dans un JSON canonique puis relue et importée dans les annales/QCM Synapse. EDNpro est explicitement marqué comme source fiable mais non officielle (`official: false`).
- **Classification question → item** : les items explicitement présents sont conservés ; sinon une classification IA limitée aux candidats plausibles est tentée. Les associations incertaines ne sont pas forcées et une question reçoit au maximum deux items.
- **Ressources vidéo** : les pages vidéo EDNpro sont indexées par URL stable, titre, catégorie et item éventuel. Les médias et URLs CDN temporaires ne sont pas téléchargés. Les ressources suffisamment confiantes apparaissent dans le panneau Ressources de la fiche item.
- **Onglet Prépa** : raccourcis intégrés pour EDNpro et Hypocampus, avec routes EDN, annales, iconographie, ECG, physiologie, anatomie/sémiologie et LCA. EDNi est préparé dans le catalogue mais désactivé tant que son accès n'est pas défini.
- **Coût IA** : le flux texte réutilise le routage économique existant (`UNESS_CORRECTION` Lite) ; un modèle visuel plus coûteux n'est pertinent que si des images sont réellement collectées.

### Vérification

- `pytest -q` : **1 026 tests passants**, 2 avertissements de dépendances externes.
- `python -m compileall -q backend frontend scripts` : réussi.
- `git diff --check` : réussi.
- Commits : `e671443` (intégration EDNpro/Prépa) et `0b24fa5` (cockpit, sprint et Flash-Zero).

### Limite restante

## Mise à jour du 4 août 2026 — correction de l'import EDNpro après vérification terrain

Les captures utilisateur ont révélé que l'ancien collecteur enregistrait seulement l'enveloppe de l'annale EDNpro : les groupes apparaissaient mais restaient à `0/0 sous-parties`, car le HTML de l'application React ne contenait pas les cartes de questions attendues. Le parcours EDNpro est différent d'UNESS et utilise une session `/annales/{id}?mode=consultation`.

### Corrigé

- Le collecteur Playwright écoute désormais les réponses JSON de la session EDNpro et joint les dossiers, questions, propositions et liens question→item ; il ne dépend plus des sélecteurs HTML de la page.
- Les sessions sont identifiées par leur véritable UUID EDNpro et leur libellé/épreuve, au lieu d'un slug inventé à partir du lien de catalogue.
- Les vidéos sont indexées depuis les données `learning_videos` associées à `item_edn`, puis enregistrées comme liens de page dans `prep_resources` ; aucune vidéo ni URL CDN temporaire n'est téléchargée.
- Une garde dans `import_source_exam` interdit maintenant de créer une annale locale sans question importable.
- Les quatre enveloppes EDNpro vides issues des tests (`0/0`) et la ressource vidéo de test ont été retirées après vérification qu'elles n'avaient aucune session liée. Une sauvegarde a été créée dans `data/backups/synapse_local-2026-08-04-pre-ednpro-empty-cleanup.db`.

### Vérification

- Tests ciblés EDNpro/import : **17 tests passants**.
- La collecte réelle et la génération IA n'ont pas pu être exécutées dans cette session : le refresh EDNpro local est expiré/refusé. Après reconnexion Google, le bouton **Importer les EDN** lancera bien la capture structurée, la correction IA Lite, l'écriture/relecture du JSON canonique et l'import Synapse.

La première collecte réelle n'a pas encore été lancée : elle nécessite la connexion Google EDNpro de l'utilisateur et déclenchera les appels IA réels. Le flux est disponible via `python scripts/ednpro/collector.py --start-year 2023` ou le bouton **Importer les EDN** de l'onglet Prépa.

## Mise à jour du 4 août 2026 — hiérarchie des dossiers et réutilisation des corrections EDNpro

Les captures EDNpro ont confirmé que l'unité à importer n'est pas une simple liste de questions : une session contient des dossiers KFP/DP/QI, un contexte patient éventuel, puis les questions et propositions de chaque dossier. Le parcours de collecte reproduit maintenant cette hiérarchie au niveau des données JSON, sans dépendre de clics DOM fragiles sur une application React.

- Les dossiers, leur type, leur numéro et leur contexte patient sont conservés dans `metadata.dossiers` et `question.dp_context`.
- L'import EDNpro crée une sous-partie Synapse par dossier, rattachée à la même annale. Les questions et propositions sont donc visibles dans le parcours annale avec le contexte du dossier.
- Les réponses correctes, mauvaises et explications existantes EDNpro sont conservées dans l'archive JSON. Une version courte est affichée dans Synapse pour rester exploitable en révision.
- Quand la correction EDNpro est complète, aucune nouvelle correction IA n'est appelée : le flux réutilise la source et évite un coût de tokens. Le modèle Lite reste le repli pour les dossiers incomplets.
- La classification question → item et les ressources vidéo restent inchangées ; les liens vidéo sont des liens de page EDNpro, pas des téléchargements.

### Vérification actualisée

- `.venv\Scripts\python.exe -m pytest -q` : **1 033 tests passants**.
- `npm test -- --run` dans `qcm_app` : **6 tests passants**.
- `npm run build` dans `qcm_app` : build Vite réussi.
- `python -m compileall -q backend frontend scripts` et `git diff --check` : réussis.

La collecte réelle EDNpro reste conditionnée à une reconnexion Google dans le profil Chromium persistant ; aucun identifiant n'est automatisé ni stocké en clair par le collecteur.
