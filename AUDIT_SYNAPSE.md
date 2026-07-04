# AUDIT SYNAPSE — Rapport complet
_Généré le 2026-06-18 — basé sur lecture directe du code, zéro spéculation_

---

## Table des matières

1. [Executive Summary](#1-executive-summary)
2. [Cartographie des fonctionnalités](#2-cartographie-des-fonctionnalités)
3. [Points de friction architecturaux](#3-points-de-friction-architecturaux)
4. [Audit UX](#4-audit-ux)
5. [Dette technique](#5-dette-technique)
6. [Vision produit — Panel d'experts](#6-vision-produit--panel-dexperts)
7. [Nouvelles features proposées](#7-nouvelles-features-proposées)
8. [Features à déprécier ou fusionner](#8-features-à-déprécier-ou-fusionner)
9. [Nouvelle architecture de navigation proposée](#9-nouvelle-architecture-de-navigation-proposée)
10. [Plan d'action priorisé](#10-plan-daction-priorisé)
11. [Métriques de succès](#11-métriques-de-succès)

---

## 1. Executive Summary

Synapse a un **moteur de révision solide** (SM-2 + mastery scoring + virtualisation) et une **UX dashboard raisonnablement bien pensée** (hero card, mode focus, validation 1-clic). Le problème n'est pas la qualité du code central : c'est l'**accumulation non priorisée de features** qui dilue l'expérience sans l'enrichir.

Ce qui doit changer en priorité : **(1)** corriger deux bugs silencieux critiques dans `stats.py` et `local_store.py` qui cassent des features sans erreur visible ; **(2)** supprimer ou fusionner 4 pages redondantes (Bilan orpheline, Todo déconnectée, Semestres doublon, Planning chevauchant le Dashboard) ; **(3)** alléger la sidebar de 12 items à 7 en regroupant logiquement.

La **priorité absolue** : le Dashboard doit rester LA page unique de la journée. Tout ce qui ne sert pas ce flow quotidien est du bruit à éliminer.

---

## 2. Cartographie des fonctionnalités

| Feature | Page/Fichier | Fréquence d'usage | Valeur utilisateur | Verdict |
|---|---|---|---|---|
| Révisions J3/J7/J14/J30 | `dashboard.py` | Quotidien | ⭐⭐⭐⭐⭐ Cœur | ✅ Garder |
| Hero card + mode focus | `dashboard.py:296,487` | Quotidien | ⭐⭐⭐⭐⭐ | ✅ Garder |
| Validation 1-clic ✓ Fait | `dashboard.py:1005` | Quotidien | ⭐⭐⭐⭐⭐ | ✅ Garder |
| Pomodoro (col gauche) | `components/pomodoro.py` | Quotidien | ⭐⭐⭐⭐ | ✅ Garder |
| Smart Banner | `dashboard.py:742` | Quotidien | ⭐⭐⭐⭐ | ✅ Garder |
| Lacunes (weak_points) | `weak_points.py` | Plusieurs fois/semaine | ⭐⭐⭐⭐⭐ | ✅ Garder |
| Lacune du Jour (sidebar dashboard) | `dashboard.py:380` | Quotidien | ⭐⭐⭐⭐ | ✅ Garder |
| Streak badge 🔥 | `theme.py:192` | Quotidien | ⭐⭐⭐ Motivation | ✅ Garder |
| Countdown J-X EDN | `theme.py:213` | Quotidien | ⭐⭐⭐⭐ | ✅ Garder |
| Collèges (parcourir cours) | `colleges.py` | Quelques fois/semaine | ⭐⭐⭐⭐ | ✅ Garder |
| QCM (saisie scores) | `qcm.py` | Quelques fois/semaine | ⭐⭐⭐⭐ | ✅ Garder |
| Externat (stage boost) | `externat.py` | Variable | ⭐⭐⭐ | ✅ Garder |
| Command Palette Ctrl+K | `command_palette.py` | Quotidien | ⭐⭐⭐⭐ | ✅ Garder |
| Ma Progression (Stats) | `stats.py` | Quelques fois/semaine | ⭐⭐⭐⭐ | ✅ Garder (fix bug) |
| Planning | `planning.py` | Rare | ⭐⭐ Overlap Dashboard | 🔄 Fusionner |
| Tab Semaine Dashboard | `dashboard.py:623` | Quotidien | ⭐⭐⭐ | ✅ Garder |
| Bilan semaine | `bilan.py` | Inaccessible | ⭐⭐⭐ (potentiel) | ❌ Orphelin → fusionner dans Stats |
| To Do (Suivi Quotidien Notion) | `todo.py` | Rare | ⭐ Déconnecté | ❌ Supprimer ou isoler |
| Semestres | `semestres.py` | Rare | ⭐ Doublon Collèges | ❌ Supprimer |
| Santé | `health.py` | Rare | ⭐ Unclear | 🔄 Déplacer dans Paramètres |
| Daily Routine Notion (J0/J1/J2) | `daily_routine.py` | Startup | ⭐⭐ Utilitaire silencieux | 🟡 Conserver, réduire les appels |
| Diagnostic du lundi | `dashboard.py:219` | 1×/semaine | ⭐⭐⭐⭐ | ✅ Garder |
| Graphe sémantique | `graph/builder.py` | Startup | ⭐⭐ Invisible utilisateur | 🟡 Garder (backend) |

---

## 3. Points de friction architecturaux

### 3.1 Cohabitation SM-2 + intervalles fixes Notion

**Le système mixte est fonctionnel mais les deux sources de dates peuvent diverger.** `ReviewService._get_notion_date()` prend la date Notion si elle existe, sinon `get_sm2_effective_date()`, sinon `date_ref + offset`. La logique de fallback est claire. Le risque : si Notion a une date J7 = 2026-06-20 mais que SM-2 calcule 2026-06-25 après une révision difficile, c'est la date Notion qui gagne. L'utilisateur voit la date Notion comme "vérité" mais SM-2 essaie d'ajuster — conflit silencieux, aucune trace visible dans l'UI.

**Recommandation** : afficher dans la carte révision quelle source a été utilisée (Notion / SM-2 / calcul fixe) via un tooltip discret.

### 3.2 Cache JSON + SQLite = deux sources de vérité

`DataStore` charge depuis un `data_cache.json` (courses/preferences) et SQLite (historique/lacunes). Si le JSON est corrompu ou expiré (>12h), un rechargement Notion se déclenche mais SQLite persiste. En cas de changement de cours côté Notion (suppression, renommage), la DB SQLite peut garder des `course_id` fantômes dans `review_history`, `study_sessions`, `weak_points`. Aucun mécanisme de nettoyage de ces données orphelines.

**Risque** : faible à court terme (app mono-utilisateur), mais les stats de progression peuvent inclure des cours supprimés.

### 3.3 Démarrage Notion-dépendant

Chaque démarrage (sans cache valide) déclenche : 1 appel `get_all_ues_map()` + 1 appel `get_all_cours()` + 1 `get_today_task()` + 1 `get_events_for_day()` + 1 `get_streak_counts()` + 2 appels révisions + 3 appels `daily_routine` (création J0/J1/J2). **Total : ~10 appels Notion en séquence partielle à chaque démarrage sans cache.** Avec cache valide (<12h), ce nombre tombe à ~6 (dashboard only). Le splash screen avec progress bar est bien géré, mais si Notion est lent ou offline, l'app reste bloquée jusqu'au timeout de 15s.

**Recommandation** : ajouter un mode "offline graceful" — charger depuis le cache même expiré si Notion échoue, avec un badge d'avertissement.

### 3.4 daily_routine.py : 3 appels Notion à chaque démarrage

`run_daily_routine()` crée ou vérifie les tâches Notion pour J+0, J+1, J+2 à chaque lancement. Cette routine est utile mais coûteuse. Elle inclut aussi une boucle de réparation de titres corrompus (`"Ã©"` detection) qui est un workaround pour un bug d'encodage résolu ailleurs.

**Recommandation** : persister la date de la dernière exécution en préférence et ne pas ré-exécuter si déjà fait aujourd'hui.

---

## 4. Audit UX

### 4.1 Problèmes UX critiques

**C1 — Bannière surchargée (dashboard.py:77-184)**

Au peak, la bannière du dashboard affiche simultanément : badge rouge "N urgentes" (gros chiffre) + badge bleu "N prévues aujourd'hui" + badge gris "~Xh estimé" + badge vert "N faites ✓" + badge indigo "objectif" + badge slate "🔥 cette semaine" + badge rouge "lacunes critiques" + badge amber "à revoir" + badge amber "Charge lourde" + badge vert "Externat". **C'est jusqu'à 10 éléments d'information simultanés avant même de voir une carte de révision.**

L'utilisateur qui ouvre l'app le matin doit scanner 10 badges avant de savoir quoi faire. C'est l'opposé du "one next action" qu'il devrait voir en premier.

→ **Fix** : garder uniquement 3 éléments primaires (N urgentes · N aujourd'hui · temps estimé). Déplacer les lacunes/charge/semaine dans un panneau secondaire rétractable ou dans la page Stats.

**C2 — Sidebar avec 12 items + 8 mini progress bars**

La sidebar (`theme.py:330-376`) contient 12 liens + une boucle qui rend des barres de progression pour jusqu'à 8 collèges entre les liens "Collèges" et "Semestres". Ces micro-barres sont visuellement lourdes dans un élément de navigation.

→ **Fix** : supprimer les micro-barres de la sidebar (elles doublonnent la page Collèges). Réduire à 7 items max.

**C3 — Page Planning redondante avec tab Semaine**

Le Dashboard a un onglet "Semaine" (`dashboard.py:623`) qui liste exactement les mêmes révisions que la page `/planning`. De plus, le dashboard affiche un bouton "📅 Voir le planning" (`dashboard.py:206`) qui pointe vers cette page. La Planning page ajoute l'export Google Calendar mais cette feature est peu visible et peu utilisée quotidiennement.

### 4.2 Problèmes UX modérés

**M1 — Validation avec feedback détaillé : trop d'étapes**

Le menu "tune" ouvre un menu avec 5 emojis de confiance + "Détailler…". Bien pensé, mais le "Détailler…" ouvre une dialog supplémentaire. 3 niveaux d'interaction (bouton → menu → dialog) pour une action fréquente.

**M2 — Absence de page d'accueil "vide"**

Si l'utilisateur n'a aucune révision du jour (vacances, tout est fait), l'état vide du dashboard est `"Rien à faire aujourd'hui — profites-en pour avancer en avance ✓"` en texte d'une ligne. Pas de CTA visible pour aller parcourir les cours, noter une lacune, ou consulter sa progression.

**M3 — QCM et Lacunes dans la sidebar mais rarement liés**

Un utilisateur fait un QCM → il peut noter son score dans `/qcm`, et créer une lacune dans `/lacunes`. Ces deux actions sont déconnectées : il n'y a pas de flux "j'ai raté ce QCM, créer une lacune directement depuis le résultat".

**M4 — To Do page déconnectée du flow**

La page `/todo` affiche le "Suivi Quotidien Notion" (table Daily Follow-Up) + "Cours à réviser" (qui redouble le Dashboard). Elle n'est pas liée au système de révision locale. C'est une page Notion-native dans une app hybride.

### 4.3 Quick wins (< 1h chacun)

- [ ] **QW1** — Réduire la bannière dashboard à 3 badges primaires, déplacer lacunes/semaine dans un détail repliable
- [ ] **QW2** — Supprimer les micro-progress bars de la sidebar (8 lignes à retirer dans `theme.py:341-367`)
- [ ] **QW3** — Supprimer le lien "Semestres" de la sidebar (page redondante avec Collèges)
- [ ] **QW4** — Ajouter un CTA "Voir ma progression →" dans l'état vide du dashboard
- [ ] **QW5** — Corriger le bug silencieux dans `stats.py:82` (voir section 5)
- [ ] **QW6** — Supprimer les fonctions dupliquées dans `local_store.py` (4 lignes de def à supprimer)
- [ ] **QW7** — Marquer `resolve_weak_point()` (statut anglais) comme deprecated et l'aligner sur `'résolue'`

### 4.4 Analyse de la navigation actuelle

```
SIDEBAR ACTUELLE (12 items + bruit)
────────────────────────────────────
RÉVISION
  [dashboard]   Tableau de Bord        ✅ core
  [trending_up] Ma Progression         ✅ core
  [event_note]  Planning               ⚠ overlap Dashboard tab
  [checklist]   To Do                  ❌ déconnecté

CONTENU
  [business]    Collèges               ✅ core
  ████░░ Collège A   23%               ← bruit sidebar
  █░░░░░ Collège B    8%               ← bruit sidebar
  ████████ Collège C 78%               ← bruit sidebar
  [...jusqu'à 8 barres...]
  [school]      Semestres              ❌ doublon Collèges
  [quiz]        QCM                    ✅ valeur
  [report_problem] Lacunes             ✅ core

OUTILS
  [local_hospital] Externat            ✅ contextuel
  [settings]    Paramètres             ✅ utilitaire
  [monitor_heart] Santé                ❓ unclear

  ──────
  EDN QCM Pro ↗                        ✅ lien utile
```

---

## 5. Dette technique

| Fichier | Problème | Sévérité | Recommandation |
|---|---|---|---|
| `stats.py:82` | `get_course_mastery(course, sessions, postpone_map...)` — arguments positionnels incorrects. `sessions` (list) est passé comme `context` (str), `postpone_count` (int) comme `sessions` (list). L'erreur est swallowed par `except Exception: continue`. → Le bandeau "cours fragiles" manque tous les cours ayant des reports. | 🔴 Critique | Remplacer par `get_course_mastery(course, context="college", sessions=sessions, total_postpone=postpone_map.get(course.id, 0))` |
| `local_store.py:1305 et 1654` | `get_qcm_last_scores_by_course()` définie DEUX fois. La v1 (1305) retourne `{trend, trend_color, platform, last_score, last_raw}`. La v2 (1654) retourne `{last_score, last_raw, last_date}`. Python utilise la v2 (dernière). Les champs `trend` et `trend_color` calculés en v1 sont silencieusement perdus. | 🔴 Critique | Supprimer la définition à ligne 1654, conserver la v1 complète à 1305 |
| `local_store.py:1351 et 1679` | `get_active_lacunes_count_by_course()` définie deux fois. Différence mineure (filtre NULL sur course_id). | 🟡 Modéré | Supprimer la définition à ligne 1679, garder la v1 à 1351 (filtre plus robuste) |
| `local_store.py:860` | `resolve_weak_point()` insère `status='resolved'` (anglais) alors que toute la logique utilise `'résolue'` (français). La migration corrige à posteriori mais la fonction continue de créer des incohérences. | 🟡 Modéré | Remplacer `'resolved'` par `'résolue'` dans `resolve_weak_point()` |
| `bilan.py` | Page complète (150 lignes) sans route dans `main.py` et sans lien sidebar. Totalement inaccessible. Accède de plus à `local_store._conn()` directement (API privée à ne pas exposer). | 🟡 Modéré | Supprimer ou intégrer dans `stats.py` |
| `bilan.py:57` | Accès direct à `local_store._conn()` — bypass de l'API publique | 🟡 Modéré | Créer une fonction publique `get_week_stats()` dans `local_store` |
| `dashboard.py` | 1924 lignes dans un seul fichier. `_rebuild_all()` contient ~200 lignes inline de logique UI + business. | 🟡 Modéré | Extraire `_render_review_card`, `_render_task_row`, `_rebuild_week`, `_update_banner` dans `components/review_list.py` |
| `local_store.py` | 1808 lignes. Tout le SQL + migrations + business logic dans un seul module. | 🟡 Modéré | Pas urgent (app mono-user), mais à terme : séparer `queries.py` / `migrations.py` |
| `store.py:143` | `mark_review_done()` marqué `DEPRECATED` mais toujours présente et appelée potentiellement par code externe. La migration SQLite est faite. | 🟢 Mineur | Supprimer la méthode (la migration JSON→SQLite est terminée) |
| `daily_routine.py:121` | Détection de `"Ã©"` dans les titres Notion — workaround d'encodage qui indique un bug résolu ailleurs mais dont le code reste. | 🟢 Mineur | Supprimer la logique de repair (ligne 121-128) si le bug d'encodage est résolu |
| `theme.py` | Injection de ~130 lignes de JavaScript et CSS dans chaque rendu de page via `ui.add_head_html()`. Rechargé à chaque navigation SPA. | 🟢 Mineur | Déplacer dans `/static/clinical-black.css` et un fichier JS séparé |

### 5.1 Risques de fiabilité

**Risque 1 — Bug stats.py silencieux (🔴)**
Le bandeau "cours fragiles" de la page `/stats` appelle `get_course_mastery` avec des arguments inversés. L'erreur est swallowed ligne 83 (`except Exception: continue`). Résultat visible : le bandeau fragile affiche potentiellement 0 cours ou uniquement des cours sans reports, sans aucun message d'erreur. L'utilisateur pense que tout va bien alors que la détection est cassée.

**Risque 2 — Fonctions dupliquées (🔴)**
Les deux définitions de `get_qcm_last_scores_by_course()` créent un comportement différent selon l'ordre d'import. La v1 (ligne 1305) est la version riche utilisée dans la documentation/design, mais c'est la v2 (ligne 1654) qui s'exécute réellement. Le dashboard appelle cette fonction pour afficher les badges QCM sur les cartes révision — les champs `trend_color` et `platform` ne seront jamais remplis.

**Risque 3 — Désync Notion/SQLite sur course_id**
Si un cours est supprimé dans Notion et que le cache JSON expire, les `course_id` fantômes persistent dans `review_history`, `study_sessions`, `weak_points`. `get_course_mastery()` sera appelé avec un cours qui n'existe plus dans `data_store.cours`. Les stats agrégées incluront ces "fantômes". Risque faible à court terme mais peut créer de la confusion sur les compteurs.

**Risque 4 — `preload_all_views()` ne gère pas le rechargement partiel**
Si `get_all_cours()` réussit mais `get_today_task()` timeout (15s), `today_task` reste `None` et le dashboard s'affiche sans révisions Notion. L'utilisateur voit un dashboard vide qui ressemble à "pas de révisions" mais c'est en fait une erreur réseau. Le message `"Prêt (avec erreurs)"` est trop discret.

---

## 6. Vision produit — Panel d'experts

### 6.1 Perspective Étudiant en médecine

**Ce qui me fait vraiment gagner du temps :**
1. Le "✓ Fait" en 1 clic est parfait — ne pas le toucher. La confiance 1-5 avec emojis est bien.
2. Je veux savoir en 3 secondes ce que je dois faire aujourd'hui. La bannière avec 10 badges me demande 30 secondes de parsing.
3. Les lacunes sont ma vraie valeur ajoutée — c'est là où je perds des points en QCM. Je veux les voir liées directement à mes révisions, pas dans une page séparée.

**Ce qui me frustre :**
- La page Planning fait la même chose que l'onglet Semaine du Dashboard. Je navigue pour rien.
- La page Santé : je ne sais pas ce que c'est censé faire.
- La page Semestres : doublon parfait de Collèges mais trié différemment. Inutile.
- La page Bilan est inaccessible — j'ai découvert en lisant le code qu'elle existe mais je n'y ai jamais accédé.

### 6.2 Perspective Product Designer

**3 changements les plus importants :**
1. **Focus unique** — La première chose visible doit être la carte "Priorité maintenant" (hero card) avec 1 action claire. Tout le reste est secondaire.
2. **Sidebar minimale** — 7 liens max, 0 widget dans la nav. La nav doit naviguer, pas informer.
3. **Fusionner Stats + Bilan** — Une seule page "Ma Progression" avec : vue semaine (objectifs) + timeline activité + cours fragiles. Trois onglets, zéro overlap.

**Ce qui est déjà bien (ne pas casser) :**
- La hero card "Priorité maintenant" est exactement le bon pattern.
- Le Mode Focus plein écran est excellent pour les sessions actives.
- La Command Palette Ctrl+K est une fonctionnalité pro-tier bien intégrée.
- Le streak badge dans le header est subtil et motivant.

### 6.3 Perspective Architecte

**3 changements les plus importants :**
1. **Corriger les bugs silencieux** — les deux bugs de `stats.py` et `local_store.py` duplication sont prioritaires car ils dégradent silencieusement des features existantes.
2. **dashboard.py doit être découpé** — 1924 lignes est trop. Extraire les composants review card, bannière, sidebar agenda dans des fichiers séparés pour permettre l'évolution sans régression.
3. **Supprimer le code mort** — `bilan.py` (page orpheline), `mark_review_done()` (deprecated), repair encodage Notion dans `daily_routine.py` — ces éléments alourdissent la base sans valeur.

**Ce qui est architecturalement solide :**
- `ReviewService` avec cache par (context, date) est propre.
- `local_store.get_all_review_data()` batch en 4 requêtes est bien pensé pour les perfs.
- Les migrations SQLite idempotentes sont une bonne pratique.
- La séparation Notion (source de vérité cours) / SQLite (historique révisions) est la bonne architecture.

### 6.4 Consensus & recommandations

**LA feature centrale visible dès l'ouverture** : la **Hero Card "Priorité maintenant"** avec le cours le plus urgent, la next action recommandée, et le bouton ✓. Elle existe déjà (`dashboard.py:1331`), il faut juste la rendre plus prominente et décharger tout ce qui la précède.

**Recommandations consensus (priorisées) :**
1. Fix bugs silencieux stats.py + local_store.py — 30 min de code, impact immédiat
2. Réduire la bannière de 10 badges à 3
3. Supprimer/fusionner : Bilan (orphelin), Semestres (doublon), Todo (déconnecté)
4. Sidebar : 7 items maximum, sans widgets
5. Planning → fusionner dans un onglet enrichi du Dashboard
6. Découper dashboard.py en composants

---

## 7. Nouvelles features proposées

| Feature | Description | Effort | Impact utilisateur |
|---|---|---|---|
| **Lacune depuis carte révision** | Lors de la validation d'une révision, un bouton "⚠ Noter une lacune" dans le menu feedback crée une lacune liée au cours sans quitter le Dashboard | 🟢 Faible (2h) | ⭐⭐⭐⭐⭐ — ferme la boucle révision→lacune dans 1 geste |
| **Résumé hebdomadaire fusionné** | Fusionner Bilan + Stats en une page unique "Ma Progression" avec 3 onglets : Activité / Cours fragiles / Objectifs semaine | 🟡 Moyen (4h) | ⭐⭐⭐⭐ — supprime l'overlap et améliore la lisibilité |
| **Notification matinale enrichie** | Améliorer `daily_routine._send_morning_notification()` : afficher le cours le plus urgent nommément (existe déjà mais n'affiche que les compteurs) | 🟢 Faible (1h) | ⭐⭐⭐ — rappel quotidien actionnable |

---

## 8. Features à déprécier ou fusionner

| Feature | Raison | Action recommandée |
|---|---|---|
| **Page Bilan** (`bilan.py`) | Orpheline — aucune route, aucun lien sidebar. Inaccessible à l'utilisateur. | Supprimer le fichier ou intégrer les objectifs hebdomadaires dans `stats.py` sous un onglet "Semaine" |
| **Page Semestres** (`semestres.py`) | Affiche les cours triés par semestre — doublon exact de Collèges trié différemment. Valeur marginale. | Supprimer la page, ajouter un tri "par semestre" dans la page Collèges comme option de vue |
| **Page To Do** (`todo.py`) | Connectée à la DB Notion "Daily Follow-Up" (gestion tâches quotidiennes Notion), déconnectée du système de révision. L'onglet "Cours à réviser" doublonne le Dashboard. | Supprimer — le Daily Follow-Up Notion est auto-géré par `daily_routine.py`. Si besoin, accéder depuis Notion directement |
| **Micro-progress bars sidebar** (`theme.py:341-367`) | Widgets de données dans un élément de navigation — visuellement lourds, rechargés à chaque navigation, doublonnent la page Collèges | Supprimer les 26 lignes concernées |

---

## 9. Nouvelle architecture de navigation proposée

```
SIDEBAR PROPOSÉE (7 items, 0 widget)
──────────────────────────────────────
RÉVISION
  [dashboard]     Tableau de Bord       ← page principale, ouverte au démarrage
  [trending_up]   Ma Progression        ← Stats + Bilan fusionnés

CONTENU
  [business]      Collèges              ← avec tri semestre/collège au choix
  [quiz]          QCM
  [report_problem] Lacunes

OUTILS
  [local_hospital] Externat
  [settings]       Paramètres           ← inclut Santé + config

──────
  EDN QCM Pro ↗                         ← lien externe, garder
```

**Pages supprimées** : Planning (→ onglet Dashboard), Semestres (→ option Collèges), To Do (→ suppression), Santé (→ intégrer Paramètres), Bilan (→ fusionner Stats).

**Pages conservées avec route** : `/` (Dashboard), `/stats` (Ma Progression fusionnée), `/colleges`, `/qcm`, `/lacunes`, `/externat`, `/settings`.

---

## 10. Plan d'action priorisé

### Phase 1 — Corrections de bugs & nettoyage (< 1 semaine)

- [ ] **[BUG🔴]** `stats.py:82` — corriger les args de `get_course_mastery()` : `get_course_mastery(course, context="college", sessions=sessions, total_postpone=postpone_map.get(course.id, 0))`
- [ ] **[BUG🔴]** `local_store.py` — supprimer les définitions dupliquées en lignes 1654 (`get_qcm_last_scores_by_course`) et 1679 (`get_active_lacunes_count_by_course`)
- [ ] **[BUG🟡]** `local_store.py:860` — remplacer `status='resolved'` par `status='résolue'` dans `resolve_weak_point()`
- [ ] **[NETTOYAGE]** Supprimer les micro-progress bars de la sidebar (`theme.py:341-367`)
- [ ] **[NETTOYAGE]** Supprimer le lien "Semestres" de la sidebar + supprimer la page ou la garder accessible par URL directe
- [ ] **[NETTOYAGE]** Supprimer le lien "To Do" de la sidebar
- [ ] **[NETTOYAGE]** Supprimer le lien "Santé" de la sidebar, déplacer son contenu dans Paramètres
- [ ] **[NETTOYAGE]** Supprimer `bilan.py` ou créer une route `/bilan` pour le rendre accessible
- [ ] **[PERF]** `daily_routine.py` — ne pas re-exécuter si déjà fait aujourd'hui (vérif `_notif_date` existe déjà, l'étendre à la routine complète)

### Phase 2 — Refonte UX Dashboard & Navigation (1-2 semaines)

- [ ] Réduire la bannière à 3 badges primaires (urgentes · aujourd'hui · temps). Mettre le reste (lacunes, semaine, charge) dans un `ui.expansion` "Détail" replié par défaut
- [ ] Déplacer la Hero Card "Priorité maintenant" en position 1 visible dès l'ouverture (avant les badges ou en remplacement de la bannière)
- [ ] Ajouter un CTA dans les états vides du Dashboard (quand 0 urgentes + 0 aujourd'hui)
- [ ] Ajouter bouton "⚠ Lacune" dans le menu feedback des cartes révision → création directe liée au cours
- [ ] Fusionner `stats.py` + `bilan.py` en une page "Ma Progression" avec onglets Activité / Fragiles / Semaine
- [ ] Mettre à jour la sidebar selon la nouvelle architecture proposée (section 9)

### Phase 3 — Qualité du code (continu)

- [ ] Extraire de `dashboard.py` (1924 lignes) les composants : `_render_review_card` → `components/review_card.py`, `_update_banner` + `_render_monday_diagnostic` → `components/dashboard_banner.py`
- [ ] Créer `local_store/queries.py` et `local_store/migrations.py` pour décharger le module de 1808 lignes
- [ ] Supprimer `DataStore.mark_review_done()` (DEPRECATED, migration terminée)
- [ ] Supprimer la logique de réparation encodage dans `daily_routine.py:121-128`
- [ ] Déplacer le CSS/JS inline de `theme.py` dans des fichiers statiques (`/static/synapse.js`, `/static/synapse.css`)
- [ ] Ajouter un mode "offline graceful" : si Notion timeout, charger depuis cache expiré avec badge avertissement

---

## 11. Métriques de succès

Comment mesurer que l'app est "plus aboutie" — 5 indicateurs concrets et mesurables :

1. **Temps jusqu'à première action** — Nombre de secondes entre l'ouverture de l'app et le premier clic sur "✓ Fait". Objectif : < 5 secondes (actuellement : l'utilisateur doit parser 10 badges + lire la hero card + trouver la carte). Mesurable en chronométrant le flux matin.

2. **Taux de complétion quotidien** — Ratio (révisions validées / révisions urgentes + aujourd'hui) sur 7 jours glissants, visible dans la page Stats. Objectif : > 80% sur une semaine normale.

3. **Lacunes créées par semaine** — Nombre de lacunes ajoutées (via la page Lacunes ou le futur bouton inline). Indicateur de engagement actif avec la matière. Objectif de référence à mesurer après le QW7 (bouton lacune inline).

4. **Nombre d'items de sidebar utilisés** — Sur une semaine, combien de pages distinctes sont visitées. Si l'utilisateur utilise toujours les mêmes 4-5 pages, les autres sont candidates à la suppression. Observable dans les logs loguru (`ENTERING XXX PAGE`).

5. **Erreurs silencieuses dans les logs** — Après correction des bugs de `stats.py` et `local_store.py`, monitorer `logs/synapse_*.log` pour des `logger.error()` ou `logger.warning()` dans les chemins critiques (preload, review generation, mastery calculation). Objectif : 0 erreur silencieuse dans le chemin quotidien après Phase 1.
