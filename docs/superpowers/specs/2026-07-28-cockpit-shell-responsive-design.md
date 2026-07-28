# Shell responsive du cockpit (Étape 17, session 1/3)

## Objectif

Rendre le shell cockpit (`frontend/cockpit_shell.py`) utilisable en dessous de la largeur desktop. Aujourd'hui, aucune media query n'existe : la sidebar reste fixe à 200px (ou 56px en mode « mini »), basculée uniquement à la main via le chevron — en dessous d'une certaine largeur d'écran, elle écrase le contenu sans aucune adaptation automatique.

Cette session couvre uniquement le **shell partagé**, conformément au découpage validé avec l'utilisateur (3 sessions pour l'Étape 17 Responsive du README) :
1. **Shell responsive** (cette session) — bénéficie à tous les écrans cockpit d'un coup, zéro dépendance.
2. Panneau contextuel → drawer 900–1200px, écran par écran (session ultérieure).
3. Mise en page mobile dédiée pour Aujourd'hui, README §16 (session ultérieure).

Le contenu propre à chaque page n'est pas retouché ici — seul le chrome (sidebar / topbar / bottom nav) s'adapte.

## Design

Trois paliers, conformes au README (règle générale Responsive) :

**≥900px — inchangé.** Sidebar 200px, bascule manuelle 200↔56 (chevron) disponible comme aujourd'hui.

**768–900px — icônes forcées.** La sidebar prend automatiquement l'apparence du mode « mini » actuel (56px, labels/groupes/wordmark masqués) via une media query qui applique directement les règles déjà écrites pour `.cockpit-sidebar.mini` à la classe de base dans cette plage — indépendamment de l'état du toggle manuel. Le chevron est masqué dans cette plage (la bascule manuelle n'aurait plus d'effet visible, donc plus de sens).

**<768px — sidebar remplacée par topbar + bottom nav.**
- La sidebar (`<aside>`) est masquée (`display:none`).
- Une **topbar mobile** fixe en haut (nouvel élément, ~52px) : logo « S » + icône recherche qui ouvre la palette de commandes existante (`open_command_palette`, rien de nouveau côté palette). Décision validée : pas de lien « Vue classic » sur mobile (retour au desktop classic n'a pas de sens sur téléphone ; reste accessible depuis Paramètres si besoin un jour — non traité ici, aucun changement dans `settings_cockpit.py`).
- Une **bottom nav** fixe en bas (nouvel élément, ~56px), 5 entrées conformes au README §16 et validées avec l'utilisateur telles quelles : Aujourd'hui (`/`) · Planning (`/planning`) · Révisions (`/todo`) · Items (`/items`) · Points faibles (`/lacunes`). Mêmes glyphes que la sidebar (◉ ▦ ↻ ≡ ⚑), icône + libellé court empilés verticalement (pattern bottom-nav standard), page active surlignée en `--accent` — même logique `active` déjà calculée par `_TITLE_TO_NAV`, réutilisée telle quelle. Pas de badges (compteur révisions, point lacunes) sur cette version — le README ne les décrit pas pour la bottom nav et ça reste un ajout simple à faire plus tard si besoin.
- `.cockpit-main` perd sa marge gauche (`margin-left:0`) et son padding devient `68px 16px 76px` (haut = hauteur topbar + espace ; bas = hauteur bottom nav + espace ; côtés resserrés à 16px) pour ne jamais passer sous les barres fixes.

Aucun nouveau fichier : tout vit dans la feuille `_SIDEBAR_CSS` existante (une media query ajoutée par palier) et dans `cockpit_frame()` (deux nouveaux blocs d'éléments, topbar mobile et bottom nav, construits une fois au même titre que la sidebar — visibilité gérée entièrement en CSS, pas de logique Python conditionnelle sur la largeur).

## Portée

Modifié : `frontend/cockpit_shell.py` uniquement. Aucun autre fichier cockpit touché — chaque page hérite du nouveau comportement via `cockpit_frame()` sans modification propre. Le contenu de chaque page peut rester imparfait sur mobile pour l'instant (sujet des sessions 2 et 3). Chemin classic (`theme.frame`) non touché.
