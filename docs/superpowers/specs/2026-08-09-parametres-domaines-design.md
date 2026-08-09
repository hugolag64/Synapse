# Spécification — Paramètres organisés par domaines

Date : 2026-08-09
Statut : design validé pour revue utilisateur
Périmètre : `frontend/pages/settings_cockpit.py`

## Contexte

La vue Paramètres contient actuellement plusieurs familles de réglages affichées dans un flux vertical unique. Les intégrations, l'apparence, la planification, les imports UNESS, LiSA/OIC et les diagnostics sont donc mélangés et donnent l'impression que tout est ouvert en même temps.

La QA navigateur du 2026-08-09 a confirmé que la page fonctionne techniquement, mais que sa hiérarchie visuelle doit encore être finalisée.

## Objectif

Permettre à l'utilisateur de comprendre immédiatement où se trouve chaque réglage, puis d'ouvrir uniquement le domaine qu'il souhaite modifier.

La page doit rester pleine largeur, responsive, accessible au clavier et compatible avec les composants d'action existants.

## Organisation fonctionnelle

La page est composée de six sections indépendantes, repliées par défaut :

| Domaine | Contenu actuel |
| --- | --- |
| Connexions | Notion, Obsidian, Google Calendar, EDNpro, Hypocampus et calendriers associés |
| Apparence et accessibilité | Mode sombre, fuseau horaire et réglages visuels associés |
| Planification EDN | Date cible, date de reprise, visibilité du Sprint et sauvegarde |
| Données UNESS | URL, préparation de l'import, collecte, scan des JSON vérifiés et diagnostic |
| LiSA / OIC | Rafraîchissement des objectifs de connaissance et état de progression |
| Diagnostics et télémétrie | Couverture DP, consommation IA et annales importées |

Les fonctions métier existantes restent dans leurs composants actuels. La refonte porte sur leur composition et leur hiérarchie, pas sur le protocole UNESS, LiSA ou Calendar.

## Comportement d'interface

Chaque en-tête de domaine contient :

- le titre court et stable du domaine ;
- une description d'une ligne ;
- une icône cohérente avec le domaine ;
- un résumé d'état quand il est disponible ;
- un indicateur ouvert/fermé compréhensible au clavier et par lecteur d'écran.

Les sections utilisent le composant d'expansion natif de NiceGUI. Elles sont fermées par défaut à chaque chargement. Une seule section peut être ouverte à la fois afin d'éviter le retour à une page longue et entièrement dépliée.

L'état ouvert/fermé n'est pas persisté dans les préférences lors de cette tranche. Un rechargement ramène donc la page à l'état compact et prévisible.

## États et erreurs

- Une erreur d'action reste affichée dans le domaine qui l'a produite.
- Un statut de connexion distingue `Connecté`, `Non configuré` et `Automatisation à connecter`.
- Une opération en cours conserve son bouton désactivé ou en chargement jusqu'à la fin.
- Les messages de succès et d'échec existants sont conservés, mais ne doivent pas apparaître dans un autre domaine.
- Aucun appel réseau live supplémentaire n'est ajouté au rendu initial.

## Contraintes d'implémentation

- Réutiliser `render_calendar_sources`, `render_uness_diagnostics`, `render_dp_coverage` et les actions déjà présentes.
- Centraliser la structure répétée des en-têtes dans un petit helper local ou un composant dédié, sans déplacer les responsabilités métier.
- Utiliser les tokens CSS existants (`--surface`, `--border`, `--text`, `--text-muted`, `--accent`, etc.).
- Conserver la classe pleine largeur `se-wrap` et vérifier l'affichage sous 820 px.
- Ne pas inclure de secrets ou de valeurs de configuration dans le DOM au-delà des statuts déjà affichés.

## Tests et critères d'acceptation

Tests source :

- chaque domaine possède un titre et une expansion explicitement identifiables ;
- les expansions sont configurées fermées par défaut ;
- les composants UNESS, Calendar, DP et OIC restent branchés ;
- la page conserve `se-wrap` en pleine largeur ;
- les six domaines apparaissent dans l'ordre défini ci-dessus.

QA navigateur :

- `/settings` se charge sans erreur serveur ;
- aucun contenu de domaine n'est visible avant ouverture ;
- l'ouverture d'un domaine ferme le précédent ;
- les boutons d'action restent utilisables après ouverture ;
- la page ne crée pas de colonne vide sur desktop ou mobile.

## Hors périmètre

- La clarification des colonnes `Progression`, `Maîtrise` et `Statut` dans Collèges fera l'objet de la tranche suivante.
- La persistance du domaine ouvert n'est pas incluse.
- La refonte graphique détaillée des formulaires internes n'est pas incluse.
- Aucun changement de modèle de données ou d'API n'est requis.
