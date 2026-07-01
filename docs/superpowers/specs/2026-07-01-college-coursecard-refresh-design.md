# Collèges & CourseCard — refonte visuelle (juillet 2026)

## Contexte

Suite de la refonte UI/UX entamée en mai-juin 2026 (Dashboard puis Lacunes). Étape suivante : la page Collèges (`frontend/pages/colleges.py`) et le composant `CourseCard` (`frontend/components/course_card.py`) qu'elle utilise.

Deux problèmes identifiés :
1. La couleur "fragile" du switch entre collèges utilise un orange saturé (`#D97706`) qui jure avec la DA (palette bleu/violet/slate définie dans `static/synapse.css`), au lieu du token ambré déjà prévu (`--s-amber-700: #B45309`).
2. La barre d'actions de `CourseCard` n'apparaît qu'au survol (`hover-reveal`), regroupe des actions de fréquence très inégale (PDF, QCM, Obsidian, +1 lecture), et l'action la plus utilisée ("Nouvelle séance") est enterrée dans un menu `⋯`. L'utilisateur veut que les 5 actions les plus fréquentes soient accessibles en permanence, sans être présentées comme une grille bento.

Décidé en session de brainstorming (compagnon visuel) : garder l'architecture actuelle de `CourseCard` (header + titre + barre d'actions), mais rendre la barre permanente et réorganiser sa hiérarchie.

## 1. Fix couleur — switch collèges

Dans `frontend/pages/colleges.py`, le dict `_FILL` mappe chaque niveau de maîtrise à une couleur de remplissage (bordure active du switch, texte de stats, jauge de couverture) :

```python
_FILL = {
    "solide":       "#059669",
    "correct":      "#3B82F6",
    "fragile":      "#D97706",   # → #B45309
    "non_commence": "#CBD5E1",
}
```

**Changement** : `"fragile": "#D97706"` devient `"fragile": "#B45309"` (token `--s-amber-700`, déjà défini dans `synapse.css` mais jamais réutilisé ici).

`_GHOST["fragile"]` et `_TINT["fragile"]` (versions translucides utilisées pour le fond de jauge et le tint de card active) doivent être recalculées à partir de la même teinte RGB `(180, 83, 9)` au lieu de `(217, 119, 6)`, pour rester cohérentes :
- `_GHOST["fragile"]` : `rgba(180,83,9,0.12)`
- `_TINT["fragile"]` : `rgba(180,83,9,0.05)`

`_TEXT_CLS["fragile"]` (classe Tailwind `text-amber-600 dark:text-amber-400`) reste inchangée — Tailwind amber-600 (`#D97706`) est proche visuellement mais c'est une classe utilitaire séparée du système de tokens custom ; pas dans le scope de ce fix (pas de token Tailwind custom à ce jour pour amber-700).

Aucun changement de comportement : le switch reste un clic pour changer d'onglet, drag-and-drop pour réordonner (`SortableList`), bordure haute pleine si actif / 20% opacité si inactif.

## 2. CourseCard — nouvelle barre d'actions

### 2.1 État actuel (pour référence)

`frontend/components/course_card.py` a une `.synapse-action-bar` qui n'apparaît qu'au survol de la card (`opacity:0` → `opacity:1` en CSS), contenant : PDF, QCM, Obsidian, +1 lecture, puis un bouton `⋯` ouvrant un menu avec : Nouvelle séance (CTA en tête de menu), suivi J3/J7/J14/J30, Fiche LISA, Objectifs (OIC), Notion, Fiche EDN (conditionnel), Lier note Obsidian (conditionnel), section Complétion (Résumé/ChatGPT/Anki).

### 2.2 Nouvelle disposition

**Barre d'actions — toujours visible**, plus de hover-reveal (`opacity` fixe à `1`, `pointer-events` toujours actifs). Contenu, de gauche à droite :

| Élément | Icône (Material Symbols) | Couleur | Action |
|---|---|---|---|
| Notion | `description` | slate-900 / slate-200 (dark) | `ui.navigate.to(_notion_url, new_tab=True)` |
| OIC LiSA | `flag` | violet `#7C3AED` | `open_lisa_dialog(course)` |
| +Lecture | `add_circle` | vert `#059669` | `quick_mark_course_action(course, "lecture", ...)` (inchangé) |
| QCM | `quiz` | gris `#64748B` si non fait, violet `#7C3AED` si fait | non fait → `_open_quick_qcm_dialog(course, refresh_fn)` ; fait → toggle via `quick_mark_course_action(course, "qcm", ...)` (comportement identique à l'existant) |
| *(spacer flex-1)* | | | |
| Séance | bouton plein, icône `add_task` + label "Séance" | fond violet `#7C3AED`, texte blanc | `open_quick_session_dialog(course, refresh_fn, client)` |

Tous les boutons icône : 28×28px, `border-radius:8px`, `hover:bg-slate-100 dark:hover:bg-slate-800`. Le bouton CTA "Séance" reste visuellement distinct (fond plein) pour signaler que c'est l'action principale — cohérent avec la mise en avant violette déjà utilisée pour "Nouvelle séance" dans l'ancien menu.

**Overflow "⋯" — dans le header de la card**, à côté du dot de maîtrise (pas dans la barre d'actions). Icône `more_vert`, gris clair (`text-slate-300`), petite (20px). Ouvre le même menu qu'aujourd'hui, moins les 4 items remontés dans la barre (Notion, OIC, +Lecture, QCM ne sont plus dans le menu) :

- PDF (ouvrir si présent / chercher via `open_pdf_wizard` sinon)
- Suivi J3/J7/J14/J30 (`open_start_tracking_dialog`)
- Fiche LISA (lien externe `_lisa_url`, distinct du dialogue OIC)
- Fiche EDN (conditionnel)
- Obsidian (ouvrir/créer/lier note — conditionnel selon config)
- Section Complétion (Résumé / ChatGPT / Anki, inchangée)

### 2.3 Dark mode

Mêmes teintes que le light mode mais désaturées : fond de card `#111827`, fond de barre `#0F172A`, icônes éclaircies (ex. OIC violet → `#A78BFA`, +Lecture vert → `#34D399`). Le bouton CTA "Séance" garde `#7C3AED` plein dans les deux modes (contraste suffisant sur fond sombre).

### 2.4 CSS

`.synapse-action-bar` dans `static/synapse.css` : supprimer les règles `opacity:0`/`transform:translateY(6px)` et le `:hover` qui les annule — la barre est visible par défaut. Garder le style de fond/bordure existant.

Nouvelle classe pour l'icône overflow de header (`.synapse-card-overflow` ou équivalent), positionnée dans le `<div>` header à côté du dot de maîtrise existant.

## 3. Point bleu (pour mémoire, aucun changement)

Le dot coloré à côté du badge ITEM est l'indicateur de **maîtrise** (`PROGRESSION_COLORS` : vert=solide, bleu=correct, orange=fragile, gris=non commencé), indépendant du statut de lecture. Confirmé comme correct par l'utilisateur, non modifié par cette refonte.

## Hors scope

- Pas de changement de structure de données, de logique Notion, ou de comportement des dialogues existants (`open_quick_session_dialog`, `_open_quick_qcm_dialog`, `open_lisa_dialog`, `open_start_tracking_dialog`, `open_pdf_wizard`) — seul leur point d'entrée visuel change.
- Pas de changement à la grille de collèges elle-même (layout, tri, drag-and-drop) — seulement la couleur "fragile".
- Pas de changement aux pages Semestres/Externat qui réutilisent aussi `CourseCard` — elles héritent automatiquement du nouveau composant sans changement de code côté appelant (mêmes props `context`, `refresh_fn`, `client`, `accent_color`, `is_urgent`).
