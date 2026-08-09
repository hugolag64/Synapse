# Synapse — vocabulaire métier

## Item

Un item est une unité de connaissance EDN canonique. Il existe une seule fois au niveau du programme, même s’il est rattaché à plusieurs collèges dans Synapse.

## Collège

Un collège est un contexte de classement, d’affichage et de révision d’un item dans Synapse. La présence d’un item dans plusieurs collèges ne crée pas plusieurs connaissances indépendantes.

## Cours Synapse

Un cours Synapse est une représentation contextuelle d’un item dans un collège. Plusieurs cours Synapse peuvent donc pointer vers le même item canonique.

## Note Obsidian canonique

Une note Obsidian représente la connaissance interconnectée d’un item canonique. La règle normale est une seule note par item, partageable depuis tous les collèges Synapse auxquels l’item est rattaché.

## Liaison Obsidian

La liaison doit résoudre l’item canonique avant son collège d’affichage. Un cours Synapse doit pouvoir afficher la note canonique de son item même si la note est physiquement rangée dans le dossier d’un autre collège.

Une absence de note dans le dossier du collège courant ne constitue donc pas une absence de note pour l’item.

## Conséquence métier

Les identifiants et relations doivent distinguer l’item canonique, les cours Synapse contextuels et la note Obsidian canonique. Les opérations de synchronisation ne doivent ni créer une note par collège ni choisir silencieusement un alias lorsqu’un item possède plusieurs cours.

## Boucles de révision

### Lecture initiale

La lecture initiale est le cycle court J3/J7/J14/J30 dÃ©clenchÃ© par une date de premiÃ¨re lecture. Il transforme une premiÃ¨re exposition en historique de rÃ©vision validÃ©. Une date historique doit Ãªtre accompagnÃ©e de validations synthÃ©tiques du cycle si les lectures ont Ã©tÃ© faites avant Synapse.

### Consolidation

La consolidation est la boucle longue SM-2 qui prend le relais aprÃ¨s un cycle J3/J7/J14/J30 complet. Elle signifie que l'item est assez avancÃ© pour Ãªtre entretenu dans le temps, pas qu'il est parfaitement maÃ®trisÃ©.

### Reprise historique

Une reprise historique est une dÃ©claration locale et rÃ©versible d'un travail effectuÃ© avant Synapse. Elle peut crÃ©er des preuves synthÃ©tiques datÃ©es sans prÃ©tendre reconstituer le dÃ©tail exact de chaque sÃ©ance, et ne doit pas Ã©craser les preuves rÃ©elles.
