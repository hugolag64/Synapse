# Planning — focus de semaine et actions par journée

## Objectif

Transformer l’espace sous la grille Planning en un bloc utile « Focus de la semaine » et rendre chaque journée actionnable sans alourdir la vue principale.

## Décision d’interface

- Conserver la grille hebdomadaire comme élément principal.
- Ajouter dessous un seul bloc compact « Focus de la semaine » contenant :
  - révisions en retard ;
  - prochaine session recommandée ;
  - créneaux libres à utiliser.
- Chaque ligne du focus est cliquable et mène vers l’action ou la vue appropriée.
- Cliquer sur une journée ouvre une modale centrée, avec deux choix :
  - `Planifier un item Synapse` ;
  - `Créer un événement Google Calendar`.
- Les animations restent discrètes : fade/scale à l’ouverture, confirmation courte, apparition progressive du nouvel élément.

## Lisibilité des items

- Vue 7 jours : titre sur maximum 2 lignes, avec ellipsis au-delà ; tooltip au survol avec le titre complet.
- Vue 3 jours : titre sur maximum 3 lignes.
- Vue 1 jour : titre complet avec retour à la ligne naturel.
- Le numéro d’item/titre et les métadonnées de révision restent séparés visuellement.

## Planification d’un item Synapse

- La modale propose une recherche par numéro ou titre.
- L’utilisateur choisit une activité : révision, lecture, QCM ou lacune.
- La durée estimée est préremplie depuis les préférences, mais modifiable.
- La planification est enregistrée localement comme une entrée manuelle attachée à la date choisie.
- Elle ne modifie ni `due_date`, ni l’algorithme de révision, ni la maîtrise de l’item.
- Une option distincte permet de créer aussi un événement Google Calendar.

## Événement personnel Google Calendar

- Champs : titre, heure de début, heure de fin ou durée.
- Création dans le calendrier Google principal (`primary`) via `calendar_service.create_event()`.
- Après création, le planning recharge les événements de la journée.
- Les événements personnels conservent le rendu existant : bordure gauche pointillée et durée affichée.

## Données et sécurité fonctionnelle

- Les événements Google restent la source de vérité pour les événements personnels.
- Les entrées manuelles Synapse sont des données locales de pilotage et ne sont pas poussées dans Notion.
- La création d’un événement ne doit jamais modifier une date de révision sans action explicite séparée.
- Une erreur Google Calendar affiche une notification explicite et ne crée pas d’entrée locale fantôme.

## Vérification

- Tester les retours à la ligne et tooltips en vues 1/3/7 jours.
- Tester l’ouverture de la modale depuis une journée vide et une journée déjà remplie.
- Tester la création locale d’un item sans modification de `due_date`.
- Tester la création Google Calendar, le rechargement et l’affichage de l’événement.
- Tester l’échec Google Calendar sans mutation locale.
