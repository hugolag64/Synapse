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

## 7. Sauvegardes chiffrées et test de restauration

Le script `deploy/synapse-backup.sh` crée un snapshot SQLite cohérent, archive le volume
`synapse-data`, chiffre l'archive avec AES-256-CBC/PBKDF2, puis écrit le même artefact sur
deux volumes distincts. Le manifeste SHA-256 détecte une copie corrompue. La clé ne doit
jamais être dans le dépôt ni dans un volume Docker.

Préparer un second volume réellement monté (par exemple `/dev/sdb1` dans `/srv/backups`
et un autre volume dans `/srv/backups/synapse-secondary`), puis vérifier que les sources
de montage diffèrent :

```bash
sudo install -d -m 700 /srv/backups/synapse /srv/backups/synapse-secondary /etc/synapse
sudo openssl rand -base64 48 | sudo tee /etc/synapse/backup.pass >/dev/null
sudo chmod 600 /etc/synapse/backup.pass
findmnt -T /srv/backups/synapse
findmnt -T /srv/backups/synapse-secondary
```

Installer les scripts et les timers :

```bash
sudo install -m 755 deploy/synapse-backup.sh deploy/synapse-restore-test.sh /srv/docker/stacks/synapse/deploy/
sudo install -m 644 deploy/synapse-backup.service deploy/synapse-backup.timer \
  deploy/synapse-restore-test.service deploy/synapse-restore-test.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now synapse-backup.timer synapse-restore-test.timer
```

Lancer une première sauvegarde et son test avant de considérer le dispositif opérationnel :

```bash
sudo systemctl start synapse-backup.service
sudo systemctl start synapse-restore-test.service
sudo journalctl -u synapse-backup.service -u synapse-restore-test.service --since today
```

Le timer de sauvegarde s'exécute chaque jour à 03:30 avec une conservation de 14 copies.
Le timer de restauration s'exécute le premier dimanche de chaque mois à 05:00 et vérifie
le SHA-256, le déchiffrement, l'extraction et `PRAGMA integrity_check` de SQLite. Les deux
timers sont `Persistent`, donc une machine arrêtée rattrape l'exécution manquée.

Les volumes `synapse-logs` et le vault Obsidian peuvent avoir leur propre stratégie de
sauvegarde ; ils ne remplacent pas la sauvegarde chiffrée de `synapse-data`.

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
