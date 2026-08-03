# Boucle d'entraînement fiable (7.1–7.7) — conception

## Objectif

Garantir qu'une tentative QCM, DP ou KFP produit un résultat juste, complet, traçable et utilisable par la maîtrise, le planning et les vues d'historique. Une session incomplète ne doit jamais devenir une preuve de maîtrise.

## Décisions de conception

### 1. Cycle de vie et idempotence (7.1, 7.3)

`ai_practice_sessions` reçoit un état persistant : `draft`, `submitted`, `scored`, `recorded` et `abandoned`. Les sessions existantes terminées sont migrées vers `recorded` lorsqu'elles ont déjà `mastery_recorded_at`, sinon vers `scored`; les autres deviennent `draft`.

Une finalisation ne réussit que si chaque question possède une dernière réponse non vide et, pour une question ouverte, une évaluation. Sinon le service renvoie un résultat `incomplete` décrivant les positions restantes, sans modifier `completed_at`, `score_percent` ou la maîtrise. La finalisation et l'enregistrement de maîtrise ont chacun un chemin idempotent : un second appel renvoie le même résultat sans créer une seconde évaluation.

La détection de lacune est exécutée après la transaction de score. Toute erreur dans ce traitement auxiliaire est journalisée et ne modifie jamais le statut de la session ni la correction renvoyée. La lecture du texte de question utilise la colonne existante `prompt`.

### 2. Scoring propositionnel et transparence EDN (7.2)

Une migration ajoute `ai_practice_attempt_propositions`, une ligne par proposition d'une tentative corrigée : identifiant de proposition, sélection de l'étudiant, vérité, rang éventuel, points, et type de discordance (`omission`, `exces`, `correct`). Les réponses brutes restent conservées dans `ai_practice_attempts.response` pour compatibilité.

Le serveur est la seule source de correction. Il normalise la réponse, construit les lignes de proposition, puis applique `compute_edn_score()` pour une question fermée si les rangs sont disponibles et fiables. Sinon il applique un score d'entraînement et renvoie `score_mode` (`edn` ou `training`) ainsi que la raison de non-calibration. L'API et le lecteur affichent « score d'entraînement non calibré EDN » si `score_mode=training`; aucun badge ni libellé « Note EDN » n'est alors montré. Les questions ouvertes ne deviennent corrigées qu'après score explicite, et ne sont jamais artificiellement comptées à zéro.

### 3. Attribution par question et maîtrise (7.4, 7.5)

Une migration ajoute `ai_practice_question_items` : `question_id`, `item_number`, `oic_code` optionnel, `confidence` entre 0 et 1, `source` (`manual`, `rule`, `ai`) et `classifier_version`. Pour les nouvelles sessions, l'item principal de la question est inséré comme lien fiable. Les classifications ultérieures peuvent ajouter des liens supplémentaires.

Les anciennes sessions multi-items ne sont pas rétroactivement converties en preuves fortes : elles conservent leur visibilité et ne produisent qu'une exposition. Une évaluation de maîtrise dérivée d'une session utilise uniquement les questions liées à l'item concerné. Sans lien question-item fiable, aucune évaluation de maîtrise n'est créée.

Le calcul de maîtrise sépare exposition (un QCM a été fait), performance (une note récente pondérée par le nombre de questions) et diagnostic (erreurs reliées à un item ou OIC). Une performance fraîche faible crée une pénalité explicite et une prochaine action de correction; un résultat réussi ne peut pas effacer cette pénalité sans nouvelle performance suffisamment haute.

### 4. Rétention robuste et calibrable (7.6)

Le jeu de preuves canoniques est agrégé par `(item, objectif, source, jour métier)`. La meilleure preuve de chaque groupe est conservée, donc plusieurs rejouages courts le même jour ne multiplient jamais la stabilité. L'effet de séance est plafonné et un gain de stabilité majoré n'est accordé qu'à une récupération espacée.

Chaque calcul de rétention persiste une prédiction de rappel et sa date. Lors d'une performance ultérieure, elle est rapprochée de la prédiction pour rendre disponibles le Brier score et des groupes de calibration. Les nouveaux champs sont additifs; les historiques existants restent lisibles.

### 5. Temps métier unique (7.7)

`backend.config.settings` expose une préférence IANA unique, `Europe/Paris` par défaut, et des fonctions `now_local()` et `business_today()`. Le stockage local, planning, actions rapides et Google Calendar utilisent ces fonctions. Les timestamps déjà offset-aware ne sont pas réécrits; seuls les nouveaux calculs de jour et les plages Calendar utilisent le fuseau configuré.

## Interfaces prévues

- `finalize_ai_practice_session(session_id)` retourne soit un résumé `scored`, soit un résumé `incomplete` avec les positions manquantes.
- `record_ai_practice_mastery(session_id)` ne finalise plus la session ; il consomme uniquement une session `scored` et devient `recorded` une fois.
- `POST /api/qcm/sessions/{id}/complete` renvoie HTTP 409 avec les questions manquantes lorsqu'une session n'est pas soumise, sinon le même débrief et le même score lors d'appels répétés.
- Les sessions et corrections exposent `score_mode`, `completion_state` et les lignes de proposition corrigées.

## Sécurité et compatibilité

Toutes les migrations SQLite sont idempotentes. Les API de lecture existantes continuent à fonctionner avec les sessions historiques. Aucun appel réseau, IA ou écriture externe n'est nécessaire au lot.

## Tests d'acceptation

1. Une réponse erronée finalise le QCM, fournit sa correction et crée au plus une lacune non bloquante.
2. Une session avec réponse manquante ou ouverte non évaluée retourne 409 et ne modifie pas la maîtrise.
3. Une question dont les rangs sont connus utilise le barème EDN; sans rang, elle porte explicitement le mode `training`.
4. Un DP lié à deux items ne modifie que l'item des questions effectivement reliées; une session historique transverse ne crée pas de maîtrise forte.
5. Un QCM faible récent baisse le signal de performance; deux répétitions le même jour n'augmentent pas deux fois la stabilité.
6. À proximité de minuit, les modules utilisent la même date `Europe/Paris` et les événements Calendar portent ce fuseau.
