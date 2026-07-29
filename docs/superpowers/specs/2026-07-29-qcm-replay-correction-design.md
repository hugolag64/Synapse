# QCM — Rejouer une session et consulter sa correction

Date : 2026-07-29  
Statut : design validé, en attente de relecture écrite

## Objectif

Permettre de retrouver une session QCM générée ou importée, de la rejouer avec les mêmes questions, puis de consulter une correction détaillée avec réponses et explications. L’expérience doit rester lisible lorsque l’historique contient de nombreuses sessions.

Le périmètre ne couvre pas les résultats saisis manuellement avec un simple score : ces entrées restent visibles dans l’analyse, mais ne peuvent pas être rejouées faute de questions conservées.

## Expérience utilisateur

La page QCM conserve son point d’entrée actuel et ajoute trois états complémentaires :

1. **Historique** — liste latérale des sessions générées/importées, triée de la plus récente à la plus ancienne, avec recherche, filtre et score.
2. **Session** — lecteur de questions avec progression, réponse unique ou multiple selon la question, navigation précédente/suivante et possibilité de quitter sans altérer la session source.
3. **Correction** — score final, nombre de bonnes réponses, erreurs à retravailler, durée si disponible, puis liste des questions. Chaque ligne indique correcte/incorrecte et peut être dépliée pour afficher la réponse donnée, la bonne réponse et l’explication.

Après la dernière question, l’utilisateur choisit explicitement de corriger ses réponses. La correction est présentée en vue synthétique dépliable ; un filtre permet de n’afficher que les erreurs. Des actions permettent de revenir à l’historique ou de rejouer la session.

## Modèle de données et flux

Les questions déjà stockées dans `ai_practice_questions` restent immuables. Les réponses sont enregistrées dans les tentatives existantes, rattachées à `ai_practice_sessions`.

- Ouvrir une session lit ses questions et les tentatives précédentes.
- Répondre crée ou met à jour la tentative de l’utilisateur pour la session courante.
- Terminer calcule le score et met à jour l’état de session sans modifier le contenu des questions.
- Rejouer appelle le mécanisme de rejeu existant afin de créer une nouvelle session liée à la session source, avec les mêmes questions.
- La correction lit `answer`, `explanation`, la réponse donnée et le statut de chaque tentative.
- Une session interrompue peut être reprise ; les réponses déjà enregistrées sont restaurées.

Les statistiques globales existantes continuent d’utiliser les résultats QCM canoniques. Le rejeu ne doit pas créer de doublon analytique non maîtrisé ; son enregistrement dans la maîtrise suit le comportement déjà prévu par le service de pratique.

## Découpage technique

- **Historique** : recherche, filtre, tri, sélection de session et état vide.
- **Lecteur de session** : progression, rendu des types de questions existants, restauration des réponses et sauvegarde.
- **Correction** : résumé, filtre « erreurs seulement », accordéons et rendu robuste des explications absentes.
- **Actions** : corriger, reprendre, rejouer, retour historique et notifications d’erreur/succès.

L’intégration se fait dans la page QCM/cockpit actuelle et respecte les tokens et composants de Synapse. Les sessions classiques à score global restent sur leur parcours analytique actuel.

## Cas limites

- session vide ou introuvable : notification claire et retour à l’historique ;
- question ouverte : afficher la réponse attendue et l’explication sans prétendre à une correction automatique si le modèle ne fournit pas de statut fiable ;
- explication manquante : afficher « Explication non disponible » sans bloquer la correction ;
- réponse non renseignée : statut « non répondue » ;
- session interrompue : restauration des réponses déjà sauvegardées ;
- erreur de sauvegarde ou de rejeu : conserver la session affichée et proposer de réessayer.

## Vérification

Les tests doivent couvrir :

- rejeu avec conservation de l’ordre et du contenu des questions ;
- sauvegarde et restauration d’une tentative ;
- score et statuts correcte/incorrecte/non répondue ;
- affichage de la correction et des explications ;
- filtre des erreurs ;
- absence de régression sur les statistiques et sessions QCM existantes ;
- rendu d’une session longue et d’une session sans explication.

## Hors périmètre

- reconstituer les questions de sessions externes dont seul le score a été saisi ;
- édition des questions originales ;
- nouvelle logique de génération IA ;
- refonte des statistiques QCM existantes.
