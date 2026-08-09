# Déploiement Synapse sur Ubuntu Server

Cette procédure vise le serveur `192.168.1.5`, Docker Compose et Nginx Proxy Manager.
Elle sépare les quatre contrats qui étaient mélangés dans la session précédente :

- liveness HTTP de Synapse (`/api/healthz`) ;
- accès au conteneur via le port publié de l’hôte (`8888`) ;
- synchronisation du vault Obsidian monté dans le conteneur ;
- AnkiConnect, qui n’est disponible que si Anki est joignable depuis le serveur.

## 1. Préparer les dossiers

```bash
sudo mkdir -p /srv/docker/stacks/synapse
sudo mkdir -p /srv/data/obsidian /srv/data/medicine /srv/data/fac
sudo chown -R "$USER":"$USER" /srv/docker/stacks/synapse /srv/data
cd /srv/docker/stacks/synapse
```

Le dossier `/srv/data/obsidian` doit être un vault synchronisé sur Ubuntu (Syncthing,
rclone mount ou autre mécanisme maîtrisé). Le chemin Windows `G:\...` ne doit jamais
être placé dans l’environnement du conteneur.

## 2. Récupérer le dépôt et créer l’environnement

```bash
git clone https://github.com/hugolag64/Synapse.git .
cp .env.example .env
chmod 600 .env
nano .env
```

Renseigner dans `.env` les tokens et IDs Notion, les credentials LiSA/Gemini si
nécessaires, et surtout les chemins hôtes Ubuntu :

```dotenv
OBSIDIAN_HOST_PATH=/srv/data/obsidian
MEDICINE_HOST_PATH=/srv/data/medicine
FAC_HOST_PATH=/srv/data/fac
```

Le Compose remplace volontairement `OBSIDIAN_VAULT_PATH`, `MEDICINE_DIR` et `FAC_DIR`
par leurs chemins internes (`/data/...`). Ne recopier aucun `.env` Windows sans
relecture : il peut contenir des chemins invalides et des secrets arrivés à expiration.

## 3. Sauvegarder avant de remplacer un volume existant

```bash
mkdir -p /srv/backups/synapse
docker run --rm \
  -v synapse-data:/data:ro \
  -v /srv/backups/synapse:/backup \
  alpine sh -c 'tar czf /backup/synapse-data-before-migration.tgz -C /data .'
```

Pour importer une copie locale, arrêter le stack, préparer une archive du dossier
`data/` local, puis l’extraire dans le volume. Cette opération ne supprime pas le
volume : elle est précédée par l’archive ci-dessus.

```bash
docker compose down
docker run --rm \
  -v synapse-data:/data \
  -v /srv/backups/synapse:/backup \
  alpine sh -c 'tar xzf /backup/synapse-data-local.tgz -C /data'
docker compose up -d --build
```

Le fichier historique `data_cache.json` placé à la racine du dépôt est lu comme
fallback puis migré dans `/app/data/data_cache.json` au prochain enregistrement.

## 4. Démarrer et valider le conteneur

```bash
docker compose config
docker compose up -d --build
docker compose ps
curl -fsS http://127.0.0.1:8888/api/healthz
docker compose logs --tail=200 synapse
```

La réponse liveness attendue est `{"status":"ok"}`. Elle ne dépend pas du preload
Notion ; un éventuel échec Notion doit donc être analysé séparément dans les logs.

Le script `deploy/validate-ubuntu.sh` effectue ensuite les checks non destructifs :

```bash
./deploy/validate-ubuntu.sh
```

## 5. Configurer Nginx Proxy Manager

Le proxy ne doit pas cibler `192.168.192.2`, ni le port `8888` d’une IP de conteneur.
Cette IP peut changer et le service écoute sur `8000` dans le conteneur.

Utiliser l’une de ces routes stables :

- recommandé avec la configuration actuelle : `http://192.168.1.5:8888` ;
- alternative si NPM et Synapse partagent un réseau Docker : nom de service `synapse`,
  port `8000`.

Activer Websockets Support. Le proxy doit laisser `/api/healthz` répondre immédiatement.
Un timeout augmenté peut aider le confort de la première connexion, mais il ne corrige
pas un upstream mal routé.

## 6. Vérifier les intégrations

### Notion

Le check doit confirmer un accès de lecture aux bases configurées. Les écritures restent
à tester par une action contrôlée dans l’interface, après backup et vérification des IDs.

### Obsidian

Le serveur doit voir `/data/obsidian` et le scan doit compter les notes. L’action
« Ouvrir note Obsidian » envoie maintenant l’URI `obsidian://` au navigateur de
l’utilisateur ; elle ne tente plus d’ouvrir une application graphique sur Ubuntu.
Le vault doit être monté en lecture-écriture pour créer une note ou ajouter une image.

### Anki

AnkiConnect par défaut sur `127.0.0.1:8765` ne désigne que le conteneur. Si Anki tourne
sur un autre ordinateur, il faut un tunnel SSH ou un VPN sécurisé et renseigner
`ANKI_CONNECT_URL`. Ne pas exposer AnkiConnect directement sur Internet ou sur le LAN
sans contrôle d’accès.

Un statut Anki déconnecté n’empêche pas Synapse de démarrer ; il signifie simplement que
les actions de révision Anki doivent rester indisponibles jusqu’à rétablissement du lien.

## 7. Sauvegardes récurrentes

Sauvegarder régulièrement le volume `synapse-data`, le volume `synapse-logs` si besoin,
et le vault Obsidian selon son propre mécanisme de synchronisation. Conserver au moins
une copie hors du serveur avant toute mise à jour de l’image.

## 8. Sécurité immédiate

Le `.env` local contenait des credentials réels dans l’environnement de travail. Même
s’il est ignoré par Git, faire tourner les tokens Notion/OpenAI/Gemini, cookies et mots de
passe concernés après la migration, puis ne conserver les nouvelles valeurs que dans
`/srv/docker/stacks/synapse/.env` avec les permissions `600`.

## Reprise des collÃ¨ges validÃ©s avant Synapse

Cette reprise ne modifie pas Notion. Elle complÃ¨te uniquement SQLite et programme le
dÃ©but de consolidation au 20 aoÃ»t 2026.

Commencer par le rapport en lecture seule :

```bash
docker compose exec -T synapse \
  python deploy/reprise_historique_consolidation.py --dry-run
```

AprÃ¨s vÃ©rification du rapport, appliquer :

```bash
docker compose exec -T synapse \
  python deploy/reprise_historique_consolidation.py --apply
```

Le script sauvegarde SQLite, conserve les niveaux existants, crÃ©e les niveaux
manquants en `correct` et n'ajoute aucune fausse ligne J3/J7/J14/J30. Il est idempotent.
