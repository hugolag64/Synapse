# PDF Zéro-Friction — Plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** L'icône PDF sur chaque course card ouvre directement le PDF local dans le navigateur — sans dialog, sans saisie manuelle — grâce à une détection automatique au démarrage.

**Architecture:** Au démarrage (pendant `preload_all_views`), après le chargement des cours depuis Notion, un pass de détection automatique enrichit chaque cours sans `url_pdf` avec le chemin local trouvé par `FileService.find_pdf()`. Le résultat est persisté en SQLite pour éviter de rescanner à chaque lancement. L'UI n'affiche plus de dialog : icône verte si PDF trouvé, icône grisée avec tooltip sinon.

**Tech Stack:** Python + NiceGUI, FastAPI (`/pdf/{course_id}` déjà en place), SQLite (`data/synapse_local.db`), `FileService` existant avec scoring fuzzy.

## Global Constraints

- Ne jamais écraser un `url_pdf` déjà présent dans Notion (lien manuel = source de vérité supérieure)
- Ne jamais toucher à la route FastAPI `/pdf/{course_id}` ni à `_resolve_pdf_path()` — elles fonctionnent
- Le scan doit être non-bloquant (async) et ne pas retarder l'affichage de l'UI
- Seuil de confiance élevé (score > 50) pour éviter les faux positifs (mauvais PDF)
- Rétrocompatibilité : le lien manuel dans le menu ⋯ reste disponible pour les cas non détectés
- Pas de JS complexe — uniquement NiceGUI

---

## 1. Analyse de l'existant

### État actuel des données

| Champ | Source | Usage |
|---|---|---|
| `course.url_pdf` | Notion property `URL PDF COLLEGE` | `has_pdf` en context "college" |
| `course.url_pdf_ue` | Notion property `URL PDF UE` | `has_pdf` en context "ue" |

`has_pdf = bool(getattr(course, "url_pdf", None))` — si vide → dialog; si rempli → ouvre `/pdf/{course_id}`.

### Logique de recherche existante

`FileService.find_pdf(query, search_path, item_number)` dans `backend/core/files.py` :
- Score item number dans le nom de fichier : **+150 pts** (match), **+50 pts** (en début de nom)
- Score substring/mots : 50 pts / 25 pts/mot
- fuzzywuzzy token_set_ratio : jusqu'à 40 pts
- Seuil actuel : score > 5.0 → trop permissif pour la détection auto

### Répertoires configurés

- `settings.medicine_dir` → racine de tous les PDFs (ex: `G:\Mon Drive\Médecine\Médecine`)
- `settings.fac_dir` → PDFs fac/UE (context "ue")
- PDFs collège : `medicine_dir/Collèges/{nom_dossier_obsidian}/`
- Mapping Notion → dossier disque : `COLLEGE_MAPPING` dans `backend/core/obsidian/service.py`

### Point d'accrochage dans le preload

`backend/state/store.py`, méthode `preload_all_views()`, lignes ~270-280 : après `refresh()` (qui charge les cours), avant la construction des index.

---

## 2. Décisions d'architecture

### Stockage du cache PDF local

**SQLite** (`data/synapse_local.db`, géré par `backend/core/reviews/local_store.py`).

Nouvelle table :
```
pdf_local_cache (
    course_id   TEXT PRIMARY KEY,
    context     TEXT,          -- "college" ou "ue"
    pdf_path    TEXT,          -- chemin absolu local
    detected_at TEXT           -- ISO date de détection
)
```

Logique de résolution au démarrage (par ordre de priorité) :
1. `url_pdf` Notion non vide → utiliser tel quel (source de vérité)
2. Cache SQLite présent ET fichier toujours sur disque → utiliser le chemin caché
3. Aucun des deux → lancer `find_pdf()`, score > 50 → enregistrer en SQLite + setter sur `course.url_pdf`

### Quand déclencher la détection

Dans `preload_all_views()`, immédiatement après que les cours sont chargés (step 1), en **background task** (`asyncio.create_task`) pour ne pas bloquer l'affichage du splash screen. L'UI se rend avec ce qu'elle a au moment du render — les cours déjà en cache SQLite auront leur PDF dès le premier render; les nouveaux cours seront enrichis quelques secondes après (sans refresh visible, car les pages NiceGUI sont rendues après `is_preloaded = True`).

**Important** : positionner le scan AVANT `is_preloaded = True` pour que le premier render bénéficie du cache SQLite (scan rapide), même si le scan complet des nouveaux cours se termine après.

### Seuil de confiance

Score > **50** pour la détection automatique (vs > 5 pour la recherche manuelle). Justification :
- Item number exact dans le nom : déjà 150 pts → toujours accepté
- Titre seul sans item number : score ~20-40 pts → rejeté (trop risqué)
- En pratique, quasi tous les PDFs collèges contiennent le numéro d'item → détection très fiable

---

## 3. Étapes d'implémentation

### Étape 1 — Table SQLite `pdf_local_cache`

**Ce qu'on fait :**  
Ajouter la création de la table `pdf_local_cache` dans `local_store.py`, dans la fonction d'initialisation SQLite existante. Ajouter deux fonctions : `get_pdf_cache(course_id, context)` → `str | None` et `set_pdf_cache(course_id, context, pdf_path)`.

**Fichiers touchés :**
- `backend/core/reviews/local_store.py` — ajout de la table dans `_init_db()` + 2 fonctions CRUD

**Résultat attendu :**  
La table est créée automatiquement au démarrage si elle n'existe pas (migration transparente). Les deux fonctions sont importables depuis le reste du code.

**Point de validation :**  
Démarrer l'app, vérifier avec un client SQLite que la table `pdf_local_cache` existe dans `data/synapse_local.db`. Tester manuellement `set_pdf_cache` + `get_pdf_cache` dans un script Python.

---

### Étape 2 — Méthode `auto_detect_pdf()` dans `FileService`

**Ce qu'on fait :**  
Ajouter une méthode `async auto_detect_pdf(course, context="college") -> str | None` à `FileService` dans `backend/core/files.py`.

Logique interne :
1. Si `course.url_pdf` (ou `url_pdf_ue` selon context) est déjà rempli → retourner `None` (rien à faire)
2. Lire le cache SQLite via `local_store.get_pdf_cache(course.id, context)` → vérifier que le fichier existe encore → retourner le chemin si valide
3. Construire le `search_path` : pour context "college", importer `COLLEGE_MAPPING` depuis `obsidian/service.py`, résoudre `college_folder = COLLEGE_MAPPING.get(course.college[0], course.college[0])`, chemin = `os.path.join(settings.medicine_dir, "Collèges", college_folder)`. Pour context "ue" : `settings.fac_dir`.
4. Si `search_path` n'existe pas → retourner `None`
5. S'assurer que le cache FileService est peuplé pour ce path (appeler `await refresh_cache_async(search_path)` si absent de `pdf_caches`)
6. Appeler `find_pdf(course.title, search_path=search_path, item_number=course.item_number, limit=1)`
7. Si résultat et score (via `scored_matches[0][0]`) > 50 → écrire en SQLite, retourner le chemin
8. Sinon → retourner `None`

**Note sur l'accès au score :** `find_pdf()` retourne actuellement uniquement les chemins. Il faudra soit exposer le score (modifier `find_pdf` pour accepter un param `return_scores=True`), soit dupliquer le top-1 avec vérification de score dans `auto_detect_pdf`.

**Fichiers touchés :**
- `backend/core/files.py` — ajout de `auto_detect_pdf()`, possiblement ajout du param `min_score` à `find_pdf()`

**Résultat attendu :**  
Appeler `await file_service.auto_detect_pdf(un_cours)` retourne un chemin PDF si trouvé avec confiance, `None` sinon. La méthode est idempotente (appel multiple = même résultat).

**Point de validation :**  
Écrire un petit script test qui instancie un cours factice avec item_number + title + college, appelle `auto_detect_pdf`, vérifie que le chemin retourné pointe vers un fichier `.pdf` existant.

---

### Étape 3 — Intégration dans `preload_all_views()`

**Ce qu'on fait :**  
Dans `backend/state/store.py`, après le step 1 du preload (chargement des cours), appeler `auto_detect_pdf` pour chaque cours en background, puis set `course.url_pdf` si un chemin est trouvé.

Deux phases :

**Phase A (rapide, avant `is_preloaded = True`)** :  
Pour chaque cours sans `url_pdf`, appeler `local_store.get_pdf_cache(course.id, "college")` — si entrée SQLite valide → `course.url_pdf = f"file:///{path}"`. Cette phase utilise uniquement SQLite (pas de scan disque) et prend < 50ms même avec 367 cours.

**Phase B (lente, en background)** :  
Lancer un `asyncio.create_task` qui itère sur les cours sans `url_pdf` après la Phase A, appelle `file_service.auto_detect_pdf(course, "college")`, met à jour `course.url_pdf` en mémoire. Cette phase ne bloque pas l'UI ; elle se termine quelques secondes après le premier render (sans refresh visible, mais les pages suivantes bénéficieront des nouvelles valeurs).

**Fichiers touchés :**
- `backend/state/store.py` — ajout des Phases A et B dans `preload_all_views()`, imports de `local_store` et `file_service`

**Résultat attendu :**  
Au démarrage, les cours déjà en cache SQLite ont leur `url_pdf` défini dès le premier render. Les nouveaux cours sont enrichis silencieusement en arrière-plan.

**Point de validation :**  
Lancer l'app, ouvrir la page Collèges, vérifier que les icônes PDF sont vertes pour les cours dont le PDF a été trouvé lors d'un précédent démarrage. Vérifier dans les logs `INFO` que le scan background se déclenche et trouve des fichiers.

---

### Étape 4 — UX : suppression du dialog "Lier PDF" pour la détection

**Ce qu'on fait :**  
Dans `frontend/components/course_card.py`, modifier le bloc `else` (quand `has_pdf` est False) du bouton PDF :

- **Avant** : icône grisée → `on_click=lambda: open_link_pdf_unified(...)` (ouvre le dialog)
- **Après** : icône grisée, **pas de `on_click`**, tooltip "PDF non trouvé automatiquement"

Le button doit être rendu non-interactif (prop `disable` ou simplement sans `on_click` et cursor non-pointer).

Dans `frontend/components/course_quick_actions.py`, même modification pour le bouton PDF dans `CourseQuickActions` (context "college" et "ue").

**Le dialog `open_link_pdf_unified` reste accessible** uniquement via le menu ⋯ (entrée "Lier un PDF manuellement…") pour permettre la liaison manuelle dans les cas non détectés. Cette entrée existe déjà dans le menu compact/micro de `CourseQuickActions`.

**Fichiers touchés :**
- `frontend/components/course_card.py` — lignes 166-174 (bloc `else` du bouton PDF)
- `frontend/components/course_quick_actions.py` — ligne ~882-888 (bouton PDF dans `CourseQuickActions`)

**Résultat attendu :**
- Cours avec PDF : icône verte, clic → ouvre le PDF dans un onglet
- Cours sans PDF : icône grisée, pas de clic, tooltip "PDF non trouvé"
- Via le menu ⋯ : "Lier un PDF manuellement…" → ouvre `open_link_pdf_unified` (dialog existant conservé)

**Point de validation :**  
Naviguer sur la page Collèges, vérifier visuellement les deux états (vert/grisé). Vérifier qu'un clic sur une icône grisée ne fait rien. Vérifier que le menu ⋯ propose bien "Lier un PDF manuellement" pour les cours sans PDF.

---

### Étape 5 — Nettoyage du cache périmé (bonus, optionnel)

**Ce qu'on fait :**  
Dans `local_store.py`, ajouter une fonction `cleanup_pdf_cache()` qui supprime les entrées dont le fichier n'existe plus sur disque. Appeler cette fonction une fois par démarrage (dans la Phase A du preload, après avoir appliqué les chemins depuis SQLite).

**Fichiers touchés :**
- `backend/core/reviews/local_store.py` — ajout de `cleanup_pdf_cache()`
- `backend/state/store.py` — appel dans la Phase A

**Résultat attendu :**  
Si un PDF est déplacé ou renommé, l'entrée SQLite est supprimée au prochain démarrage, et le cours repasse en état "non trouvé" (icône grisée) en attendant un re-scan.

**Point de validation :**  
Déplacer manuellement un PDF lié, redémarrer l'app, vérifier que l'icône repasse en grisé et que l'entrée a disparu de `pdf_local_cache`.

---

## 4. Fichiers à modifier — récapitulatif

| Fichier | Nature de la modification |
|---|---|
| `backend/core/reviews/local_store.py` | +table `pdf_local_cache`, +`get_pdf_cache()`, +`set_pdf_cache()`, +`cleanup_pdf_cache()` |
| `backend/core/files.py` | +`auto_detect_pdf()`, ajout param `min_score` à `find_pdf()` |
| `backend/state/store.py` | Phase A (SQLite cache) + Phase B (scan background) dans `preload_all_views()` |
| `frontend/components/course_card.py` | Bouton PDF "sans PDF" → icône passive, tooltip |
| `frontend/components/course_quick_actions.py` | Idem pour `CourseQuickActions` |

**Fichiers NON touchés :**
- `main.py` — route `/pdf/{course_id}` et `_resolve_pdf_path()` inchangées
- `backend/core/obsidian/service.py` — `COLLEGE_MAPPING` importé mais non modifié
- `backend/core/notion/models.py` — champs `url_pdf` inchangés

---

## 5. Risques

| Risque | Probabilité | Mitigation |
|---|---|---|
| **Faux positif** : mauvais PDF détecté (ex: PDF d'un autre item dans le même dossier) | Faible si item_number présent (score 200 pts) | Seuil > 50 ; item_number quasi toujours présent |
| **Performance** : scan de 367 dossiers au 1er démarrage (cache vide) | Moyen (~5-15s total) | Phase B en background ; splash screen masque l'attente |
| **Stale cache** : fichier déplacé/renommé → chemin SQLite invalide | Faible | `cleanup_pdf_cache()` au démarrage (étape 5) |
| **Dossier introuvable** : `medicine_dir` non configuré ou chemin erroné | Faible | Guard `if not os.path.exists(search_path): return None` |
| **Collision lien manuel** : l'auto-détection écrase un lien Notion existant | Zero (si garde implémentée) | Vérifier `url_pdf` avant tout — si rempli, skip complet |
| **Émoji dans les noms de dossiers** : path join échoue sur Windows | Très faible | Testé dans le code Obsidian existant (même mapping) |
| **Race condition** : Phase B modifie `course.url_pdf` pendant qu'une page est en train de se rendre | Très faible | NiceGUI est single-threaded par client ; les pages sont statiques après render |

---

## 6. Ce qu'il ne faut PAS faire

- Ne pas déclencher la détection "à la demande" quand l'utilisateur clique sur l'icône — la latence serait perceptible
- Ne pas écrire le résultat dans Notion — trop coûteux (API call par cours, rate-limit)
- Ne pas baisser le seuil de confiance sous 50 pour tenter d'augmenter le taux de détection — mieux vaut une icône grisée qu'un mauvais PDF
- Ne pas supprimer `open_link_pdf_unified` — il reste utile pour la liaison manuelle via le menu ⋯
