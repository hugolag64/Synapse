# État des lieux Synapse — 29 juillet 2026

## Synthèse

Synapse fonctionne aujourd'hui avec un backend Python et deux surfaces web :

- le cockpit historique en Python/NiceGUI ;
- l'espace QCM interactif en React/Node, intégré sous `/qcm-app`.

Le projet n'est donc pas encore entièrement en Node. Cette séparation est
fonctionnelle, mais elle explique les différences visuelles observées entre le
cockpit, le retour de séance et les QCM.

## Fonctionnalités réalisées récemment

- sessions QCM interactives et corrections détaillées ;
- historique QCM rejouable, suppression des sessions et import JSON ;
- correction du montage React, du routage et des pages blanches ;
- ajustements responsive et réduction de la typographie QCM ;
- récupération LiSA/OIC avec codes d'items normalisés ;
- suggestions de fiches lacunes et questions d'ancrage après échecs répétés ;
- refonte du retour de séance vers un panneau compact inspiré de Linear ;
- correction du pied de validation lorsque les détails avancés sont ouverts ;
- 740 tests Python passent au moment de cette clôture.

## Dette ou vérifications restantes

### Frontends

La cohérence visuelle doit encore être consolidée entre NiceGUI et React. La
prochaine décision structurante sera de garder cette séparation avec un langage
visuel partagé, ou de déplacer progressivement certains écrans vers React.

### QCM et imports

L'import doit afficher un résultat explicite : item reconnu, nombre de questions,
session créée, doublons et erreurs. Les banques importées doivent être
consultables depuis l'item et leur provenance doit rester visible.

### Items, OIC et lacunes

Les objectifs OIC, les sessions QCM, les erreurs et les ancrages doivent devenir
des vues reliées depuis chaque Item. Il faut aussi vérifier les items dont le
code LiSA est fourni avec ou sans zéros initiaux.

### Mémoire pédagogique

Les questions, réponses, corrections et explications doivent être conservées
comme un historique immuable, puis reliées à Obsidian sans écraser les notes
manuelles.

## Ordre recommandé pour la suite

1. Vérification navigateur du nouveau retour de séance.
2. Accusé de réussite détaillé pour l'import QCM.
3. Tests d'intégration QCM + item + maîtrise.
4. Vue Item regroupant QCM, OIC, lacunes et historique pédagogique.
5. Harmonisation visuelle des derniers écrans NiceGUI.
6. Synchronisation Obsidian bidirectionnelle contrôlée.
