# Déploiement Ubuntu et intégrations Synapse — Plan d’implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** rendre Synapse déployable sur Ubuntu/Docker avec un routage reproductible, une persistance explicite et des intégrations Notion/Obsidian/Anki testables.

**Architecture:** l’application écoute selon une configuration runtime (`SYNAPSE_ENV`, `SYNAPSE_HOST`, `SYNAPSE_PORT`) et expose un endpoint de liveness indépendant du preload Notion. Docker publie un port stable sur l’hôte ; Nginx Proxy Manager cible l’hôte, jamais une IP interne de conteneur. Obsidian est monté dans le conteneur pour la synchronisation, mais l’URI `obsidian://` est ouverte par le navigateur client ; AnkiConnect reste optionnel et son endpoint devient configurable.

**Tech Stack:** Python 3.11+, NiceGUI 3.8, FastAPI/Starlette, SQLite, Docker Compose, Notion API, Obsidian, AnkiConnect.

## Global Constraints

- Ne jamais committer `.env`, les tokens, les cookies ou les bases personnelles.
- Ne jamais utiliser une IP Docker fixe dans le reverse proxy.
- Le démarrage HTTP doit rester testable même si Notion, Obsidian ou Anki sont indisponibles.
- La migration des données existantes doit créer une sauvegarde avant restauration.
- Les changements de comportement Python suivent RED → GREEN → REFACTOR.

### Task 1: Contrat runtime et liveness

**Files:**
- Create: `backend/config/runtime.py`
- Modify: `main.py:305-317`
- Test: `tests/test_runtime_config.py`

**Interfaces:**
- Produces `RuntimeConfig(host: str, port: int, prod: bool)` and `get_runtime_config()`.
- `/api/healthz` returns HTTP 200 with `{"status": "ok"}` without attendre `DataStore.preload_all_views()`.

- [ ] Écrire les tests pour les défauts dev/prod et l’override des variables.
- [ ] Exécuter les tests et vérifier l’échec avant implémentation.
- [ ] Implémenter la configuration runtime et la route liveness.
- [ ] Exécuter les tests ciblés puis la suite complète.

### Task 2: AnkiConnect configurable et ouverture Obsidian côté navigateur

**Files:**
- Modify: `backend/config/settings.py`
- Modify: `backend/core/anki/client.py`
- Modify: `frontend/components/course_quick_actions.py`
- Test: `tests/test_anki_client.py` and a focused Obsidian link regression test.

**Interfaces:**
- `ANKI_CONNECT_URL` controls the AnkiConnect base URL; the default remains `http://127.0.0.1:8765`.
- The course action sends `obsidian://open?...` through NiceGUI navigation to the user’s browser instead of launching a browser on the Ubuntu server.

- [ ] Écrire les tests de configuration Anki et du lien Obsidian côté client.
- [ ] Exécuter les tests et observer les échecs attendus.
- [ ] Implémenter le minimum nécessaire.
- [ ] Exécuter les tests ciblés puis la suite complète.

### Task 3: Docker Compose reproductible

**Files:**
- Create: `Dockerfile`
- Create: `docker-compose.yml`
- Modify: `.env.example`
- Create: `deploy/README-UBUNTU.md`

**Interfaces:**
- The image runs the checked-out repository with `SYNAPSE_ENV=prod`, listens on container port `8000`, and uses `/app/data` and `/app/logs` as persistent paths.
- Host directories for Obsidian, medicine PDFs and faculty PDFs are explicit mounts, with safe empty defaults.
- The healthcheck calls `/api/healthz`; the compose file never hardcodes an internal Docker IP.

- [ ] Ajouter les fichiers de build/compose et les variables documentées sans secrets.
- [ ] Valider le YAML, le build context et les chemins avec des checks locaux disponibles.
- [ ] Documenter la route Nginx Proxy Manager vers `192.168.1.5:8888` ou le nom de service sur un réseau partagé.

### Task 4: Migration des données et protocole de validation

**Files:**
- Modify: `deploy/README-UBUNTU.md`
- Create: `deploy/validate-ubuntu.sh`

**Interfaces:**
- The runbook backs up the existing Docker volume before replacing it, copies `data/`, and checks HTTP, Notion, Obsidian and Anki separately.
- It explicitly marks Anki as unavailable unless AnkiConnect is reachable from the server/container.

- [ ] Décrire les commandes de sauvegarde/restauration non destructives.
- [ ] Ajouter un script de validation qui ne modifie ni Notion ni Obsidian.
- [ ] Après accès SSH, exécuter les checks distants et reporter chaque intégration avec preuves.

### Task 5: Vérification finale

- [ ] Exécuter `pytest -q`.
- [ ] Exécuter le build Docker et le smoke test HTTP si Docker est disponible.
- [ ] Vérifier l’absence de secrets dans le diff et rappeler la rotation des secrets déjà exposés.
- [ ] Mettre à jour le compte-rendu de déploiement avec l’état réel, les URLs et les limites restantes.
