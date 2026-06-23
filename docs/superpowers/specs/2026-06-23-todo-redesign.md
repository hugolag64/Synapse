# Spec — Refonte To Do / Suivi Quotidien

**Date** : 2026-06-23  
**Statut** : approuvé  
**Périmètre** : `frontend/pages/todo.py`, `frontend/theme.py`, nouveau modèle SQLite pour la routine

---

## 1. Objectif

Refaire la page To Do de Synapse pour qu'elle serve à la fois de **journal quotidien** (bilan passé) et de **planificateur** (organisation future). La page doit être instantanée à l'affichage, ergonomique, et cohérente avec le design `clinical-black.css` existant.

---

## 2. Navigation

### 2.1 Ajout dans la barre de nav
Ajouter `('To Do', '/todo')` dans `_NAV_ITEMS` de `frontend/theme.py`, entre `Planning` et `Externat`.

### 2.2 Navigation par date
- **Flèches ◀ ▶** : naviguer jour par jour
- **Label date central** cliquable : ouvre un `ui.date` picker natif NiceGUI pour sauter à une date lointaine
- **Boutons rapides** : `Hier` · `Auj.` · `Demain` — le bouton actif est mis en évidence

La date active est stockée dans un état local Python (`current_date`). Changer de date efface et recharge la zone de contenu.

---

## 3. En-tête sticky

Toujours visible en haut même en scrollant :

```
[◀]  Hier  Auj.  Demain  [Lundi 23 juin 2026 ▼]  [▶]
━━━━━━━━━━━━━━━━━━━━━━░░░░░░  6 / 9 · 67%
```

- Barre de progression fine (`h-1.5`) mise à jour en temps réel (optimistic)
- Compteur `X / Y · Z%` à droite de la barre
- Style : fond blanc/slate-900 semi-transparent avec `backdrop-blur`, bordure basse fine

---

## 4. Timeline verticale

La zone de contenu est une **colonne** avec 3 blocs séquentiels. Chaque bloc a un **marqueur latéral** (ligne verticale `w-1 rounded`) coloré sur sa gauche, et un titre de section en petites majuscules.

### 4.1 Bloc Routine 🔵 (marqueur bleu `sky-500`)

**Source** : SQLite local (`routine_checks` table). Pas d'appel réseau.

**Contenu fixe** (identique tous les jours) :
- ☐ Révision
- ☐ QCM
- ☐ Sport
- ☐ Musique
- ☐ Anki

**Comportement** :
- Chargement instantané depuis SQLite au rendu de la page
- L'état coché/décoché est persisté en SQLite par `(user_date, item_name)`
- Optimistic update : la checkbox se met à jour immédiatement, l'écriture SQLite est asynchrone
- Les items de routine sont **configurables dans les Paramètres** (ajout/suppression) — hors périmètre de cette spec, prévoir le schéma

**Schéma SQLite** :
```sql
CREATE TABLE IF NOT EXISTS routine_checks (
    date        TEXT NOT NULL,        -- 'YYYY-MM-DD'
    item_name   TEXT NOT NULL,
    checked     INTEGER DEFAULT 0,
    PRIMARY KEY (date, item_name)
);

CREATE TABLE IF NOT EXISTS routine_items (
    name        TEXT PRIMARY KEY,
    position    INTEGER NOT NULL,
    active      INTEGER DEFAULT 1
);
```

### 4.2 Bloc Ajouté 🟣 (marqueur violet `violet-500`)

**Source** : GCal (live) + Notion daily page (cache SQLite partiel).

**Contenu** :

**A. Cours à réviser** — liste des cours du jour (Collège GCal + révisions manuelles Notion)
- Chaque cours : icône 📘 + titre + badge source (GCal / Manuel)
- Bouton ✓ pour valider (optimistic : barré immédiatement, sync Notion en arrière-plan)
- Cours validés affichés barrés + icône `check_circle` verte

**B. Tâches libres** — les `dynamic_checkboxes` Notion actuelles
- Checkboxes texte libre, cochables
- Supprimables (icône ✕ au hover)

**C. Boutons d'ajout** (en bas du bloc) :
- `+ Cours` → ouvre un drawer/dialog avec le sélecteur de cours Collège (ITEM XXX) + date déjà pré-remplie avec la date affichée
- `+ Tâche` → champ texte inline qui apparaît sous les tâches existantes, validation par `Entrée` ou bouton ✓

**Skeleton UI** pendant le chargement GCal/Notion :
- 3 rectangles animés (`animate-pulse bg-slate-200 dark:bg-slate-700 rounded`) de hauteurs variables

### 4.3 Bloc Note du jour 🟡 (marqueur ambre `amber-500`)

- **Jour courant ou futur** : textarea expandable (2 lignes par défaut, grandit au focus). Bouton "Enregistrer" visible uniquement si du texte a été saisi. Sync vers Notion.
- **Jours passés** : note affichée en lecture seule avec style `italic text-slate-500`. Bouton "Modifier" discret apparaît au hover du bloc.
- Si aucune note : label placeholder `"Rien noté pour ce jour"` en italique grisé.

---

## 5. Performance & chargement

| Donnée | Stratégie |
|---|---|
| Routine (checkboxes fixes) | SQLite local — instantané, zéro latence |
| GCal cours du jour | Live, chargé en parallèle avec Notion |
| Notion daily page (tâches custom, note) | Live Notion — skeleton UI pendant le chargement, pas de cache (source de vérité unique) |
| Optimistic updates | Tous les toggles (routine + cours + tâches libres) |

**Ordre de rendu** :
1. Skeleton UI affiché immédiatement sur les 3 blocs
2. Routine chargée depuis SQLite → remplace son skeleton en < 50 ms
3. GCal + Notion daily page chargés en `asyncio.gather` → remplace le skeleton du bloc Ajouté et de la Note simultanément

---

## 6. UI/UX — Règles de style

- **Cohérence** : respecter `clinical-black.css`, polices Inter/Plus Jakarta Sans, couleurs `slate-*`
- **Marqueurs timeline** : `w-1 h-full rounded-full` avec les couleurs définies par bloc
- **Transitions** : `transition-all duration-200` sur les checkboxes, `duration-500` sur les animations de validation (cours barré + slide-out)
- **Dense** : `props('dense')` sur tous les inputs/checkboxes, padding réduit (`py-2 px-3`)
- **Dark mode** : toutes les couleurs ont leur variante `dark:`
- **Sticky header** : `position: sticky; top: 0; z-index: 10` + `backdrop-blur-sm bg-white/80 dark:bg-slate-900/80`
- **Pas de tabs** : page unique scrollable, les 3 blocs se suivent verticalement

---

## 7. Fichiers impactés

| Fichier | Changement |
|---|---|
| `frontend/theme.py` | Ajout `('To Do', '/todo')` dans `_NAV_ITEMS` + `_TITLE_TO_NAV` |
| `frontend/pages/todo.py` | Réécriture complète |
| `backend/core/reviews/local_store.py` | Ajout des tables `routine_checks` et `routine_items` dans `init_db()`, + fonctions CRUD dédiées. La DB existante `data/synapse_local.db` est réutilisée. |

> **Note** : il n'y a pas de nouveau fichier SQLite. Tout passe par la connexion existante dans `local_store.py`.

---

## 8. Hors périmètre

- Configuration des items de routine (Paramètres) — prévoir le schéma SQLite, UI reportée
- Notifications / rappels
- Vue hebdomadaire ou mensuelle
