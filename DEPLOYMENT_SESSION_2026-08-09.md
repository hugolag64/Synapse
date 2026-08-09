# Déploiement Synapse sur Homeserver Ubuntu - Session 2026-08-09

## Résumé
Déploiement réussi de l'application Synapse (NiceGUI + FastAPI) sur Ubuntu homeserver avec Docker/Portainer. 
**Statut: FONCTIONNEL mais accès via nom de domaine reste à corriger.**

---

## Procédure de mise à jour validée

Depuis le PC local, pousser le commit sur `origin/main`, puis exécuter sur le home server :

```bash
cd /srv/docker/stacks/synapse
git pull --ff-only origin main
docker compose build --pull synapse
docker compose up -d --force-recreate synapse
```

### Dernière mise à jour

- Commit déployé : `3ea0929`
- `git pull --ff-only origin main` : OK
- Build Docker avec Chromium : OK
- Conteneur `synapse` recréé et démarré : OK

### Étape suivante

QA navigateur sur `http://192.168.1.5:8888` : vues Collèges, Item/Ressources, Annales, mode concours, Correction, Revue et Paramètres.

### QA navigateur effectuée — 2026-08-09

- URL : `http://192.168.1.5:8888`
- Outil : Chromium via Playwright
- Routes testées : `/colleges`, `/prepa`, `/annales`, `/revue`, `/settings`
- Résultat technique : les cinq routes répondent sans `Traceback`, `Internal Server Error` ni exception visible dans le DOM.
- Contrôles confirmés : `Pilotage global` et `Avancement de lecture` dans Collèges ; EDNpro et Hypocampus dans Prépa ; `Épreuves EDN` et `Épreuves par matière` dans Annales ; `FOCUS SEMAINE PROCHAINE` dans Revue ; en-têtes `CONNEXIONS`, `PLANIFICATION EDN` et `LISA / OIC` dans Paramètres.
- Limites : la vue Collèges emploie `Avancement de lecture` plutôt que `Progression/Statut` ; EDN-i n'est pas présent dans les données rendues de cet environnement ; le repliage complet par domaine des Paramètres reste à finaliser.

La QA confirme la stabilité de navigation, mais ne vaut pas validation visuelle finale de ces trois points.

### Tranche Paramètres — état au 2026-08-09

- Commit local poussé : `ef6a59c` (`feat: organize settings by collapsible domains`)
- Tests locaux : `1306 passed, 2 warnings`
- Vérification Chromium sur `http://192.168.1.5:8888/settings` : serveur accessible sans erreur, mais ancienne version encore active (`APPARENCE`, `UNESS`, anciens panneaux).
- Historique : lors de la première tentative, la QA était en attente du déploiement de `ef6a59c` sur le homeserver.

Commande à exécuter sur le homeserver :

```bash
cd /srv/docker/stacks/synapse
git pull --ff-only origin main
docker compose build --pull synapse
docker compose up -d --force-recreate synapse
```

### QA Paramètres validée — nouvelle version

- URL : `http://192.168.1.5:8888/settings`
- Les six domaines sont visibles : `CONNEXIONS`, `APPARENCE ET ACCESSIBILITÉ`, `PLANIFICATION EDN`, `DONNÉES UNESS`, `LISA / OIC`, `DIAGNOSTICS ET TÉLÉMÉTRIE`.
- Au chargement, les contenus `Notion` et `Date cible EDN` sont invisibles ; les en-têtes restent accessibles.
- Après ouverture de `CONNEXIONS`, `Notion` devient visible. L'ouverture de `PLANIFICATION EDN` referme `CONNEXIONS`.
- Le bouton `Enregistrer la planification` et le bouton `Rafraîchir tous les OIC (LiSA)` sont accessibles après ouverture.
- Aucun `Traceback`, `Internal Server Error`, exception DOM ou log navigateur d'erreur/avertissement n'a été relevé.

### Tranche métriques Collèges — état au 2026-08-09

- Commits applicatifs poussés : `79a69e3` et `5426989`
- Tests locaux : `1310 passed, 2 warnings`
- Le code sépare désormais `Lecture`, `Maîtrise` et `Statut`, et un collège `valide` est présenté comme entièrement lu sans créer de score de maîtrise.
- Vérification Chromium actuelle sur `/colleges` : l'instance accessible affiche encore l'ancienne grille (`Fragile`, ancien pilotage) ; le commit Collèges n'est donc pas encore visible sur le homeserver.
- QA navigateur de cette tranche : en attente du déploiement de `5426989`.

Commande de mise à jour homeserver :

```bash
cd /srv/docker/stacks/synapse
git pull --ff-only origin main
docker compose build --pull synapse
docker compose up -d --force-recreate synapse
```

## État actuel

### ✅ Complété
- ✅ Structure Docker créée: `/srv/docker/stacks/synapse/`
- ✅ Dockerfile multi-stage (Python 3.11-slim)
- ✅ docker-compose.yml avec volumes nommés (synapse-data, synapse-logs)
- ✅ Code Synapse cloné via Git: `https://github.com/hugolag64/Synapse`
- ✅ Variables d'environnement (.env) créées avec secrets
- ✅ Image Docker buildée et conteneur en cours d'exécution
- ✅ Port 8888 mappé vers port 8000 du conteneur
- ✅ Nginx Proxy Manager configuré pour synapse.local
- ✅ AdGuard DNS configuré pour résoudre synapse.local → 192.168.1.5
- ✅ **Accès direct fonctionnel: http://192.168.1.5:8888** ✨

### ⚠️ Problème restant
- ❌ Accès via `http://synapse.local` → **504 Gateway Timeout**
- Cause probable: Timeout Nginx PM trop court pour première requête (preload données Notion)

---

## Configuration appliquée

### Infrastructure
- **OS**: Ubuntu Server
- **IP fixe homeserver**: 192.168.1.5
- **Port Synapse**: 8888 (host) → 8000 (conteneur)
- **Runtime**: Docker + Portainer + Nginx Proxy Manager + AdGuard

### Fichiers clés créés

#### `/srv/docker/stacks/synapse/Dockerfile`
```dockerfile
FROM python:3.11-slim as builder
WORKDIR /app
COPY synapse/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

FROM python:3.11-slim
WORKDIR /app
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY synapse/ .
RUN mkdir -p /app/data /app/logs
EXPOSE 8000
CMD ["python", "main.py"]
```

#### `/srv/docker/stacks/synapse/docker-compose.yml`
```yaml
version: '3.9'

services:
  synapse:
    build: .
    container_name: synapse
    restart: unless-stopped
    
    ports:
      - "8888:8000"
    
    environment:
      - TZ=Europe/Paris
    
    env_file:
      - .env
    
    volumes:
      - synapse-data:/app/data
      - synapse-logs:/app/logs

volumes:
  synapse-data:
    driver: local
  synapse-logs:
    driver: local
```

#### `/srv/docker/stacks/synapse/synapse/main.py` (modifications)
**Ligne 314-315:**
```python
host='0.0.0.0',  # ← MODIFIÉ (était 127.0.0.1)
port=8000        # ← MODIFIÉ (était 8082)
```

### Nginx Proxy Manager
**Route créée:**
- Domain: `synapse.local`
- Scheme: `http`
- Forward to: `192.168.192.2:8888` (IP Docker du conteneur)
- Websockets Support: ✅ Activé
- Block Common Exploits: ✅ Activé

### AdGuard Home
**DNS Rewrite:**
- Domain: `synapse.local`
- IP: `192.168.1.5`

---

## Logs de démarrage

```
NiceGUI ready to go on http://localhost:8000, and http://192.168.192.2:8000
Global Preload Completed Successfully
```

**Nota**: Les premières requêtes prennent ~5-10 sec (preload données Notion depuis 3 bases de données, 700+ cours, 366 items).

---

## Accès fonctionnel

```
✅ Accessible: http://192.168.1.5:8888
❌ Non fonctionnel: http://synapse.local (504 Gateway Timeout)
```

---

## Problème 504 Gateway et solutions possibles

### Diagnostic
- Le timeout du preload Notion (≈5-10 sec) dépasse le timeout Nginx PM par défaut (≈60 sec normalement, mais peut être plus court)
- Première requête = preload global + sync Notion = temps élevé

### Solutions à tester
1. **Augmenter timeouts Nginx PM:**
   - Dans Nginx PM UI → Edit synapse.local
   - Chercher paramètres: `proxy_connect_timeout`, `proxy_send_timeout`, `proxy_read_timeout`
   - Augmenter à 300s

2. **Custom Locations dans Nginx PM:**
   - Ajouter une rule pour augmenter les timeouts spécifiquement

3. **Alternative:** Accepter l'accès direct via IP (http://192.168.1.5:8888)

---

## Données stockées

### Volumes Docker
- `synapse-data:/app/data` → SQLite DB + backups + cache
- `synapse-logs:/app/logs` → Logs rotatifs

### Fichier .env
Localisation: `/srv/docker/stacks/synapse/.env` (permissions 600)
Contient: NOTION_TOKEN, GEMINI_API_KEY, OPENAI_API_KEY, LISA credentials, etc.

---

## Commandes utiles

```bash
# Démarrer
cd /srv/docker/stacks/synapse
docker compose up -d

# Arrêter
docker compose down

# Logs
docker logs synapse -f

# Rebuild
docker compose build --no-cache
docker compose up -d

# Vérifier configuration
docker exec synapse grep "host=\|port=" /app/main.py
```

---

## Prochaines étapes

1. **Fixer accès synapse.local:**
   - Tester augmentation timeouts Nginx PM
   - Ou utiliser Custom Locations
   - Ou accepter IP directe

2. **SSL/HTTPS (optionnel):**
   - Nginx PM peut générer certificats self-signed ou Let's Encrypt

3. **Monitoring:**
   - Vérifier logs via `/app/logs/synapse_*.log`
   - Monitor CPU/mémoire dans Portainer

4. **Backup:**
   - Backup volume `synapse-data` régulièrement
   - Docker volumes stockés dans `/var/lib/docker/volumes/`

---

## Notes de déploiement

- **Modification importante:** Changement host/port dans main.py était critique
  - NiceGUI par défaut écoute 127.0.0.1:8082
  - Requis pour conteneur Docker accessible de l'extérieur

- **docker compose build vs docker build:**
  - Utiliser `docker compose build --no-cache` pour reconstruire via compose
  - Évite les conflits avec nommage d'image

- **Architecture réseau Docker:**
  - Conteneur IP: 192.168.192.2 (réseau Docker interne)
  - Host IP: 192.168.1.5
  - Nginx PM (Docker) peut contacter Synapse (Docker) via IP conteneur

---

## Contacts / Infos session

- **Date**: 2026-08-09
- **User**: hugo@192.168.1.5
- **Repo**: https://github.com/hugolag64/Synapse
- **App**: Synapse (Medical education tracking platform)
- **Stack**: Python 3.11 + NiceGUI + SQLite + Notion API

## Tranche alignement grille items Collèges - 2026-08-09

- Commit applicatif pousse : `a3a0e83` (`fix: align college item grid columns`)
- Correction : colonne `Action` fixee a `88px` dans le `DataGrid` et le CSS partage ; les enfants de grille utilisent `min-width:0`.
- Tests : `1311 passed, 2 warnings` ; tests cibles : `16 passed, 1 warning`.
- QA distante : l'instance visible repond, mais affiche encore l'ancienne grille (`%`, `FRAGILES`) ; la correction n'est pas encore deployee.
- Deploiement homeserver : tentative realisee avec la commande habituelle, echec SSH `Permission denied (publickey,password)`.

## Suite alignement resume Colleges - 2026-08-09

- Correction : `.cg-head` et `.cg-row` utilisent maintenant la meme grille fixe ; les largeurs avec padding sont bornees par `box-sizing:border-box`.
- Tests cibles : `17 passed, 1 warning`.
- Suite complete : `1312 passed, 2 warnings`.
- QA distante non concluante : l'instance visible n'est pas encore reconstruite depuis `main` et affiche encore l'ancien resume.
- Nouvelle tentative SSH : `Permission denied (publickey,password)`.

## Suite uniformisation vue OIC - 2026-08-09

- Commit applicatif pousse : `a425e5f` (`fix: stabilize OIC panel row layout`).
- Correction : lignes OIC en trois zones fixes code / contenu / actions, avec variante mobile.
- Tests cibles OIC et ressources : `9 passed, 1 warning`.
- Suite complete : `1312 passed, 2 warnings`.
- Etat au moment de la tentative locale : QA et deploiement en attente ; cette attente a ensuite ete levee par le deploiement homeserver confirme ci-dessous.

## QA effective apres deploiement OIC - 2026-08-09

- Deploiement confirme par le homeserver : `git pull` vers `7bfb39f`, build Docker termine, conteneur `synapse` demarre.
- `/colleges` : 8 tracks detectees ; les positions et largeurs de l'en-tete et d'une ligne sont identiques pour les 7 colonnes de contenu.
- `/cours/256b9fc3-1e69-804a-acab-f1fbe576c5a1` puis onglet OIC : 9 objectifs charges, Rang A/B visibles, boutons de maitrise et d'evaluation visibles.
- Mesure OIC : tracks identiques `110px / contenu / 132px` sur les deux premieres lignes controlees.
- Aucun `Traceback`, `Internal Server Error`, log navigateur `error` ou `warning`.

## Suite alignement QCM - 2026-08-09

- Commit applicatif pousse : `94b5170` (`fix: stretch QCM course rows to full width`).
- Cause corrigee : les lignes QCM occupaient `378px` contre `547px` pour l'en-tete ; `.qc-head` et `.qc-row` sont maintenant forces a `width:100%` avec `box-sizing:border-box`.
- Tests cibles : `28 passed, 1 warning`.
- Suite complete : `1313 passed, 2 warnings`.
- Deploiement et mesure Chromium en attente ; tentative SSH locale : `Permission denied (publickey,password)`.

## Mise Ã  jour QA Chromium CollÃ¨ges - 2026-08-09

- La route `http://192.168.1.5:8888/colleges` rÃ©pond, mais reste sur `Chargement des donnÃ©esâ€¦` aprÃ¨s attente prolongÃ©e.
- Aucun `Traceback`, `Internal Server Error`, exception DOM ou log navigateur `error`/`warning` n'a Ã©tÃ© relevÃ©.
- Les en-tÃªtes de la nouvelle grille et les KPI du pilotage ne sont pas rendus tant que le prÃ©chargement n'est pas terminÃ© ; ils ne sont donc pas validÃ©s visuellement.
- La QA de cette tranche reste en attente du dÃ©ploiement effectif et/ou de la rÃ©solution du prÃ©chargement serveur.
