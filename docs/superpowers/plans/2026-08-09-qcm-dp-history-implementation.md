# Historique rejouable QCM / DP — Implementation Plan

## Goal

Séparer visuellement les historiques QCM et DP dans le cockpit QCM et exposer
le Tuteur DP sur chaque session DP, sans modifier la persistance ni les
algorithmes de scoring.

## Steps

- [x] Ajouter un test de séparation déterministe QCM/DP, avec compatibilité des
  sessions sans type.
- [x] Ajouter un test de contrat vérifiant les titres `HISTORIQUE QCM`,
  `HISTORIQUE DP` et l’action `Tuteur DP`.
- [x] Ajouter `_split_replayable_history` dans le cockpit.
- [x] Rendre deux sections visibles dans la colonne d’historique, en conservant
  recherche, filtre, sélection et suppression.
- [x] Rebrancher l’action Tuteur DP sur `render_dp_tutor_action`, avec le
  contexte des questions DP historiques.
- [x] Afficher aussi l’action Tuteur DP dans le panneau de session sélectionnée.
- [x] Vérifier les tests ciblés : `30 passed`.
- [x] Vérifier la suite complète : `1315 passed`.
- [ ] Commit/push sur `main`.
- [ ] Déployer sur le homeserver avec la commande documentée.
- [ ] Contrôler `/qcm` dans Chromium après déploiement.

## Commit prévu

`feat: separate QCM and DP replay history`
