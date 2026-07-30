# Regroupement des Annales UNESS par partiel

## Contexte

Le pipeline manuel ChatGPT (voir `2026-07-30-uness-manual-chatgpt-bridge.md`) importe chaque sous-partie d'un partiel UNESS (mDP1, DP1, DP2, SQI1, ...) comme une session de pratique indépendante via `import_uness_exam`. La page `frontend/pages/annales.py` liste donc aujourd'hui une ligne par sous-partie, alors qu'un partiel réel est identifié par une seule URL UNESS et un seul export ChatGPT, quel que soit le nombre de sous-dossiers qu'il contient.

Les métadonnées `faculty`, `level`, `year` existent déjà dans `UnessExam` mais ne sont jamais reportées sur la ligne de session de pratique (`ai_practice_sessions`) : elles restent enfouies dans le JSON `import_metadata` de chaque question, non triables ni filtrables.

## Objectif

Une annale UNESS doit apparaître comme une seule ligne, triable/filtrable par matière, faculté, année et type d'annale (matière normale, concours blanc, vrai concours, EDN complet). Cliquer sur cette ligne ouvre la liste de ses sous-parties. Chaque sous-partie se joue et se corrige avec le lecteur Node déjà en place pour le QCM (`/qcm-app/?session=<id>`) — aucune nouvelle UI de prise de test n'est créée.

## Périmètre

- Regroupement des sessions de pratique UNESS déjà importées ou à importer, par partiel.
- Tag manuel du type d'annale à l'import (pas de déduction automatique).
- Réécriture de la page liste (`/annales`) et ajout d'une page détail (`/annales/{annale_id}`), en NiceGUI.
- Réutilisation à l'identique du lecteur/correction Node QCM existant pour la prise de test.
- Migration ponctuelle des 4 sessions déjà importées (id 10-13, run du 2026-07-30) vers le nouveau modèle.

Hors périmètre : toute nouvelle UI de prise de test ou de correction (déjà couverte par `qcm_app/`), déduction automatique du type d'annale, historique global cross-annales (au-delà de ce qu'affiche déjà la page détail par partiel).

## Modèle de données

Nouvelle table `uness_annales` :

| Colonne | Type | Notes |
|---|---|---|
| `id` | INTEGER PK | |
| `source_url` | TEXT NOT NULL | URL UNESS de l'annale ; identifiant naturel du partiel (« 1 URL = 1 partiel ») |
| `collected_at` | TEXT NOT NULL | Horodatage de la collecte, issu de `provenance.collected_at` |
| `faculte` | TEXT NOT NULL | |
| `niveau` | TEXT NOT NULL | |
| `annee` | INTEGER | |
| `matiere` | TEXT | |
| `titre` | TEXT NOT NULL | Titre du cours/UE UNESS, sans le suffixe de sous-partie |
| `type_annale` | TEXT NOT NULL | `matiere` \| `concours_blanc` \| `vrai_concours` \| `edn_complet` |
| `created_at` | TEXT NOT NULL | |

Contrainte d'unicité sur `source_url` seul (« 1 URL = 1 partiel », y compris entre deux collectes différentes de la même annale) : `collected_at` est conservé comme métadonnée de provenance mais ne fait pas partie de la clé.

Nouvelle colonne nullable `annale_id INTEGER` sur `ai_practice_sessions`, clé étrangère vers `uness_annales.id`. `NULL` pour toute session non issue d'UNESS (comportement inchangé).

## Flux d'import

`import_service.import_verified_directory()` évolue :

1. Regroupe les fichiers scannés de `UNESS/vérifiés/` par `provenance.source_url`.
2. Pour chaque groupe dont `source_url` n'existe pas déjà dans `uness_annales` : expose les métadonnées déduites (matière/fac/année/titre, déjà extraites par `convert_chatgpt_export.py` lors de la conversion) à l'appelant, qui doit fournir un `type_annale` avant que l'import puisse continuer. Le scan retourne ce groupe comme `pending_tag` plutôt que d'échouer ou de deviner.
3. Une fois le type fourni (via l'UI Paramètres), crée la ligne `uness_annales`, importe chaque fichier du groupe via `import_uness_exam` comme aujourd'hui, et renseigne `annale_id` sur chaque session créée.
4. Les groupes déjà connus (même `source_url` déjà en base) s'importent directement dans l'annale existante, sans étape de tag — une nouvelle collecte de la même URL vient donc s'ajouter au partiel déjà présent plutôt que d'en créer un doublon.
5. Le dédoublonnage par empreinte (`_exam_fingerprint`), l'archivage des fichiers `vérifiés/` et `à_vérifier/` restent inchangés.

Interface ajoutée : `list_pending_annale_tags() -> list[dict]` (groupes détectés sans type), `import_verified_directory(tags: dict[str, str] | None = None)` (accepte, par `source_url`, les types choisis par l'utilisateur pour les groupes en attente de cette invocation).

## UI Paramètres (`frontend/pages/settings_cockpit.py`)

Le bouton « Scanner les JSON vérifiés » lance un scan ; si des groupes `pending_tag` existent, une boîte de dialogue s'ouvre avant la finalisation :

- Une section par groupe en attente, préremplie (titre, matière, fac, année déduits du fil d'Ariane UNESS).
- Un `ui.select` pour choisir `type_annale` parmi les 4 valeurs.
- Bouton « Valider » qui relance l'import avec les types choisis ; bouton « Ignorer pour l'instant » qui laisse les fichiers dans `vérifiés/` sans les importer (pour ne pas forcer un choix dans l'immédiat).

## Pages frontend

### `frontend/pages/annales.py` (réécrite)

- Une ligne par `uness_annales`, avec : titre, matière, faculté, année, type, nombre de sous-parties terminées/total, score moyen des sous-parties terminées.
- Barre de contrôle : recherche texte, filtres matière / faculté / année / type (menus déroulants alimentés par les valeurs distinctes présentes en base), sur le modèle du panneau « HISTORIQUE REJOUABLE » de `qcm_cockpit.py`.
- Clic sur une ligne → `ui.navigate.to(f"/annales/{annale_id}")`.

### `frontend/pages/annale_detail.py` (nouvelle, route `/annales/{annale_id}`)

- En-tête : titre, matière/faculté/année/type, bouton retour vers `/annales`.
- Liste des sous-parties (sessions liées via `annale_id`), une carte par sous-partie affichant statut, score, boutons « Ouvrir »/« Rejouer ».
- Les boutons appellent `_open_node_qcm(session_id)` (nouvellement extrait en composant partagé, voir ci-dessous), donc `ui.navigate.to(f"/qcm-app/?session={session_id}")` — identique au comportement déjà utilisé par `qcm_cockpit.py`.

### Composant partagé

Extraction de la carte de session (rendu statut/score/actions) et de `_open_node_qcm` depuis `qcm_cockpit.py` vers `frontend/components/practice_session_card.py`, réutilisé par `qcm_cockpit.py` et `annale_detail.py` pour éviter la duplication.

## Migration des données existantes

`scripts/uness/backfill_annales.py` : parcourt les lignes `ai_practice_sessions` où `model LIKE 'uness-%'` et `annale_id IS NULL`, relit `faculty`/`level`/`year`/`source_url` depuis le premier `import_metadata.uness.provenance`/`import_metadata.uness.exam` disponible parmi ses questions, regroupe par `source_url`, invite une fois par groupe pour le `type_annale` (CLI interactif), crée la ligne `uness_annales` correspondante et met à jour `annale_id`. Exécuté une fois pour rattacher les 4 sessions du run du 2026-07-30 (id 10-13).

## Tests

- `tests/test_uness_annales_model.py` — schéma et contrainte d'unicité de `uness_annales`.
- `tests/test_uness_import.py` (étendu) — regroupement par `source_url`, `pending_tag` pour un nouveau groupe, import différé jusqu'à réception du type, attribution de `annale_id`, rattachement d'une nouvelle collecte à une annale déjà existante.
- `tests/test_settings_uness_import.py` (étendu) — la boîte de dialogue de tag apparaît pour un nouveau groupe et pas pour un groupe déjà connu ; « Ignorer » laisse les fichiers en place.
- `tests/test_annales_page.py` (nouveau) — tri/filtre par matière/faculté/année/type, navigation vers la page détail.
- `tests/test_annale_detail_page.py` (nouveau) — rendu des sous-parties, câblage vers `_open_node_qcm`.
- `tests/test_backfill_annales.py` (nouveau) — regroupement et création rétroactive à partir de sessions existantes sans `annale_id`.

## Gestion d'erreurs

- Fil d'Ariane UNESS insuffisant pour déduire matière/fac/année/titre : déjà rejeté explicitement par `_exam_metadata()` dans `convert_chatgpt_export.py` (`ValueError`) — le fichier concerné apparaît en erreur dans le résultat du scan plutôt que d'être importé avec des champs vides.
- Groupe en attente de tag jamais validé : les fichiers restent dans `vérifiés/`, aucune donnée partielle n'est créée en base.
- Contrainte d'unicité sur `source_url` : un second scan du même run, ou une nouvelle collecte de la même annale, ne recrée pas de ligne `uness_annales` ; les fichiers déjà archivés ne sont plus scannés (comportement actuel inchangé).
