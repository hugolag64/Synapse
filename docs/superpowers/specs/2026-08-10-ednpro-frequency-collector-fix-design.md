# Correctif du collecteur de fréquences EDNpro

## Objectif

Rendre la synchronisation EDNpro fidèle à la page `/training-v2`, en
conservant pour les 367 items le nombre exact de sessions, le nombre de
questions d’annales, les années de passage et la priorité affichée.

## Cause identifiée

Le collecteur écoute les réponses JSON générales de la page et les envoie à
un normaliseur qui ne connaît pas le format réel de `get_annales_items_index`.
Le flux correct contient `item_number`, `nb_sessions`, `nb_questions` et
`annees`. Sans ce mapping, les lignes peuvent être interprétées comme des
items sans fréquence et la synchronisation peut produire un snapshot vide ou
incorrect.

## Conception retenue

Le navigateur authentifié reste la source de session : aucun token n’est
exporté ni persisté par Synapse. Le collecteur déclenche depuis le contexte de
la page authentifiée un appel au RPC `get_annales_items_index`, récupère sa
réponse et la transmet au normaliseur existant.

Le normaliseur accepte les champs EDNpro réels :

- `nb_sessions` devient `session_count` ;
- `nb_questions` devient `question_count` ;
- `annees` devient `years` ;
- la priorité est dérivée de `nb_sessions` : 0, 1, 2 ou au moins 3 sessions.

Le snapshot final est complété avec les items absents du RPC comme « jamais
tombés », afin de conserver les 367 items du référentiel. Une écriture est
refusée si la réponse est vide, invalide, dupliquée ou ne permet pas de
reconstituer les 367 items attendus.

## Vérification et tests

Les tests couvriront :

1. la normalisation d’un payload réel `get_annales_items_index` ;
2. la dérivation des quatre priorités depuis le nombre de sessions ;
3. le refus d’un snapshot incomplet ou vide ;
4. la conservation du comportement de synchronisation via CDP et du mode
   authentification requis.

La validation manuelle finale comparera les totaux 205/57/67/38 et plusieurs
items connus avec la page EDNpro authentifiée.
