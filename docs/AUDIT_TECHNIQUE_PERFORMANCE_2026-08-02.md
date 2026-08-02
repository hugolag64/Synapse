# Synapse — Audit technique : performance, code mort, indirection

**Date** : 2 août 2026
**Portée** : ce document est complémentaire à `AUDIT_ET_FEUILLE_DE_ROUTE_EDN_2026-08-02.md` (fonctionnalités EDN) et à `synapse_audit_reconnexion_algorithmes(1).md` (reconnexion pédagogique). Il ne couvre que l'angle **technique** : fluidité perçue, code mort, complexité évitable. Un premier audit de fiabilité des données (bugs dans reviews/notion/obsidian/lisa/store, pas de backup DB) a déjà été livré séparément le même jour (artefact « Synapse — Audit & feuille de route », mémorisé dans `project_audit_aug2026.md`) — non répété ici, seulement rappelé en section E.

**Méthode** : 3 revues indépendantes (agents dédiés) sur le code mort repo-entier, la performance/fluidité, et l'indirection architecturale, chacune avec vérification croisée (grep cross-repo, lecture directe, pas de simple heuristique).

**État déjà acquis** : le code mort des 9 pages `frontend/pages/*.py` (legacy post-refonte cockpit) a été purgé et committé (`06d8383`) — **3454 lignes supprimées**, 955 tests toujours passants. Ne pas re-traiter.

---

## Suivi d'implémentation — 2 août 2026 (soir)

Sections A et B traitées dans la foulée de cet audit. Détail par point ci-dessous (marqué **FAIT**/**ÉVALUÉ, non appliqué**/**FAIT sur décision d'Hugo**) ; résumé :

- **A.1 FAIT** — `consolidation.py::get_due_consolidation_tasks` et `items.py` (page /items) utilisent maintenant `review_service._get_mastery_cached` au lieu d'appeler `get_course_mastery` à froid. C'était le vrai goulot (storm de requêtes N+1) — corrigé à la racine.
- **A.2 ÉVALUÉ, non appliqué** — tracé le chemin réel : `_full_rebuild()` (dashboard cockpit) est appelé depuis des callbacks *synchrones* (`_dialogs.py::_save_lacune`, `on_click=_save_lacune`). Le convertir en async pour permettre `asyncio.to_thread` aurait cassé silencieusement le rafraîchissement après ajout d'une lacune depuis le mode focus (un `_on_save()` non-awaité sur une coroutine ne s'exécute pas). Risque jugé disproportionné par rapport au gain restant une fois A.1 appliqué (le storm de requêtes, qui était la vraie cause du blocage, a disparu). Non fait.
- **A.3 — découverte en cours de route : `rebuild_all()` était du code mort.** `frontend/pages/dashboard/_reviews.py::rebuild_all()` (la fonction visée par ce point) n'était appelée que depuis `frontend/pages/dashboard/__init__.py`, lui-même une coquille `return`-après-cockpit du même type que les 9 pages déjà purgées — jamais détecté car c'est un `__init__.py` de sous-paquet, hors du périmètre du premier audit (`frontend/pages/*.py`). **Purgé** : `dashboard/__init__.py` (283→39 lignes) et `_reviews.py` (1087→25 lignes, ne garde que `open_focus_mode`, seul symbole encore importé ailleurs). Le vrai rebuild live (`_cockpit_today.py::_fetch()`/`_render()`) sépare déjà proprement données et UI, mais partage le même risque de callback synchrone que A.2 — non converti en async pour la même raison. Vérifié en navigateur (redémarrage à froid, dashboard + données réelles, aucune erreur serveur).
- **A.4 FAIT** — `local_store.py::get_all_pdf_cache()` ajoutée (1 requête au lieu de ~2 par cours, jusqu'à ~1400 pour 700 cours) ; `cleanup_pdf_cache()` batché (`executemany` au lieu d'un DELETE par ligne) ; toute la Phase A du préchargement déchargée du event loop via `asyncio.to_thread`. Vérifié sur redémarrage serveur à froid : préchargement réussi (~7s), aucune erreur.
- **A.5 — partiellement pertinent après vérification** : `get_streak_counts()` — caching écarté (risque réel de streak affiché faux si le cache survit à la validation de la tâche du jour) ; pagination Notion (`get_all_cours`) déjà optimale (le SDK utilise déjà 100/page par défaut, l'ajout explicite de `page_size=100` est un no-op) ; polling splash 2Hz laissé tel quel (commentaire existant explique déjà le choix délibéré) ; `save_to_disk()`/`auto_link_process` non touchés (même risque de callback synchrone qu'A.2, pas creusé faute de temps).
- **B.1** — déjà fait dans une passe précédente (voir plus bas, inchangé).
- **B.2 FAIT sur décision d'Hugo** — supprimés : `network_capture/ednpro_sync.py`, `network_capture/hypocampus_sync.py`, `ai_qcm/watcher.py`. **Gardé** : `anki/service.py` (sync deck Anki — feature à câbler plus tard, pas du code mort à jeter).

Vérification à chaque étape : compilation + `ruff --select F401,F811,F821,F841` + suite complète (`955 passants`, mêmes 8 échecs préexistants sans rapport — routage IA). Rien n'est commité.

---

## Résumé exécutif

Le point le plus important de cet audit n'est pas le code mort (qui est réel mais cosmétique) : c'est la **chaîne de performance A → B → C** en section 1, qui explique très probablement l'essentiel de la lenteur perçue au quotidien. La corriger a un effet direct sur *"rendre le programme plus fluide"*, bien plus que n'importe quelle suppression de fichier.

| Priorité | Sujet | Effet |
|---|---|---|
| 🔴 1 | Cache mastery absent dans `plan_consolidation` + verrou SQLite global + rebuild UI complet | Chaque clic "Valider une révision" peut geler l'app pour tout le monde pendant plusieurs centaines de ms à quelques secondes |
| 🔴 2 | Préchargement PDF cache bloquant au démarrage | Rallonge le temps avant que l'UI soit utilisable |
| 🟠 3 | ~1450 lignes de code mort certain, prêtes à supprimer sans risque produit | Réduit la surface de lecture/maintenance de ~3% supplémentaires |
| 🟠 4 | 2 fonctionnalités "désactivées" mais entièrement codées (EDN Pro/Hypocampus, watcher AI QCM) | Décision produit à prendre : réactiver, réparer, ou supprimer définitivement |
| 🟡 5 | ~290 imports différés sans justification technique réelle | Lisibilité, pas de coût perf mesurable |

---

## A. Performance & fluidité — la fuite principale

### A.1 — Storm de requêtes SQLite non cachées à chaque interaction (🔴 Élevé)

`backend/core/reviews/mastery.py:60-290` (`get_course_mastery`) exécute **6 à 8 requêtes SQLite par cours** (seed snapshot, couverture OIC, évidence Anki, sessions IA récupérées deux fois, sessions QCM, OIC LiSA), avec en plus un **N+1 imbriqué** dans `_canonical_retention_evidence` (mastery.py:368-376) — une requête `get_oic_attempts()` par OIC.

Cette fonction, **sans aucun cache**, est appelée en boucle sur ~600 cours à deux endroits :
- `backend/core/reviews/consolidation.py:86` (`get_due_consolidation_tasks`)
- `frontend/pages/items.py:195-199` (chargement de `/items`)

`get_due_consolidation_tasks()` est elle-même invoquée par `plan_consolidation()` (`planning/service.py:271`), appelée par **`rebuild_all()`** (`frontend/pages/dashboard/_reviews.py:866`) — la fonction qui reconstruit le dashboard **après chaque validation, report ou "passer" d'une révision**. Un seul clic sur "Valider" peut donc déclencher des milliers de requêtes SQLite synchrones.

### A.2 — Verrou global + appels synchrones dans la boucle asyncio (🔴 Élevé)

`backend/core/reviews/local_store.py:37-91` : une seule connexion SQLite pour les 165 fonctions du module, protégée par un `threading.RLock` global acquis à chaque `execute()`. Ces appels sont **100% synchrones**, jamais passés par `asyncio.to_thread` dans les chemins révision/mastery/items (contrairement à `background.py` et `google/calendar_service.py`, qui font ça correctement). NiceGUI tourne sur une seule boucle asyncio : chaque requête bloque **tous les onglets ouverts**, pas seulement celui qui a cliqué. C'est le facteur qui transforme A.1 (beaucoup de requêtes) en gel perceptible.

### A.3 — Reconstruction complète de l'arbre UI à chaque interaction (🔴 Élevé)

`frontend/pages/dashboard/_reviews.py:849-981` : `rebuild_all()` fait `clear()` puis reconstruit intégralement les colonnes "urgent", "aujourd'hui" et "semaine" pour un changement d'une seule ligne — destruction + recréation de tous les éléments NiceGUI (DOM + aller-retour WebSocket) au lieu d'une mise à jour incrémentale de l'élément modifié.

**→ A.1 + A.2 + A.3 forment une seule chaîne causale.** Corriger prioritairement : brancher `_get_mastery_cached` dans `consolidation.py:86` (au lieu d'appeler `get_course_mastery` à froid), puis rendre `rebuild_all()` incrémental.

### A.4 — Démarrage de l'app (🟠 Moyen-Élevé)

- `backend/state/store.py:340-348` : 2 requêtes SQLite séquentielles par cours (`get_pdf_cache`) dans `preload_all_views()`, sans `to_thread` — bloque le démarrage pour ~600 cours.
- `local_store.py:3879-3897` (`cleanup_pdf_cache`) : boucle Python avec `os.path.isfile()` (I/O disque) + `DELETE` individuel par ligne, appelée dans la même phase de préchargement.
- `backend/core/notion/service.py:756-762` (`get_streak_counts`) : récupère jusqu'à 100 pages Notion à chaque démarrage pour calculer un entier, sans cache, alors que l'historique des jours passés est immuable.

### A.5 — Autres points identifiés (🟡 Moyen/Faible)

- `local_store.py:634-641` (`get_all_history`) : `SELECT *` sans LIMIT sur une table qui grossit indéfiniment (jamais purgée), appelée à chaque rebuild dashboard et à chaque `/items`.
- Index manquants : `study_sessions` n'a qu'un index (`course_id`) alors que `get_active_weak_points()` filtre sur `weak_detail`/`weak_category`/`qcm_result` avec `TRIM()`/`LOWER()` (aucun index utilisable) ; `review_history` a 4 index séparés mais pas de composite couvrant les requêtes réelles (`status` + `DATE(completed_at)` — l'usage de `DATE()` empêche de toute façon l'index).
- `store.py:246` (`set_preference`) : `save_to_disk()` sérialise et réécrit **tous** les cours sur disque à chaque toggle de préférence (dark mode, tri…), de façon synchrone.
- `background.py:468-524` (`auto_link_process`) : boucle complète sur tous les cours toutes les 5 min même quand rien n'a changé.
- `main.py:203` : polling du splash screen à 2 Hz via `ui.timer(0.5, ...)` — négligeable mais un callback événementiel serait plus propre.
- `notion/service.py:85` (`get_all_cours`) : pas de `page_size` explicite sur la pagination Notion.

---

## B. Code mort et inutilisé

### B.1 — Suppression sûre (0 référence, 0 test, confiance "Certain") — **FAIT**

Exécuté le 2 août 2026 : les 6 fichiers et 7 fonctions ci-dessous ont été supprimés après revérification manuelle (grep cross-repo, chaque symbole n'avait qu'un seul site — sa propre définition). Compilation + `ruff --select F401,F811,F821,F841` + suite complète re-vérifiés après coup : **955 tests passants, mêmes 8 échecs préexistants et sans rapport qu'avant** (routage IA, `test_ai_practice.py`/`test_ai_service.py`/`test_ai_tasks.py`). Non commité — laissé pour relecture.

| Fichier | Lignes | Constat |
|---|---|---|
| `frontend/components/ui_kit.py` | 212 | Design System v2 jamais adopté ; `dashboard/_reviews.py` a sa propre implémentation locale en doublon |
| `frontend/components/dashboard_card.py` | 283 | `render_review_card` n'existe que dans son propre docstring — un homonyme réel et utilisé vit dans `dashboard/_reviews.py:425,1052` |
| `frontend/components/qcm_result_card.py` | 150 | `QcmResultCard` jamais importée |
| `frontend/components/search_bar.py` | 75 | Supplantée par `item_search_palette.py` |
| `frontend/components/sortable_list.py` | 65 | `SortableList` sans site d'appel |
| `backend/core/utils/ics_helper.py` | 38 | Aucune fonctionnalité d'export .ics dans l'app |
| `backend/core/knowledge/models.py` — `CollegeStatus` | ~15 | Remplacée par `ItemState`, jamais nettoyée |
| `backend/core/externat/store.py` — `deactivate_all_stages` | ~10 | 0 appel |
| `backend/core/ai_qcm/lacunes.py` — `build_lacune_candidates` | ~20 | 0 appel |
| `backend/core/ai_qcm/service.py` — `get_inbox_count` | ~10 | 0 appel |
| `backend/core/network_capture/converters.py` — `_classify_session_errors`, `_build_weak_points_from_questions` | ~40 | 0 appel, y compris interne |
| `scripts/uness/url_scanner.py` — `_has_dfasm` | ~5 | Jumelle `_is_dfgsm` utilisée, celle-ci non |
| `backend/state/store.py:282` — `self.preferences.pop("ui_mode", None)` | 1 | Résidu mort de l'ancien flag classic/cockpit (grep confirmé : `ui_mode` n'existe plus nulle part ailleurs) |

**Total ≈ 870 (components) + ~150 (backend divers) ≈ 1000-1050 lignes**, suppression mécanique sans impact fonctionnel.

### B.2 — Décision produit à prendre avant suppression (fonctionnalités désactivées mais codées)

Ce ne sont **pas** des oublis de refactor comme les pages legacy — le code lui-même contient des commentaires explicites indiquant une désactivation *volontaire* :

- **`backend/core/network_capture/ednpro_sync.py`** (100 lignes) et **`hypocampus_sync.py`** (308 lignes) — jamais importés. `background.py:126-133` dit explicitement *"Capture EDN Pro — DÉSACTIVÉ (fetch manuel via bouton)"*, mais aucun bouton n'existe (`grep ednpro|hypocampus` sur `frontend/` : 0 résultat). `background.py:336` (`_fetch_ednpro_background`, elle-même jamais appelée) réimplémente la même logique en doublon.
- **`backend/core/ai_qcm/watcher.py`** (163 lignes) — jamais importé. `background.py:126-129` : *"Watcher AI QCM — DÉSACTIVÉ"* (l'auto-import créait des doublons, remplacé par un import 100% manuel via bouton).
- **`backend/core/anki/service.py`** (`AnkiSyncService`, `sync_fiches_edn`, 66 lignes) — entièrement testé (`tests/test_anki_mapping.py`) mais jamais appelé depuis `frontend/components/anki_review_session.py` ni ailleurs : sync du deck "Fiches EDN Notion" implémentée puis jamais câblée à l'UI.

**Question à trancher** : ces trois blocs représentent-ils du travail à reprendre (auto-capture EDN Pro/Hypocampus, sync Anki bidirectionnelle) ou des pistes abandonnées à supprimer proprement ? Sans réponse, je ne les touche pas.

### B.3 — Divers

Aucun TODO/FIXME/XXX/HACK trouvé dans `backend/`, `scripts/`, `frontend/components/` — pas de dette "en attente" non documentée ailleurs que ce qui précède.

---

## C. Indirection et complexité évitable

### C.1 — Imports différés sans justification technique (🟡 lisibilité, pas perf)

~290 imports `from X import Y` à l'intérieur de corps de fonctions dans `backend/`. Après traçage réel des chaînes d'import, la **grande majorité n'évite aucun cycle** :

- `backend/state/store.py` — 8 imports différés dans `preload_all_views()` (lignes 78, 222-223, 236-237, 336, 361, 369, 376-377, 462) : aucun des modules importés ne remonte vers `store.py`, même indirectement.
- `from backend.state.store import data_store` différé dans 8 fichiers indépendants (`reviews/consolidation.py`, `reviews/service.py`, `reviews/lacune_adapter.py`, `planning/service.py`, `search/service.py`, `externat/service.py`, `features/daily_routine.py`) — `store.py` n'importe aucun de ces modules : pas de cycle réel, habitude systématique.
- `reviews/mastery.py` importe `knowledge.service`/`knowledge.models`/`reviews.local_store` **deux fois** dans la même fonction `get_course_mastery` (lignes 114 et 204).
- `ai/gemini_client.py` importe `log_ai_call` **4 fois** dans le même fichier à des points d'appel différents.
- `local_store.py` : `import json` répété 15 fois sur 4440 lignes, jamais en tête de fichier — stdlib, zéro risque.

**Cas légitimes à ne pas toucher** : `backend/core/files.py:380` (commentaire explicite "lazy import — avoids circular at startup") et `reviews/consolidation.py:62` (cycle réel avec `knowledge/store.py`).

### C.2 — Échecs silencieux du préchargement jamais visibles côté UI

`preload_all_views()` (`store.py:306-494`) contient **6 blocs `try/except ... logger.warning("non bloquant")`** distincts (cache PDF, graphe sémantique, stage actif, index de recherche, snapshot hebdomadaire, auto-import PDF). Le panneau diagnostic existant (`uness_diagnostic_panel.py`) ne couvre que l'import UNESS — ces 6 échecs restent invisibles hors des logs. Un échec silencieux de `rebuild_semantic_graph` par exemple dégrade réellement une fonctionnalité (priorisation) sans qu'aucun signal n'atteigne l'utilisateur. Résilience du démarrage : bien. Absence totale de remontée : lacune.

### C.3 — Le calcul de maîtrise est la chaîne la plus opaque du dépôt

Contrairement à "valider une révision" ou "ajouter un QCM" (2 sauts propres, chaque étape ajoute une vraie logique — bon exemple d'architecture), **"calculer la maîtrise d'un item"** saute entre 4 modules (`knowledge.service`, `knowledge.models`, `reviews.local_store`, `knowledge.retention`) via des imports différés non justifiés (C.1). `retention.py` et `sm2.py` sont propres et purs isolément, mais `mastery.py` doit assembler manuellement l'`Evidence` avant d'appeler `retention.py` — impossible de suivre d'où vient un score sans ouvrir les 4 fichiers.

### C.4 — Le split page-shell / cockpit est mal placé pour 2 pages

`qcm_cockpit.py` importe 4 symboles privés depuis `qcm.py` (qui fait 1861 lignes — ce n'est pas un shell fin, c'est toujours l'implémentation complète). Même schéma sur `stats_cockpit.py` (6 symboles privés importés depuis `stats.py`, 775 lignes). Les helpers réellement partagés (`_compute_groups`, `_get_all_mastery_snapshots`, etc.) devraient vivre dans un module dédié plutôt que dans le fichier "legacy" — qui reste en réalité un fichier de première classe malgré son nom. `externat_cockpit.py`/`weak_points_cockpit.py` n'ont qu'un symbole chacun, moins problématique.

---

## D. Priorisation recommandée

1. **A.1 + A.2 + A.3** (cache mastery + verrou SQLite + rebuild UI) — le levier "fluidité" le plus rentable, à traiter en premier et avec des tests avant/après mesurables (temps de réponse sur "valider une révision").
2. **A.4** (préchargement démarrage) — deuxième gain le plus visible, sur le temps avant que l'app soit utilisable.
3. **B.1** — suppression mécanique sûre (~1000 lignes), même profil de risque que la purge des pages déjà faite : compiler + tester avant/après.
4. **B.2** — décision produit nécessaire (garder/réparer/supprimer EDN Pro, Hypocampus, watcher AI QCM, sync Anki) avant tout nettoyage de ce bloc.
5. **C.2** — faire remonter les 6 échecs silencieux du préchargement dans le panneau Diagnostic existant (déjà l'emplacement naturel).
6. **C.1, C.4** — nettoyage de confort (lisibilité), à faire au fil de l'eau, pas urgent.

---

## E. Rappel — audit de fiabilité déjà livré (non répété ici)

Voir `project_audit_aug2026.md` (mémoire) et l'artefact « Synapse — Audit & feuille de route » du 2 août : bug critique de perte des préférences après 12h (`store.py:248-331`), cache mastery jamais invalidé après validation (`reviews/service.py:268-281` — angle fiabilité, complémentaire du levier perf A.1 ci-dessus), absence de sauvegarde de `data/synapse_local.db`, sync Obsidian sans verrou (doublons possibles par hash de chemin), client Notion sans retry/backoff.
