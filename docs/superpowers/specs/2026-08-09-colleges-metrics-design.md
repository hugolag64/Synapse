# Spécification — Métriques explicites dans la vue Collèges

Date : 2026-08-09
Statut : design validé pour revue utilisateur
Périmètre : `frontend/pages/colleges_cockpit.py`

## Problème

La colonne actuellement nommée `Progression` affiche le score de maîtrise lorsqu'il existe, ou `100 %` dès qu'un cours possède une date de première lecture. Elle mélange donc deux concepts différents. Le panneau `Pilotage global` présente également des agrégats qui ne permettent pas de distinguer lecture, maîtrise et rétention.

## Contrat métier

### Avancement de lecture

L'avancement de lecture mesure uniquement si le cours a été lu :

- `Lu` si `date_1ere_lecture` existe ;
- `Non lu` sinon ;
- si le collège est `valide`, tous ses cours sont présentés comme `Lu`, même si leur date individuelle est absente.

La validation d'un collège est une règle de présentation et de pilotage. Elle ne modifie ni `date_1ere_lecture`, ni l'historique, ni la maîtrise calculée.

### Maîtrise

La maîtrise utilise exclusivement le score produit par le moteur de maîtrise :

- score numérique en pourcentage lorsqu'une preuve est disponible ;
- `—` lorsqu'aucun score n'est disponible.

Un cours lu n'est donc pas automatiquement maîtrisé.

### Statut

Le statut est le libellé interprétable dérivé du niveau de maîtrise ou de l'absence de lecture : `À lire`, `En cours`, `Fragile`, `Solide`, `À réviser` selon les valeurs déjà normalisées par le composant de statut.

Le statut de validation du collège (`Confirmé manuellement`, `Validation automatique proposée`, etc.) reste affiché dans l'en-tête du collège et ne remplace pas le statut pédagogique de chaque cours.

## Grille cible

La grille des items affiche les colonnes suivantes dans cet ordre :

1. `Item`
2. `Lecture`
3. `Maîtrise`
4. `Statut`
5. `Retard`
6. `Prochaine`
7. `QCM`
8. action

La colonne `Fragile` est supprimée : elle est redondante avec `Maîtrise` et `Statut`. Les signaux de retard et de prochaine révision restent indépendants.

Le header et chaque ligne doivent utiliser le même template CSS afin de conserver l'alignement horizontal.

## Pilotage global

Le panneau latéral distingue explicitement :

- `Avancement de lecture` : cours lus / cours total ;
- `Maîtrise moyenne` : moyenne des scores de maîtrise disponibles, avec `—` si aucun score n'est disponible ;
- `Rétention` : valeur séparée lorsqu'elle est fournie par les données agrégées ;
- `Répartition des statuts` : compte des niveaux pédagogiques.

Les cours considérés lus uniquement par la validation du collège sont inclus dans l'avancement de lecture, mais pas artificiellement dans la moyenne de maîtrise.

## Filtres et signaux

- Le filtre `Jamais lus` exclut un collège `valide`, car tous ses items sont présentés comme lus.
- Le filtre `En retard` conserve sa source actuelle basée sur les tâches urgentes.
- `Sans PDF` conserve sa source actuelle et n'est pas influencé par le statut de validation.
- La validation d'un collège ne masque pas ses retards ni ses lacunes de maîtrise.

## Contraintes

- Aucun changement de calcul dans `backend/core/reviews/mastery.py` n'est requis.
- Aucun changement de date de lecture ou d'historique ne doit être effectué.
- Les scores QCM restent les derniers scores par cours.
- Les états existants `non_commence`, `correct`, `solide`, `fragile`, `critique` restent compatibles avec `status_label` et `status_class`.
- La grille reste responsive avec un débordement horizontal contrôlé sur petit écran.

## Tests et critères d'acceptation

Tests source et unitaires :

- un cours lu sans score produit `lecture=Lu`, `mastery=—` et un statut non maîtrisé explicite ;
- un cours non lu avec score absent produit `lecture=Non lu`, `mastery=—` et `statut=À lire` ;
- un collège validé force `lecture=Lu` et l'avancement à 100 % sans créer de score de maîtrise ;
- la grille contient `Lecture`, `Maîtrise`, `Statut`, `Retard`, `Prochaine` et `QCM`, mais plus de colonne `Fragile` ;
- le panneau global contient des libellés séparés pour lecture, maîtrise et rétention.

QA navigateur :

- les titres des colonnes sont alignés avec les données ;
- un collège validé affiche 100 % de lecture ;
- une ligne lue sans preuve de maîtrise affiche `Lu`, `—` et un statut distinct ;
- aucun score de maîtrise n'est inventé par la validation du collège.
