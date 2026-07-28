# Refonte UI-UX de l’onglet OIC — Design

## Objectif

Faire de l’onglet OIC de la fiche item un espace de suivi dense, lisible et
actionnable, aligné sur la direction « Linear dominant » du handoff Synapse.
La logique LiSA, l’agrégation, la validation manuelle et l’évaluation IA
restent inchangées.

## Composition retenue

L’onglet est composé de quatre niveaux visuels :

1. Une barre d’outils compacte avec le libellé « Objectifs d’apprentissage »,
   l’état du cache/synchronisation et une action « Actualiser ».
2. Une synthèse horizontale dense indiquant le total d’OIC, la progression Rang
   A, la progression Rang B et le nombre maîtrisé. Les progressions utilisent
   des barres segmentées et des chiffres mono, pas des cartes lourdes.
3. Deux sections Rang A / Rang B avec titre, compteur et séparateur fin.
4. Une liste de lignes compactes : code mono, intitulé, rubrique éventuelle,
   statut de maîtrise, niveau et bouton « Évaluer ». Une ligne maîtrisée est
   désaccentuée par opacité et texte secondaire, sans transformer toute la
   ligne en carte verte.

## Style et interactions

- Utiliser les tokens Synapse : `--bg`, `--surface`, `--surface-hover`,
  `--border`, `--text`, `--text-muted`, `--text-dim`, `--accent`.
- Rayon maximal 8px, bordure 1px, pas d’ombres décoratives ni de pills.
- Les codes, compteurs et niveaux utilisent la police mono.
- L’action d’évaluation reste secondaire visuellement ; le clic de maîtrise
  reste disponible avec un bouton explicite et un tooltip accessible.
- Les états vide, chargement et erreur gardent la même structure de panneau et
  proposent une action de récupération claire.
- Aucun emoji structurel ; les icônes restent des icônes Quasar/NiceGUI.
- La liste doit rester utilisable sur petit écran sans défilement horizontal.

## Périmètre technique

- Modifier `frontend/components/oic_panel.py`, renderer partagé classic/cockpit.
- Ajuster le conteneur OIC de `frontend/pages/course_detail_cockpit.py` si
  nécessaire pour accueillir la toolbar et la synthèse.
- Ajouter des tests de contrat visuel/structurel dans
  `tests/test_course_detail_oic_tab.py` sans tester le HTML NiceGUI au pixel.
- Ne pas modifier la persistance OIC ni le dialogue AnythingLLM.
