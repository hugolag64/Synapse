# Plan d’implémentation — fréquences EDNpro et priorité de gain

## Objectif

Collecter périodiquement les statistiques visibles dans EDNpro `/training-v2`,
les conserver dans SQLite et les exploiter dans la fiche item pour lancer les
questions EDNpro déjà importées et calculer un potentiel de gain local.

## Contraintes retenues

- EDNpro est une source tierce fiable mais non officielle.
- La collecte est due tous les 180 jours, non bloquante au démarrage.
- Playwright intercepte les réponses JSON de la page authentifiée ; aucune
  lecture de cookies ou extraction de jeton n’est nécessaire.
- Aucun appel IA n’est ajouté à cette fonctionnalité : la collecte et le score
  restent déterministes et peu coûteux.
- Un échec de collecte conserve le dernier snapshot valide.

## Étapes

### 1. Tests rouges et modèle pur

Fichiers :

- `tests/test_ednpro_frequency.py`
- `backend/core/ednpro/frequency.py`

Ajouter d’abord des tests qui décrivent :

- la normalisation de plusieurs formes de JSON EDNpro ;
- la fusion des doublons, le tri des années et les catégories ;
- le seuil de 180 jours ;
- le score `fréquence × (100 - maîtrise) × disponibilité`.

Lancer le fichier de tests et constater l’échec avant l’implémentation.

### 2. Snapshot SQLite

Fichiers :

- `backend/core/reviews/local_store.py`
- `tests/test_ednpro_frequency_store.py`

Créer `ednpro_item_frequency` et des fonctions ciblées : lecture par item,
lecture du snapshot, remplacement atomique d’une collecte valide et
filtrage des questions de pratique EDNpro importées par item. Les tests
utiliseront une base temporaire sans modifier la base utilisateur.

### 3. Collecteur Playwright et orchestration

Fichiers :

- `backend/core/ednpro/frequency_sync.py`
- `scripts/ednpro/frequency_collector.py`
- `tests/test_ednpro_frequency_sync.py`

Implémenter :

- interception des réponses JSON déclenchées par `/training-v2` ;
- extraction tolérante des lignes item, catégorie, sessions, questions et
  années, avec conservation d’un payload brut borné pour audit ;
- utilisation du profil persistant EDNpro existant ;
- refus propre si aucune réponse exploitable ou si la session est absente ;
- écriture SQLite uniquement après normalisation complète ;
- commande CLI avec `--force`, `--start`/`--headless` si déjà supportés par le
  collecteur existant, et sortie synthétique exploitable par l’interface.

Ajouter une fonction `sync_if_due()` réutilisable par l’application et un
garde-fou pour ne pas lancer deux collectes simultanément.

### 4. Synchronisation non bloquante

Fichier : `backend/core/background.py`.

Brancher `sync_if_due()` dans la boucle existante, avec un lancement asynchrone
unique et silencieux quand la collecte n’est pas due. Ne pas supprimer ni
remplacer les statistiques en cas d’échec.

### 5. Entraînement depuis la fiche item

Fichiers :

- `frontend/components/ai_practice_panel.py`
- `backend/core/reviews/local_store.py`
- `tests/test_ednpro_practice_filter.py`

Ajouter dans l’onglet Entraînement :

- catégorie EDNpro, sessions, questions, années et date de collecte ;
- score de potentiel de gain utilisant la maîtrise actuelle ;
- bouton `Travailler les annales` qui réutilise les sessions QCM existantes
  filtrées sur l’item ;
- état désactivé et explicite lorsque les statistiques existent mais qu’aucune
  question EDNpro n’est importée.

Ne pas créer de lecteur parallèle ni de nouveau format de question.

### 6. Audit, vérification et commit

Mettre à jour `docs/AUDIT_2026-08-03.md` et/ou la feuille de route avec :

- le snapshot SQLite et le collecteur implémentés ;
- la cadence de 180 jours ;
- l’exploitation dans la fiche item ;
- la limite actuelle : une session EDNpro authentifiée est requise pour une
  collecte réelle.

Vérifier :

```text
.venv\Scripts\python.exe -m pytest -q
.venv\Scripts\python.exe -m compileall -q backend frontend scripts
git diff --check
```

Puis inspecter les branches et créer un commit unique de la fonctionnalité,
sans inclure de secrets, de profil Playwright ni de base utilisateur.
