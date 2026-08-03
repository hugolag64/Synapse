# Finir 7.4, barème EDN unifié et fuseau métier — Design

**Date :** 2026-08-03  
**Statut :** approuvé par l’utilisateur

## Objectif

Finir le calcul de maîtrise question → item/OIC, utiliser un seul barème EDN dans le parcours QCM/DP, afficher partout la correction propositionnelle, et rendre le fuseau métier configurable entre `Europe/Paris` et `Indian/Reunion`.

## Décisions

### Un seul barème

Toutes les questions fermées utilisent le moteur EDN et exposent `score_mode = "edn"`, y compris lorsque les rangs A/B ne sont pas présents. La grille de score est celle déjà implémentée :

- 0 discordance : 1 point ;
- 1 discordance : 0,5 point ;
- 2 discordances : 0,2 point ;
- 3 discordances ou plus : 0 point.

Les rangs A/B restent des métadonnées affichables. Leur absence ne déclenche pas un second système de notation et ne permet pas d’afficher « Rang A validé ».

Les questions ouvertes/QROC restent à évaluer tant qu’une correction dédiée n’existe pas. Une session qui en contient ne devient pas une preuve EDN complète tant que ces questions n’ont pas reçu de score.

### Maîtrise par question puis item

La source de vérité pour une preuve QCM/DP est `ai_practice_question_items`, jointe aux dernières tentatives scorées des questions de la session.

- Chaque item reçoit la moyenne des scores des seules questions qui lui sont explicitement liées.
- Une question liée à plusieurs items contribue à chacun de ces items.
- `ai_practice_session_items` reste une information de couverture et de navigation ; elle ne sera pas propagée automatiquement aux questions.
- Les anciennes sessions aux rattachements larges ou sans lien question-item restent consultables mais ne produisent pas de preuve de maîtrise par item.
- Une session enregistrée dans la maîtrise est idempotente ; ses évaluations par item ne sont pas recréées au second appel.

Les liens créés à la génération d’une session restent explicites. Les liens futurs pourront être fournis par la source avec `item_number`, `oic_code`, `confidence`, `source` et `classifier_version`.

### Contrat du lecteur

Le backend expose le mode EDN au niveau session et les lignes propositionnelles au niveau de chaque correction. Une ligne contient au minimum :

- identifiant et texte de la proposition ;
- sélection utilisateur ;
- vérité attendue ;
- rang éventuel ;
- points ;
- discordance (`correct`, `omission`, `exces`).

Le lecteur React `qcm_app` et la correction NiceGUI `frontend/components/qcm_replay.py` affichent le même contrat : libellé « Barème EDN propositionnel », score global, score sur 20 et détail des propositions. Le statut « Validé Rang A » est supprimé du lecteur.

### Fuseau métier configurable

La préférence persistée `timezone` accepte exactement :

- `Europe/Paris`, sélectionnée par défaut pour la situation actuelle ;
- `Indian/Reunion`, disponible pour le retour à La Réunion.

Le résolveur central du fuseau :

- utilise la préférence chargée quand elle existe ;
- utilise `APP_TIMEZONE` comme fallback de démarrage ;
- retombe sur `Europe/Paris` si la valeur persistée est invalide.

`now_local()` et `business_today()` reposent sur ce résolveur dynamique. Le planning, les actions rapides et Google Calendar cessent d’utiliser `Indian/Reunion` en dur et consomment le même fuseau courant. Le changement dans Paramètres est persisté immédiatement.

## Flux de données

```text
tentative fermée
  → score_closed_attempt() avec grille EDN
  → tentative + lignes propositionnelles en SQLite
  → finalisation complète de session
  → regroupement des dernières tentatives par question-item
  → une preuve QCM par item réellement lié
  → correction React/NiceGUI avec le même détail
```

```text
Paramètres timezone
  → préférence DataStore
  → résolveur central
  → dates métier, planning, actions et Google Calendar
```

## Gestion des erreurs

- Une question sans tentative scorée bloque la finalisation complète de la session.
- Une erreur de génération d’une lacune ne bloque jamais le score ni l’écriture de la maîtrise.
- Une session sans lien question-item ne crée pas de preuve par item ; elle reste disponible pour la consultation.
- Une valeur de fuseau invalide est rejetée par l’interface et protégée par le fallback `Europe/Paris` côté service.
- Les données propositionnelles absentes sur une tentative historique sont affichées comme indisponibles sans recalculer un faux détail.

## Tests d’acceptation

1. Deux questions d’une session liées à deux items différents produisent deux évaluations avec leurs scores propres.
2. Une session liée uniquement via `ai_practice_session_items` ne produit aucune preuve question-item.
3. La répétition de l’enregistrement de maîtrise ne crée pas de doublons.
4. Une question fermée sans rangs reste en `score_mode = "edn"` et utilise la grille EDN.
5. L’API expose le mode EDN, sa raison éventuelle et les textes des lignes propositionnelles.
6. Le lecteur React affiche le bandeau EDN et les lignes propositionnelles ; la correction NiceGUI expose le même détail.
7. Une QROC non scorée empêche l’enregistrement d’une preuve EDN complète.
8. La préférence `Europe/Paris` puis `Indian/Reunion` modifie `now_local()`, `business_today()`, le planning, les actions rapides et les bornes Google Calendar.

## Hors périmètre

- Reclassification IA de l’arriéré historique UNESS.
- Nouveau barème spécifique aux QROC.
- Calibration statistique des coefficients de rétention.
- Refonte générale de tous les appels à `date.today()` qui ne participent pas aux dates métier ciblées par l’audit.
