# Composition d’épreuve officielle — Design

## Objectif

Remplacer la sélection aléatoire du simulateur par une composition serveur,
figée et rejouable, compatible avec le lecteur React actif. Une épreuve est
créée à partir des questions UNESS déjà importées ; aucun appel IA n’est requis.

## Formats

- `dp`: trois dossiers progressifs distincts, avec toutes leurs questions dans
  l’ordre d’origine ;
- `series`: vingt questions isolées, sans deux questions du même dossier ;
- `mixed`: deux dossiers progressifs puis dix questions isolées non déjà
  sélectionnées.

Chaque format possède une durée par défaut configurable (DP 3 h, série 1 h 30,
mixte 2 h). Une durée explicitement fournie par l’interface est prioritaire.

## Sélection déterministe

`compose_exam_session()` reçoit un format, un sujet optionnel et un seed. Les
candidats sont lus depuis `ai_practice_questions` et leurs liaisons de sessions
UNESS. Un score local combine fréquence EDNpro, signaux d’erreur récents et
ancienneté de la dernière pratique. Le score devient un poids borné ; un
`random.Random(seed)` effectue ensuite le tirage pondéré. Le seed, le format,
la durée et les identifiants sélectionnés sont persistés dans
`exam_compositions`, relié à la session de pratique.

## Intégrité serveur

Les sessions composées portent `exam_mode`, `exam_format`, `exam_seed` et
`duration_seconds`. Une tentative en mode examen n’est acceptée que pour la
prochaine position non répondue ; une tentative hors ordre est rejetée côté
serveur. Les tentatives `timed_out` peuvent toutefois compléter toutes les
positions lorsque le chrono expire.

## Flux et UX

La page de configuration existante appelle le composeur et ouvre le lecteur
React avec `exam=1` et la durée persistée. Le lecteur conserve l’ordre, masque
les rangs pendant l’épreuve et affiche le débrief après finalisation. La
composition n’est pas recalculée pendant une session.

## Tests d’acceptation

- même seed, même format et même corpus produisent la même composition ;
- un seed différent peut produire une composition différente ;
- DP, série et mixte respectent leurs cardinalités et l’absence de doublons ;
- la session et `exam_compositions` conservent seed/format/durée/ordre ;
- une tentative hors ordre est refusée, une tentative timeout reste autorisée ;
- le endpoint/page ouvre le lecteur React avec la durée de l’épreuve ;
- les épreuves sans candidats suffisants échouent avec un message explicite.
