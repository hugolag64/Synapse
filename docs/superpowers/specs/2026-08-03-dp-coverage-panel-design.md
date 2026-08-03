# Couverture DP par item — rattachements réels et affichage responsive

## But

Afficher, pour chaque collège sélectionné, tous les items réellement associés
aux cours Synapse, y compris les items transversaux. Le panneau ne doit jamais
imposer de défilement horizontal pour lire le nombre de DP.

## Source de données

Le référentiel `data/items_edn.json` reste la source du titre officiel et la
solution de repli pour les items sans cours. Les appartenances à un collège
viennent de `data_store.cours` : chaque `course.item_number` est associé à
toutes les valeurs de `course.college`. Les alias d'un même item sont dédupliqués.

Pour un collège, le panneau affiche l'union des items dont le référentiel donne
ce collège principal et des items rattachés à ce collège par les cours chargés.
Le nombre de DP continue de venir de `local_store.get_dp_count_by_item()`.

## Interface

Les lignes utilisent une grille CSS sans largeur minimale : item, titre et
nombre de DP. En vue « Tous », le collège est affiché dans la ligne de titre
plutôt que comme une colonne rigide. Les titres peuvent se couper sur deux
lignes ; le nombre de DP reste toujours visible à droite. L'ascenseur vertical
reste limité à la liste, sans ascenseur horizontal.

## Tests

- un item rattaché à un collège par un cours apparaît même si son collège
  principal du référentiel est différent ;
- un item ne figure qu'une fois malgré plusieurs cours/alias ;
- les classes CSS de la grille ne permettent pas de débordement horizontal.
