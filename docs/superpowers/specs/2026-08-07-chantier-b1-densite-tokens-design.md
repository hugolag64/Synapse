# Chantier B1 — Densité & tokens

**Date** : 2026-08-07
**Statut** : design validé, prêt pour plan d'implémentation

## Contexte

Suite du chantier A (correctifs & navigation, terminé). Le chantier B (design system Linear)
a été découpé en 4 sous-chantiers séquentiels — voir
[docs/UI_REFONTE_ETAT_DES_LIEUX.md](../../UI_REFONTE_ETAT_DES_LIEUX.md) pour la vue d'ensemble et
l'audit complet. B1 est le premier : purement mécanique, aucune décision de design nouvelle, taux
de risque faible.

Le projet dispose déjà d'un design system documenté et d'une refonte complète réalisée
(`design_handoff_synapse_refonte/`, 16 écrans, étapes 0-18). QCM, Épreuves & Annales, Examen blanc
et Prépa ont été construits **après** cette refonte et n'ont jamais reçu le même traitement — B1
comble cet écart sur les points mécaniques (largeur, fond de carte, résidus Tailwind, libellés).

## Objectif

Faire disparaître l'espace mort et l'aspect « gris/daté » sur 8 pages en appliquant partout un
principe déjà utilisé ailleurs dans le cockpit (Items, Révisions, Points faibles) : **`--surface`
est la couleur de survol, jamais un fond de repos** ; **une page liste occupe toute la largeur
disponible**, sans plafond artificiel.

## Périmètre

### 1. Largeur & centrage — 8 fichiers

**Problème.** Chaque fichier plafonne son conteneur avec un `max-width` fixe. Certains (`revue.py`,
`stats_cockpit.py`, `prepa.py`) n'ont en plus **aucun** `margin:0 auto`, donc le bloc colle à gauche
au lieu de se centrer — exactement le symptôme « pas centrée » signalé pour Revue hebdo et
Statistiques.

**Décision.** `max-width` → `max-width:none` sur les 8 fichiers suivants, alignant leur
comportement sur `items.py`/`todo_cockpit.py` (déjà corrigés au chantier A) :

| Fichier | Sélecteur | Valeur actuelle |
|---|---|---|
| `frontend/pages/qcm_cockpit.py:250` | `.qc-wrap` | `max-width:1200px` |
| `frontend/pages/annales.py:18` | `.ans-wrap` | `max-width:1200px` |
| `frontend/pages/annale_detail.py:23` | `.an-wrap` | `max-width:1200px` |
| `frontend/pages/exam_simulator_page.py:22` | `.ex-wrap` | `max-width:1100px` |
| `frontend/pages/prepa.py:15` | `.prep-wrap` | `max-width:980px` |
| `frontend/pages/weak_points_cockpit.py:31` | `.wp-wrap` | `width:860px; max-width:100%` → `width:100%; max-width:none` |
| `frontend/pages/revue.py:44` | `.rh-wrap` | `max-width:900px` (pas de `margin:auto`) |
| `frontend/pages/stats_cockpit.py:36` | `.st-wrap` | `max-width:900px` (pas de `margin:auto`) |

Une fois le plafond retiré, `margin:0 auto` devient sans objet (rien à centrer dans un bloc qui
occupe 100 % de la largeur) — pas besoin de l'ajouter sur `revue.py`/`stats_cockpit.py`/`prepa.py`.

**Hors périmètre, volontairement non touchés** : `semestres_cockpit.py` (900px),
`externat_cockpit.py` (900px), `settings_cockpit.py` (700px) — non cités dans les retours
utilisateur ; ce sont des pages courtes (formulaire de connexions, cartes de stage peu nombreuses)
où un plafond reste pertinent.

### 2. Vue Item spécifique — traitement différent

**Problème.** `.ci-center` (`frontend/pages/course_detail_cockpit.py:76`) plafonne à 900px alors
que la page a un layout à deux colonnes (centre + panneau contextuel 270px) : sur un grand écran,
l'espace restant entre les deux est mort.

**Décision.** Contrairement aux pages-liste, la colonne centrale d'un détail d'item contient du
texte long (note Obsidian, paragraphes de physiopathologie) — un plein-largeur dégraderait la
lisibilité. Le plafond est **relevé, pas supprimé** : `max-width:900px` → `max-width:1100px`,
décision utilisateur explicite (lisibilité > plein-écran pour cette page précise). La règle
`flex:1 1 auto` déjà présente est conservée : la colonne comble l'espace disponible jusqu'à ce
plafond, puis s'arrête.

### 3. Cards grises → tokens corrects — 4 fichiers, 6 sélecteurs

**Problème.** `--surface` (#f4f4f5 en clair) est utilisé comme fond **permanent** de conteneurs de
contenu, au lieu d'être réservé à l'état `:hover`. C'est ce qui produit l'aspect « carte grise
plate » que les listes bien traitées (Items, QCM-liste par cours, Révisions, Points faibles)
n'ont pas : celles-ci utilisent un fond transparent/`--bg` + une bordure, et ne colorent qu'au
survol.

**Décision — deux traitements selon le rôle du sélecteur**, distingués par ce qu'ils représentent :

*Cartes individuelles cliquables* (chacune représente un élément de liste sur lequel on clique) :
`background:var(--surface)` → `background:var(--bg)`. La règle `:hover { background:var(--surface-hover); }`
déjà présente sur ces deux sélecteurs **reste inchangée** — seul le fond de repos change.

| Fichier | Sélecteur | Rôle |
|---|---|---|
| `frontend/pages/annales.py:24` | `.ans-card` | ligne de la liste d'annales |
| `frontend/pages/annale_detail.py:29` | `.an-part-card` | carte de sous-partie |

*Panneaux structurels* (contiennent leurs propres lignes/éléments déjà correctement survolables ;
ce ne sont pas eux-mêmes des cibles de clic) : même changement de fond
(`background:var(--surface)` → `background:var(--bg)`), mais **sans ajouter de `:hover`** — un
survol de zone sur un panneau entier qui contient déjà des lignes avec leur propre survol
produirait deux états de survol superposés et confus.

| Fichier | Sélecteur | Rôle |
|---|---|---|
| `frontend/pages/qcm_cockpit.py:293` | `.qc-history` | panneau conteneur de l'historique rejouable (les lignes `.qc-history-row` à l'intérieur ont déjà leur propre survol) |
| `frontend/pages/qcm_cockpit.py:303` | `.qc-selected` | panneau d'affichage de la session sélectionnée (lecture seule, pas interactif comme bloc) |
| `frontend/pages/exam_simulator_page.py:27` | `.ex-card` | carte de section (en-tête + contenu) |
| `frontend/pages/exam_simulator_page.py:31` | `.ex-panel-q` | panneau de question (contient ses propres lignes `.ex-prop-row`, déjà correctement survolables) |

### 4. Résidus Tailwind bruts → tokens

**Problème.** Trois emplacements utilisent encore des classes Tailwind codées en dur au lieu des
tokens `var(--*)`, jamais migrées lors de la construction initiale de ces écrans.

| Fichier:ligne | Classes actuelles | Remplacement |
|---|---|---|
| `frontend/pages/annales.py:227` | `border border-slate-200 dark:border-slate-800 rounded-md gap-1 bg-slate-50 dark:bg-slate-900/40` | `border` inline-style `border-color:var(--border); border-radius:var(--radius-md); background:var(--bg-alt)` |
| `frontend/pages/annales.py:313` | `border border-slate-200 dark:border-slate-800 rounded-md` | `border-color:var(--border); border-radius:var(--radius-md)` |
| `frontend/pages/annale_detail.py:175` | `border border-slate-200 dark:border-slate-800 rounded-md` | `border-color:var(--border); border-radius:var(--radius-md)` |

Ces trois occurrences utilisent des classes Tailwind sur un `ui.column()`/`ui.card()` plutôt qu'une
classe CSS dédiée : le remplacement se fait via `.style(...)` avec les tokens, pas via l'ajout
d'une nouvelle classe partagée (portée trop restreinte pour justifier une classe globale).

### 5. Retrait du préfixe « + » sur les boutons

**Problème.** Cinq libellés de bouton portent un préfixe `+ ` alors qu'ils affichent déjà une icône
Quasar signifiant l'ajout — redondance signalée par l'utilisateur comme du bruit visuel.

| Fichier:ligne | Avant | Après |
|---|---|---|
| `frontend/components/command_palette.py:158` | `"+ Lacune"` | `"Lacune"` |
| `frontend/components/command_palette.py:159` | `"+ QCM"` | `"QCM"` |
| `frontend/components/command_palette.py:160` | `"+ Séance"` | `"Séance"` |
| `frontend/components/command_palette.py:224` | `"+ Lacune"` | `"Lacune"` |
| `frontend/components/command_palette.py:225` | `"+ QCM"` | `"QCM"` |
| `frontend/components/command_palette.py:226` | `"+ Séance"` | `"Séance"` |
| `frontend/components/course_quick_actions.py:44` | `"+ Lecture"` | `"Lecture"` |
| `frontend/pages/externat_cockpit.py:124` | `"+ Nouveau stage"` | `"Nouveau stage"` |

Le bouton `"💡 + Mnémo / Image"` (`course_detail_cockpit.py:725`) est **exclu** de ce point : son
emoji et son triple codage (emoji + texte + icône) relèvent de la refonte complète du wizard
associé, traitée au chantier B2, pas d'un simple retrait de préfixe.

### 6. QCM — suppression du sélecteur de difficulté

**Problème.** L'écran de lancement d'une session QCM générée par IA (`ai_practice_panel.py`)
propose un `ui.toggle` à 4 valeurs (Standard / EDN / Difficile / Concours, défaut EDN). L'utilisateur
ne prépare que l'EDN : ce choix n'a jamais d'utilité réelle et alourdit l'écran pour rien.

**Décision.** Le `ui.toggle` (lignes 55-62 de `frontend/components/ai_practice_panel.py`) est
retiré de l'interface. L'appel de génération (ligne 117) utilise
`difficulty=PracticeDifficulty.EDN` en dur. La ligne 219 (« Difficulté : EDN · questions
fermées · raisonnement clinique ») reste : elle informe déjà que la difficulté est fixée à EDN,
sans proposer de la changer — cohérent avec la suppression du sélecteur.

**Hors périmètre.** L'enum `PracticeDifficulty` (backend) n'est pas modifiée : elle est utilisée par
`backend/core/practice/service.py` et par des tests (`test_ai_practice.py`, `test_ai_routing.py`),
et potentiellement par `frontend/pages/qcm.py` (classic) — vérifier avant implémentation qu'aucune
autre vue cockpit n'expose ce même toggle.

## Hors périmètre du chantier B1

Explicitement exclus, traités dans les sous-chantiers suivants :
- Refonte des wizards mnémo/image et validation de séance (palette de couleurs, centrage,
  suppression des emojis) → **B2**.
- Animation d'expansion des collèges, redesign visuel de Prépa (motion, hiérarchie, « récemment
  consulté ») → **B3**.
- Déplacement du bloc Tuteur DP de l'onglet Historique vers l'onglet QCM → **B4**.
- Toute modification de la logique pédagogique (Flash-Zero, Sprint EDN, acquis antérieurs) →
  **chantier C**.

## Risques

- **Points 1 et 2** (largeur) sont des changements CSS purs, à risque de régression visuelle nul —
  déjà validés sur `items.py`/`todo_cockpit.py` au chantier A avec zéro effet de bord détecté.
- **Point 3** (fond de carte) change une couleur de fond sur des conteneurs qui contiennent parfois
  eux-mêmes des lignes cliquables (`qc-history-entry`, `qc-selected`) — vérifier visuellement
  qu'aucune ligne interne ne devient invisible faute de contraste une fois le fond du parent
  éclairci.
- **Point 6** est le seul changement fonctionnel (pas seulement visuel) du chantier B1 : vérifier
  qu'aucun test n'attend la présence du toggle de difficulté dans `ai_practice_panel.py` avant de le
  retirer.

## Tests

Aucun de ces changements n'a de logique métier testable au sens strict (à l'exception du point 6).
Les tests à ajouter/adapter :
- Un test de présence des règles CSS clés (`max-width:none`, absence de `max-width:1200px`, etc.)
  par fichier, sur le modèle de `tests/test_items_sorting.py::test_items_list_is_not_capped_at_a_fixed_width`
  déjà écrit au chantier A.
- Un test vérifiant que `ai_practice_panel.py` ne construit plus de `ui.toggle` de difficulté et
  appelle bien la génération avec `PracticeDifficulty.EDN` fixé.
- Suite complète (`pytest -q`) avant/après pour confirmer l'absence de régression, comme pour le
  chantier A.
