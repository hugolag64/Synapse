# Synapse QCM frontend

Frontend Node/React du lecteur et de la correction QCM.

## Développement

Depuis ce dossier :

```powershell
npm install
npm run dev
```

Le serveur Vite écoute sur `http://127.0.0.1:52171`. Il proxy les appels `/api` vers Synapse sur `http://127.0.0.1:8082`.

## Production locale

```powershell
npm run build
python ..\main.py
```

Après redémarrage de Synapse, le bundle est servi sur `/qcm-app/`. Une session s’ouvre avec `/qcm-app/?session=<id>`.
