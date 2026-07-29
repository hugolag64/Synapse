# Refonte Linear du retour de séance

## Statut

Proposition à valider avant planification et implémentation.

## Contexte

Le retour de séance actuel est un grand formulaire modal issu de l'ancienne interface NiceGUI. Il fonctionne, mais il est visuellement éloigné du cockpit Synapse et demande trop de décisions simultanées.

Le dossier `design_handoff_synapse_refonte` définit une interface plus proche de Linear : dense, lisible, contextuelle, avec peu de couleurs sémantiques, des bordures fines, une hiérarchie typographique claire et des actions directement reliées à l'item.

## Objectifs

- Permettre de valider une séance en quelques secondes.
- Montrer clairement quel item est mis à jour.
- Ne conserver à l'écran que les informations utiles à la majorité des séances.
- Adapter les champs au type d'activité, notamment QCM/DP/KFP.
- Relier immédiatement la validation à la maîtrise, aux lacunes et aux ressources de l'item.
- Préserver les traitements métier existants : évaluation, maîtrise, prochaine révision et création de lacunes.

## Décision UX recommandée

Remplacer le grand modal par un panneau contextuel de validation, ouvert depuis l'item ou le cockpit. Sur grand écran, il s'affiche comme un drawer latéral droit ; sur petit écran, il devient une page ou un bottom sheet pleine largeur.

Le panneau doit rester suffisamment compact pour laisser apparaître l'item derrière lui. Il ne doit pas ressembler à une nouvelle page indépendante.

## Structure de l'interface

### 1. En-tête contextuel

Afficher :

- bouton de fermeture ;
- libellé discret `RETOUR DE SÉANCE` ;
- identifiant et titre de l'item, par exemple `ITEM 162 · IST n°2 : Syphilis et ulcérations des muqueuses` ;
- éventuellement la matière ou le collège en texte secondaire.

Ajouter des liens rapides compacts vers `Ouvrir l'item`, `Lacunes`, `QCM` et `Ressources` lorsque ces données existent.

### 2. Résumé de la séance

Le titre est `Comment s'est passée cette séance ?`.

Présenter une ligne de synthèse avec quatre valeurs :

- activité ;
- durée ;
- résultat si l'activité est un QCM/DP/KFP ;
- confiance.

Ces valeurs sont mises à jour immédiatement lorsque l'utilisateur modifie les contrôles.

### 3. Activité

Utiliser une sélection compacte en ligne, avec un état sélectionné violet et des états non sélectionnés neutres. Éviter les gros boutons arrondis de type formulaire.

Activités disponibles : `Révision`, `Lecture`, `QCM`, `DP/KFP`, `Anki`, `Fiche`, `Correction`.

L'activité est préremplie à partir du contexte d'ouverture :

- depuis une session QCM : `QCM` ;
- depuis Anki : `Anki` ;
- depuis la lecture d'un PDF : `Lecture` ;
- sinon : dernière activité connue ou `Révision`.

### 4. Champs essentiels

Afficher par défaut uniquement :

- durée, avec les valeurs courantes `5`, `10`, `20`, `30`, `45`, `60`, `90` minutes et une option personnalisée ;
- confiance, sous forme d'une échelle textuelle 1 à 5 : `Très incertain`, `Incertain`, `Correct`, `Solide`, `Très solide` ;
- difficulté : `Facile`, `Moyenne`, `Difficile`.

Les contrôles doivent être compacts, alignés et accessibles au clavier. Aucun emoji ne doit être nécessaire pour comprendre la valeur.

### 5. Champs spécifiques au QCM/DP/KFP

Afficher uniquement lorsque l'activité est concernée :

- résultat : `Réussi`, `Moyen`, `Raté` ;
- score chiffré si disponible ;
- lien vers la correction et la session rejouable.

Si le résultat est `Moyen` ou `Raté`, proposer sans imposer :

- `Créer une fiche lacune` ;
- `Créer une question d'ancrage` ;
- type d'erreur EDN, dans les détails avancés.

La proposition doit réutiliser le mécanisme existant de suggestion après échecs répétés et ne pas créer automatiquement une fiche sans action explicite.

### 6. Détails avancés

Section repliée par défaut, intitulée `Détails avancés`.

Lorsqu'elle est ouverte, elle contient :

- type d'erreur : diagnostic, clinique, examens, traitement, complication, physiopathologie, piège EDN, valeur chiffrée, autre ;
- résultat détaillé QCM/DP lorsque disponible ;
- commentaire libre court ;
- contexte ou notion ciblée.

Les détails doivent rester facultatifs et ne doivent jamais bloquer la validation.

### 7. Conséquence et validation

Avant le bouton principal, afficher une phrase discrète :

> Cette validation mettra à jour la maîtrise de l'item et sa prochaine révision.

Le pied du panneau contient :

- `Annuler` comme action secondaire ;
- `Valider la séance` comme action primaire ;
- raccourci clavier `Ctrl/Cmd + Entrée` si compatible avec l'application.

Après validation, fermer le panneau et afficher un toast court avec les conséquences principales, par exemple : `Séance enregistrée · maîtrise mise à jour · prochaine révision dans 3 jours`.

## Connexion au modèle Synapse

La validation doit continuer à alimenter les mêmes opérations métier que l'écran actuel :

- enregistrement de l'activité et de la durée ;
- évaluation de confiance et de difficulté ;
- mise à jour de la maîtrise de l'item ;
- planification de la prochaine révision ;
- enregistrement du résultat QCM/DP/KFP ;
- alimentation des lacunes et des suggestions d'ancrage.

Le panneau doit recevoir un contexte d'item explicite plutôt que reconstruire le titre ou l'identifiant depuis du texte d'interface.

## Direction visuelle

- largeur drawer recommandée : 440 à 520 px ;
- fond blanc, bordure `#e4e4e7`, ombre légère uniquement sur le drawer ;
- accent violet `#5e6ad2` réservé à la sélection et à l'action primaire ;
- succès, attention et erreur utilisés uniquement pour les résultats ;
- rayon maximal 8 px ;
- pas de gros conteneur blanc flottant dans un overlay gris ;
- pas de boutons ovales surdimensionnés ;
- labels courts en petites capitales ou texte secondaire ;
- typographie et espacements alignés sur le handoff Linear.

## États à couvrir

1. Ouverture depuis un item sans activité préexistante.
2. Ouverture depuis une session QCM avec résultat connu.
3. Changement d'activité avec apparition/disparition des champs spécifiques.
4. Détails avancés ouverts puis refermés.
5. Validation réussie.
6. Erreur d'enregistrement avec conservation des saisies.
7. Fermeture avec modifications non enregistrées : demander confirmation uniquement si nécessaire.
8. Affichage mobile ou fenêtre étroite.

## Critères d'acceptation UX

- L'utilisateur identifie l'item et l'effet de la validation sans lire toute l'interface.
- Une séance standard peut être validée avec activité, durée, confiance et difficulté sans ouvrir les détails avancés.
- Les champs QCM/DP/KFP n'encombrent pas les activités qui ne les utilisent pas.
- Le panneau est visuellement cohérent avec le cockpit, les pages item et le handoff Linear.
- Aucun emoji ou bouton géant n'est requis pour comprendre ou compléter le formulaire.
- Les actions `Lacunes`, `QCM` et `Ressources` restent accessibles depuis le contexte de l'item.
- Les résultats de maîtrise et de planification restent identiques à comportement métier équivalent.

## Hors périmètre de cette refonte

- Modification de l'algorithme de maîtrise.
- Modification de la notation QCM.
- Refonte globale du cockpit ou des pages item.
- Création automatique de fiches lacunes sans confirmation.
- Suppression des anciennes données de séances.

## Plan de migration proposé

1. Créer le composant de panneau contextuel en conservant le contrat de callback existant.
2. Mapper les champs actuels vers le nouveau modèle d'affichage.
3. Ajouter les champs conditionnels QCM/DP/KFP et les raccourcis item.
4. Remplacer l'ouverture du modal actuel depuis le cockpit et les pages item.
5. Vérifier les calculs de maîtrise, la planification et les suggestions de lacunes.
6. Supprimer les styles et composants spécifiques à l'ancien grand modal après validation visuelle.
