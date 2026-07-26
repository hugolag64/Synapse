# Handoff : Refonte UI/UX Synapse

## Overview
Synapse est une application web personnelle de pilotage des études médicales et de préparation à l'EDN. Cette refonte transforme l'interface actuelle (top-nav clair, cartes uniformes, émojis-icônes, accent violet saturé) en un **cockpit décisionnel** dense et rapide, inspiré de la structure de Linear et de la connaissance reliée d'Obsidian, avec une identité propre à Synapse.

Objectif produit central : répondre en moins de 5 secondes à **« que dois-je faire maintenant, pourquoi, et avec quelle ressource ? »**.

Direction retenue : **« Linear dominant » (1a)** — listes denses + panneau contextuel — **avec la sidebar labellisée et groupée de la direction 1b**.

## About the Design Files
Les fichiers de ce bundle sont des **références de design réalisées en HTML** — des prototypes montrant l'apparence et le comportement souhaités, **pas du code de production à copier tel quel**. Le prototype est écrit comme un « Design Component » (un runtime maison, `support.js`) : ne portez pas ce runtime en prod. La tâche est de **recréer ces écrans dans l'environnement cible** — ici une app **NiceGUI / Quasar (Python)** existante — en réutilisant ses composants (`q-layout`, `q-drawer`, `q-list`, `q-tabs`, `q-dialog`, `q-linear-progress`…) et ses patterns établis. Le backend (répétition espacée, mastery, Notion, Obsidian, Google Calendar) **reste inchangé** : c'est la couche présentation qui est refondue.

Un tableau de correspondance NiceGUI/Quasar + écarts figure dans `Synapse - Handoff.dc.html` (section 6) et est résumé plus bas.

## Fidelity
**High-fidelity (hifi).** Couleurs, typographie, espacements, densité et interactions sont finaux et doivent être reproduits fidèlement en réutilisant les composants Quasar et une feuille de surcharge de tokens. Les valeurs exactes sont listées dans « Design Tokens » ci-dessous.

## Principe transverse — grammaire de statut
Six dimensions lisibles d'un coup d'œil ; **une seule** passe par la couleur.

| Dimension | Encodage | Valeurs |
|---|---|---|
| Progression (workflow) | **Forme** (anneau), jamais la couleur | ○ à préparer · ◔ à lire · ◑ en construction · ◕ à consolider · ◉ à entraîner · ● maîtrisé |
| Maîtrise / santé | Barre + score 0–100 | solide ≥80 (vert) · correct 55–79 (gris) · fragile 30–54 (ambre) · critique <30 (rouge) |
| Urgence / retard | **Couleur** (stable) | rouge = en retard · ambre = échéance du jour · vert = à jour · gris = non planifié |
| Type d'activité | Étiquette mono | PDF · NOTE · QCM · VIDÉO · RAPPEL · LACUNE |
| Charge / temps | Largeur de barre + minutes mono | durée estimée, charge du jour |
| Reporté / archivé | Opacité réduite (~0.55) | jamais de couleur |

Rouge / ambre / vert ne servent qu'à l'urgence et à la santé de maîtrise — jamais décoratifs. Aucun émoji comme icône : glyphes géométriques + `<kbd>`.

## Screens / Views

### App shell (commun à toutes les vues)
- **Layout** : trois colonnes en flex, hauteur plein écran. Sidebar (gauche, 200px, réductible à 56px) · zone centrale (flex:1) · panneau contextuel (droite, 296px, masquable). Séparateurs : bordure 1px `--border`.
- **Sidebar** : fond `--bg-alt`, padding 14px 10px. En-tête = pastille logo « S » (24px, fond `--accent`, texte `--accent-text`) + wordmark « Synapse » (Inter 600, 13.5px) + chevron ‹ pour réduire. Barre de recherche cliquable (ouvre la command palette) avec `<kbd>⌘K</kbd>`. Nav **groupée** avec petits labels 10px uppercase `--text-dim` :
  - **Pilotage** : Aujourd'hui · Planning · Révisions (badge count `2`)
  - **Connaissance** : Collèges · Semestres · Items · QCM · Lacunes (point ambre)
  - **Analyse** : Revue hebdo · Statistiques · Externat
  - **Système** : Paramètres
  - **Récents** (bas de sidebar) : 2 items récents.
  - Item nav : hauteur ~32px, radius 6px, glyphe 14px + label 12.5px. Actif = fond `--surface`, texte `--text`, poids 500. Hover = fond `--surface`. Mode réduit : labels masqués, glyphes conservés, largeur 56px, transition `width 160ms`.

### 1. Aujourd'hui (cockpit) — vue pilote
- **Purpose** : savoir immédiatement quoi faire maintenant.
- **Topbar** (46px) : titre « Aujourd'hui » (15px/600) + date grise + toggle segmenté Jour / Semaine (fond `--surface`, actif fond `--bg`).
- **Daily summary** : bandeau **une seule ligne** (pas de cartes séparées), séparateurs verticaux 1px. Métriques : « 2 h 10 recommandé » (17px/600), « 7 tâches », « 2 en retard » (point + chiffre rouge), « 1 lacune critique » (point ambre), et à droite une mini-barre de progression du jour (96×5px, remplissage `--accent`).
- **Recommended action** : bloc dominant, fond `--accent-wash`, bordure basse. Ligne de méta mono `▸ PROCHAINE ACTION` + point rouge + « Priorité haute · rappel J30 en retard 4 j ». Corps : id mono `ITEM 330` + titre 16px/600 + raison + « ~35 min · maîtrise 38 ». Étiquette `PDF`. Bouton primaire « Commencer » (fond `--accent`, radius 6px, 9×16px).
- **File de travail** : en-tête de colonnes 11px uppercase (Item / titre / Type / Durée / Échéance). Lignes denses (`study task row`) hauteur ~40px : anneau de progression (forme, couleur neutre) · id mono · titre + collège grisé (ellipsis) · étiquette type mono · durée · échéance (point couleur urgence + libellé). Ligne sélectionnée = fond `--surface`. Ligne « maîtrisé/rappel lointain » à opacité 0.55. Clic → sélection persistante + ouverture du panneau contextuel.
- **Context panel** (droite) : en-tête (forme + titre court + id + ✕). Sections : « Pourquoi maintenant » (encadré `--accent-wash`), « Maîtrise » (barre + score), « Note Obsidian » (extrait encadré), « Notions reliées » (liens `◇`), « Ressources » (liens `↗`). Pied : boutons Terminer (primaire) / Reporter / Focus.

### 2. Détail d'un item — vue pilote
- **Purpose** : connaissance reliée d'un item sans empiler 15 cartes.
- **En-tête synthétique** : fil d'ariane (Aujourd'hui › Collège › Item 221). Ligne titre : id mono `ITEM 221` + `Athérome` (24px/600) + « ◕ À consolider ». Ligne de méta : maîtrise (barre + « 48 · fragile »), dernière révision, prochaine (J7 ambre), QCM moyen. Actions : Réviser maintenant (primaire) · ↗ PDF · ↗ Obsidian. **L'en-tête passe à la ligne (`flex-wrap`) sous ~1000px.**
- **Navigation interne** (onglets, soulignés accent 2px) : Vue d'ensemble · Note · Révisions · QCM · Lacunes · Historique.
- **Onglet Vue d'ensemble** : bloc recommandation (`--accent-wash`) ; **grille 2 colonnes** avec (a) **Prédiction de maîtrise** = courbe d'oubli SVG (repère pointillé rouge « J+7 · 42 », point de départ « auj. 48 ») + phrase « sans révision → 42 dans 7 j (fragile) » ; (b) **Notions reliées** = mini-graphe SVG (nœud central 221 accent + 4 voisins colorés par urgence : SCA rouge, FdR CV ambre, Statines/ECG gris) + suggestion du voisin le plus faible. Puis paragraphe physiopathologie + note perso (bord gauche accent).
- **Onglet Note** : rendu Markdown de la note Obsidian (titres `##`, liens internes), chemin de fichier mono. **Backlink vivant** : action « ⚑ Créer une lacune » à partir d'une sélection → note « ajoutée à l'item 221 et à la file de révision » (point vert).
- **Onglet Révisions** : timeline J3/J7/J14/J30 (point couleur urgence, cycle mono, état fait/à faire/futur, bouton Réviser sur l'échéance due).
- **Onglet QCM** : barres Dernier QCM / Moyenne 30 j + **Série QCM adaptative** (encadré `--accent-wash`) : « 15 questions ciblées sur tes 3 erreurs récurrentes » avec chips pondérés (`plaque stable/instable ×7` rouge, `dd douleur thoracique ×5` ambre, `FdR ×3`) + bouton « Lancer la série adaptative ».
- **Onglet Lacunes** : cartes lacune (point statut, titre, récurrence, bouton Revoir ; résolue à opacité 0.6).
- **Onglet Historique** : timeline (date mono, type badge `--accent-wash`, détail, durée).
- **Panneau droit (270px)** : Notions reliées · Rétroliens · Ressources.

### 3. Planning
Grille semaine 7 colonnes (`grid-template-columns:repeat(7,1fr)`), chaque jour = carte min-height 280px : en-tête (jour uppercase + date mono, aujourd'hui en `--accent`/`--accent-wash`), blocs empilés = **tâche** (bord gauche plein `--accent`, fond `--bg`) ou **événement calendrier** (bord gauche pointillé `--text-dim`, transparent), pied = charge du jour. Légende sous la grille. En-tête : charge restante + créneaux libres + navigation semaine.

### 4. Révisions
File par cycle de répétition espacée. Chips filtres (Toutes / J3 / J7 / J14 / J30). En-tête de colonnes puis lignes : étiquette cycle mono, id, cours + collège + type, barre de maîtrise + score, échéance (point urgence), bouton Réviser.

### 5. Collèges (rollup par matière)
Liste dense, une ligne par collège. Ordre des colonnes : **nom + « lus/total · restants »** · barre de progression (flex) · **pourcentage mono** · **retard** (cliquable → ouvre Items filtré sur ce collège ; fond rouge léger si >0, « à jour » gris sinon, chevron ›) · **fragiles** (point ambre + compte) · **prochaine rév.** (point urgence + libellé) · **QCM moyen** (mono, couleur santé, « — » si aucun). Hover ligne = `--surface-hover`.

### 6. Semestres
Cartes de progression par UE. Noms **en toutes lettres** : « Semestre 5 — Cardiologie · Pneumologie · Néphrologie », etc. Barre de progression + % (couleur santé) + nombre d'items.

### 7. Items
Liste transverse filtrable de tous les items. Chips filtres (Tous / Cardiovasculaire / Fragile-critique / En retard). Colonnes : forme · id mono · **titre** · Collège · Type · Maîtrise (barre + score) · Prochaine (point urgence). **En vue filtrée sur un collège**, la colonne Collège (redondante) est remplacée par **« Dernière révision »** (date relative + point de couleur urgence), avec un rappel discret dans la barre de filtres. Clic ligne → détail item.

### 8. QCM
Bandeau de stats (moyenne 71 %, taux de réussite, cours à retravailler). Liste par cours : id, titre + collège + nb sessions, barre de score (couleur santé), score mono, badge « à retravailler » si <70 %.

### 9. Lacunes
Liste de cartes : point statut (critique rouge / active ambre / résolue vert à opacité 0.55), titre, récurrence, collège, id. Actions d'en-tête : ↻ Synchroniser Obsidian · + Ajouter.

### 10. Statistiques
Bandeau (temps travaillé, révisions faites, maîtrise moyenne). Toggle 7 j / 30 j / Tout. « Temps par collège » (barres horizontales). « Activité récente » (timeline).

### 11. Revue hebdo (générée automatiquement)
Bandeau (temps + delta vs semaine dernière, +N consolidés, −N en régression, révisions faites). Deux colonnes : **Consolidé cette semaine** (vert, transitions de score « 52 → 61 ») et **A régressé / oubli** (rouge, « 40 → 26 »). Bloc **Focus semaine prochaine** (`--accent-wash`) : 3 priorités à points de couleur + bouton « Planifier ce focus ».

### 12. Externat
Cartes de stage clinique : nom, statut (point couleur), dates, items rattachés (ids mono).

### 13. Paramètres
Liste de connexions (Notion, Obsidian, Google Calendar = vert connecté ; EDNpro/Hypocampus = ambre, saisie manuelle) + bascule d'apparence clair/sombre.

### 14. Command palette (⌘K / Ctrl+K)
Dialogue centré (largeur 560px, radius 8px, ombre popover) sur scrim `rgba(15,15,20,0.32)`, à ~13vh du haut. Input avec `⌕` + `<kbd>esc</kbd>`. Liste filtrée (fuzzy) : colonne tag mono (aller/item/action) · label · groupe. Entrée exécute, Esc ferme, focus auto sur l'input.

### 15. Mode focus (plein écran)
Overlay plein écran fond `--bg`. En-tête discret « Mode focus » + « Quitter le focus `<kbd>esc</kbd>` ». Centre : méta mono (ITEM · COLLÈGE · TYPE), titre 30px/600, objectif, **minuteur 68px mono (25:00)** + barre de progression, boutons ▶ Démarrer / ↗ Ouvrir PDF, puis ⚑ Noter une lacune / ✓ Marquer terminé. Cohérent avec le thème général.

### 16. Mobile simplifié (<768px)
Cadre 390×780. Header (logo + « Aujourd'hui » + ⌕). Résumé compact une ligne. Action recommandée (carte `--accent-wash`, CTA pleine largeur). File compacte (forme + titre + collège/durée + type + point urgence). **Bottom nav** 5 entrées (Auj. / Planning / Révisions / Items / Lacunes). Le détail s'ouvre en drawer plein écran ; le panneau contextuel s'empile.

## Interactions & Behavior
- **Réduire la sidebar** : ‹/› bascule 200px ↔ 56px, transition `width 160ms ease-out` ; labels masqués, glyphes conservés.
- **Command palette** : ⌘K / Ctrl+K ouvre (preventDefault), frappe filtre, Entrée exécute, Esc ferme.
- **Navigation clavier** : ↑/↓ dans les listes, Entrée ouvre ; focus visible partout (anneau accent 2px, offset 2px).
- **Sélection tâche** : clic → surbrillance persistante (`--surface`) + ouverture panneau contextuel.
- **Reporter / replanifier** : offset calculé **depuis la date d'échéance théorique** (jamais depuis aujourd'hui) ; la date théorique et l'id de tâche sont préservés.
- **Retard collège cliquable** : clic → vue Items filtrée sur ce collège (`stopPropagation` pour ne pas déclencher l'ouverture de ligne).
- **Filtre Items par collège** : masque la colonne Collège, affiche « Dernière révision » à la place.
- **Ouvrir PDF / Obsidian** : actions directes depuis ligne, panneau, détail.
- **Mode focus** : réduit l'UI à tâche + minuteur + ressource + noter une difficulté ; Esc quitte.
- **Aujourd'hui / Semaine** : toggle segmenté.
- **Clair / sombre** : attribut `data-theme="dark"` sur la racine → tous les tokens basculent.
- **Animations** : 120–180ms ease-out, sur couleur/bordure/opacité uniquement. Pas de bounce, scale, ni transition de page.

## State Management
Variables d'état (dans le prototype, à mapper sur l'état NiceGUI/session) :
- `view` : vue active (`today`, `planning`, `revisions`, `colleges`, `semestres`, `items`, `item`, `qcm`, `lacunes`, `stats`, `revue`, `externat`, `settings`).
- `theme` : `light` | `dark`.
- `device` : `desktop` | `mobile` (démo uniquement — en prod, media query réelle).
- `selId` : id de tâche sélectionnée dans la file Aujourd'hui.
- `panelOpen` : panneau contextuel visible.
- `paletteOpen` + `query` : command palette.
- `focusOpen` : mode focus.
- `itemTab` : onglet actif du détail item.
- `collapsed` : sidebar réduite.
- `itemsFilter` : collège filtrant la vue Items (`null` = tous).

Données servies par le backend existant (inchangé) : items (id, titre, collège, forme/étape, maîtrise 0–100, prochaine échéance + retard, type, dernière révision), révisions (cycle J3/J7/J14/J30), QCM (scores, sessions, erreurs récurrentes), lacunes (statut, récurrence), planning (tâches + événements Google Calendar), collèges (lus/total, retard, fragiles, prochaine, QCM moyen), stats, revue hebdo (deltas de maîtrise).

## Design Tokens
Repris du design system **Linear Editorial**. Charger via `ui.add_head_html` sur `:root` / `.body--dark` (ou `[data-theme="dark"]`).

**Couleurs — clair / sombre**
- `--bg` #ffffff / #0f0f14
- `--bg-alt` #fafafa / #15151b
- `--surface` #f4f4f5 / #1a1a20
- `--surface-hover` #ececee / #232329
- `--text` #0f0f14 / #f4f4f6
- `--text-muted` #6b6b76 / #8b8b96
- `--text-dim` #a0a0ab / #5c5c68
- `--border` #e4e4e7 / #26262f
- `--border-strong` (bordure renforcée hover) — cf. tokens DS
- `--accent` #5e6ad2 / #7b85e8
- `--accent-hover` (accent assombri au survol)
- `--accent-text` (texte sur accent, ~#ffffff / #0f0f14)
- `--accent-wash` (fond accent très pâle pour blocs recommandation)
- **Sémantiques (stables clair & sombre)** : `--success` #3fb271 · `--warning` #e5a23f · `--danger` #e5484d
- Retard collège : fond rouge léger `rgba(229,72,77,0.08)`
- Scrim overlay : `rgba(15,15,20,0.32)`

**Typographie**
- `--font-sans` : Inter (400 / 500 / 600 uniquement)
- `--font-mono` : JetBrains Mono (ids, durées, dates, scores, kbd)
- Échelle : 10.5 / 11 / 11.5 / 12 / 12.5 / 13 / 13.5 / 14 / 15 / 16 / 17 / 20 / 24 / 26 / 30 / 68 (minuteur) px
- Titres ≥22px : letter-spacing −0.5 % (−0.01 à −0.02em). Emphase = poids 600, jamais d'italique. Casse : sentence case ; UPPERCASE seulement sur labels 10–11px.

**Espacement / rayons / profondeur**
- Base 4px : 4 / 8 / 12 / 16 / 24 / 32 / 48 / 64
- Rayons : 4 (petits contrôles) · 6 (boutons, champs) · 8 (cartes, dialogues) — **plafond 8px**, pas de pills.
- Profondeur : bordures 1px comme seul indice par défaut. Une seule ombre `--shadow-popover` (`0 2px 8px rgba(0,0,0,0.04)`) réservée aux dropdowns, toasts, dialogues, command palette.
- Motion : `--duration-fast` / `--duration-base` (120–180ms), `--ease-standard`.
- Layout : max 1200px de contenu, gouttière 24px, dense par défaut.

## Correspondance NiceGUI / Quasar & écarts
| Composant Synapse | Base Quasar | Écart / custom |
|---|---|---|
| App shell | q-layout + 2× q-drawer | natif |
| Sidebar groupée | q-drawer + q-list/q-item | groupes + mode icônes (`mini`) → style à surcharger |
| Command palette | q-dialog + q-input + q-list | fuzzy + raccourci ⌘K + nav clavier = custom |
| Study/item row | q-item / div flex | densité + 6 dimensions de statut = template custom |
| Mastery / barres | q-linear-progress | couleur santé via `color` |
| Onglets détail item | q-tabs + q-tab-panels | natif |
| Context / note panel | q-drawer right | rétroliens + note preview = custom |
| Planning semaine | grille CSS custom | pas de planner dense natif ; drag = SortableJS |
| Mode focus | q-dialog maximized | minuteur = timer Python/JS custom |
| Filtres, chips | q-chip / q-btn-toggle | style à surcharger (pas de pills) |
| Courbe d'oubli / graphe notions | SVG custom (ECharts en option) | à raster pour export |
| Clair / sombre | $q.dark + variables CSS | mapper les tokens sur `:root` / `.body--dark` |

**Note.** Quasar impose ses styles (rayons, ombres, ripple). Prévoir une feuille de surcharge : désactiver le ripple, rayons 4/6/8, retirer les ombres sauf popover, forcer la palette de tokens.

## Mapping vers l'arborescence existante
| Vue prototype | Fichier cible | Remplace / fait évoluer |
|---|---|---|
| Aujourd'hui | `pages/dashboard.py` | résumé une ligne + action recommandée + file (au lieu des cartes) |
| Détail item | `pages/course_detail.py` | en-tête synthétique + onglets + panneau (au lieu de 15 cartes) |
| Collèges | `pages/colleges.py` | liste progression enrichie (retard/fragiles/prochaine/QCM) |
| Semestres | `pages/semestres.py` | cartes progression par UE, noms en toutes lettres |
| Items | `pages/items.py` (nouveau) | liste transverse filtrable |
| Révisions | `pages/todo.py` · `planning.py` | file par cycle J3/J7/J14/J30 |
| Planning | `pages/planning.py` | grille semaine + événements Google Calendar |
| QCM | `pages/qcm.py` | analytique + série adaptative |
| Lacunes | `pages/weak_points.py` | liste par statut + sync Obsidian + backlink vivant |
| Statistiques | `pages/stats.py` · `bilan.py` | métriques + temps/collège + activité |
| Revue hebdo | `pages/revue.py` (nouveau) | consolidé / régression + focus semaine |
| Externat | `pages/externat.py` | stages + items rattachés |
| App shell / thème | `frontend/theme.py` | sidebar groupée, tokens, clair/sombre, command palette |

Composants réutilisables à créer sous `frontend/components` : `study_task_row`, `mastery_indicator`, `context_panel`, `command_palette`, `review_timeline`, `compact_calendar`, `focus_bar`, `forgetting_curve`, `relation_graph`.

## Critères d'acceptation
- Page Aujourd'hui : action recommandée visible sans scroll ; répond en <5s à quoi/pourquoi/quelle ressource.
- Une seule couleur porteuse de sens (rouge/ambre/vert = urgence/santé) ; aucun badge coloré décoratif.
- Aucun émoji comme icône ; glyphes géométriques + `<kbd>`.
- Densité : file entièrement scannable, lignes ≤44px, aucune grande carte vide.
- ⌘K, navigation clavier, sélection persistante, panneau contextuel fonctionnels.
- Cohérence clair/sombre sur tous les composants (contraste AA sur texte muted).
- Report = offset depuis la date d'échéance ; date théorique et id préservés.
- Responsive : 3 colonnes ≥1200px ; panneau → drawer 900–1200px ; sidebar icônes 768–900px ; bottom nav <768px.
- Transitions ≤180ms, couleur/bordure/opacité uniquement.

## Assets
- **Polices** : Inter + JetBrains Mono (Google Fonts). Berkeley Mono (spec d'origine) substituée par JetBrains Mono — remplacer si licence disponible.
- **Icônes** : aucune bibliothèque requise ; glyphes géométriques Unicode (○ ◔ ◑ ◕ ◉ ● ◇ ◎ ▤ ▦ ↻ ✓ ⚑ ▧ ⚙ ↗). Si un set réel est souhaité, **Lucide** (traits 1.5–2px) est le plus proche de l'esthétique.
- **Logo** : aucun fourni — wordmark « Synapse » en Inter 600 + pastille « S ». Ne pas inventer de logo.
- **Graphes** (courbe d'oubli, graphe de notions) : SVG inline dans le prototype ; en prod, SVG custom ou ECharts.

## Files
Fichiers de design inclus dans ce bundle (également présents à la racine du projet) :
- `Synapse - Prototype.dc.html` — prototype interactif complet (toutes les vues, clair/sombre, mobile, palette, focus).
- `Synapse - Handoff.dc.html` — spécification visuelle (tokens, composants, interactions, responsive, NiceGUI/Quasar, critères).
- `Synapse Refonte - Analyse & 3 directions.dc.html` — analyse (Linear/Obsidian/à éviter/propre à Synapse), référence du système de statut `#statuts`, et les 3 directions comparées.

Ces fichiers utilisent un runtime maison (`support.js`) et le design system sous `_ds/` : ce sont des **références**, pas du code à porter tel quel.

## Screenshots
Captures hifi de chaque vue dans `screenshots/` :
- `01-aujourdhui.png` — cockpit Aujourd'hui + panneau contextuel
- `02-detail-item.png` — détail item (en-tête + onglets + panneau)
- `03-planning.png` · `04-revisions.png` · `05-colleges.png` · `06-semestres.png` · `07-items.png` · `08-qcm.png` · `09-lacunes.png` · `10-revue-hebdo.png` · `11-statistiques.png` · `12-externat.png`
- `13-items-liste.png` — liste Items
- `14-command-palette.png` — command palette (⌘K)
- `15-mode-focus.png` — mode focus plein écran
- `16-mode-sombre.png` — mode sombre
