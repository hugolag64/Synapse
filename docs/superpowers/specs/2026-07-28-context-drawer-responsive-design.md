# Panneau contextuel vers drawer responsive — Design

**Étape 17, session 2/3 — 900–1200 px**

## Objectif

Transformer les panneaux contextuels secondaires du cockpit en drawers superposés entre 900 et 1200 px, écran par écran, sans modifier le chemin classic ni les données métier.

## Décision

Une primitive de présentation partagée sera ajoutée dans `frontend/components/responsive_drawer.py`. Elle fournira les classes, attributs ARIA et le comportement commun du drawer : scrim, fermeture par bouton, `Escape`, clic extérieur et restitution du focus. La logique métier restera dans chaque page.

Le drawer sera visible automatiquement lorsqu’un panneau existe et que la largeur CSS est comprise entre 900 px inclus et 1200 px exclus. À 1200 px et plus, le panneau restera dans la grille/colonne latérale existante. Sous 900 px, la primitive ne forcera pas de nouveau comportement : les règles 768–900 px du shell et le traitement mobile <768 px restent prioritaires.

## Écrans couverts

- Aujourd’hui : le panneau `context_panel` devient un drawer droit ; la sélection de tâche, les actions Terminer/Reporter/Focus et la fermeture restent branchées sur les callbacks existants.
- Détail item : le panneau `.ci-panel` devient un drawer droit ; les onglets, les liens et les panneaux OIC restent inchangés.
- Révisions et Collèges : auditer les panneaux de pilotage existants et appliquer le même pattern s’ils sont secondaires à la liste principale.
- QCM et Items : aucun drawer artificiel ; ces écrans n’ont pas de panneau contextuel secondaire dans le cockpit actuel.

## Structure et comportement

La primitive ne crée pas de logique de sélection et ne connaît pas les objets métier. Elle fournit un conteneur `responsive-drawer`, un état ouvert/fermé côté DOM et des hooks de fermeture utilisables par NiceGUI. Le panneau reste rendu pour éviter de reconstruire son contenu lors de chaque bascule de largeur.

Entre 900 et 1200 px : le drawer est positionné à droite, avec largeur bornée par le panneau existant et la largeur disponible, hauteur viewport, `z-index` supérieur au contenu et scrim derrière. Le focus est placé sur le bouton de fermeture à l’ouverture ; `Escape` et le clic sur le scrim déclenchent le même callback que `✕`. La fermeture ne détruit pas la tâche sélectionnée ; elle masque le panneau et conserve la sélection, afin qu’un bouton « Contexte » puisse le rouvrir.

À ≥1200 px : scrim, position fixe et contrôles de drawer sont désactivés ; la mise en page originale est conservée.

À <900 px : aucune règle de cette session ne doit écraser les règles mobile existantes. Le détail item pourra suivre le traitement mobile dédié de la session 3 si nécessaire.

## Contraintes

- Réutiliser les tokens CSS existants ; aucune couleur, spacing ou durée arbitraire.
- Ne pas injecter de style dans un callback post-load : `ui.add_head_html` doit rester synchrone au build.
- Ne pas toucher au backend ni au chemin classic.
- Conserver les dimensions et transitions ≤180 ms.
- Utiliser des glyphes existants, sans emoji comme icône.

## Validation

Les tests couvriront la logique pure de classe/breakpoint et les callbacks de fermeture. La vérification manuelle ciblera 1200, 1000, 900, 899 et 768 px, en clair et sombre, avec sélection/fermeture/réouverture et navigation vers le détail item.
