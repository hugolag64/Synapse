# Design — Diagnostic UNESS (Paramètres) + import partiel des questions non vérifiables

## Contexte et objectif

Session de debug du 2026-08-01 sur le pipeline UNESS (collecte → correction
Gemini → import) : plusieurs pannes silencieuses corrigées une à une à la main
(quiz jamais importés, quiz jamais même tentés après un crash, quiz bloqué en
entier à cause d'une seule question). Deux problèmes de fond restent :

1. **Pas de vue d'ensemble.** Rien dans l'app ne dit « cette annale a 6/8 quiz
   importés, voici pourquoi les 2 autres manquent ». Il faut recompter les
   fichiers sur le disque et croiser 3 tables à la main pour le savoir — ce que
   cette session a fait manuellement plusieurs fois.
2. **Un seul verrou technique bloque tout un quiz.** `assert_verified_exam`
   rejette l'import complet d'un quiz dès qu'une question a
   `verification_status == "unsupported"` (image que l'IA n'a pas pu analyser),
   alors que le reste du quiz est parfaitement valide. Cas réel : SQI1 de
   Dermatologie, 1 question sur 4 concernée, quiz entier rejeté.

Décisions validées avec l'utilisateur avant ce design :
- Périmètre strictement UNESS (pas un debug IA général — QCM ChatGPT/Gemini
  hors sujet).
- Page dédiée dans **Paramètres**, pas une extension des cartes `/annales`.
- Les actions du panneau sont **directement exécutables** (Relancer, Importer),
  pas de simple pointeur vers l'UI existante.
- Une question `unsupported` est **conservée** dans le quiz importé, marquée
  visuellement, plutôt qu'exclue silencieusement.

Le point 2 est un prérequis du point 1 : sans lui, le panneau de diagnostic
aurait un statut "❌ Bloqué" beaucoup trop fréquent (toute question avec une
image non fournie à l'IA), qui doit en réalité être rarissime après le fix
(seulement si même la réponse officielle UNESS manque).

## Partie A — Import partiel malgré une question non vérifiable

### Problème précis

`gemini_conversion._question()` fixe déjà `verification_status = "unsupported"`
quand une image n'a pas pu être fournie à Gemini, mais laisse le verdict/
explication de Gemini tels quels sur les propositions — alors que le prompt
demande à Gemini de ne pas se prononcer sur une image non vue, rien ne
garantit qu'il s'en tient à cette consigne. `import_service.assert_verified_exam`
rejette ensuite tout l'examen dès qu'une question porte ce statut.

Un mécanisme équivalent existe déjà côté `ai_verifier.py`
(`_unsupported_visual_question`) : verdict IA vidé, explication remplacée par
un texte explicite, réponse officielle UNESS conservée — mais il n'est jamais
atteint car `assert_verified_exam` rejette l'examen avant. Idem pour le
rendu : `qcm_replay.py` a déjà un bandeau d'avertissement pour un autre cas
(`support_visuel_seul`) qu'il suffit de dupliquer pour celui-ci.

### Changements

**1. `backend/core/uness/models.py`** — nouvelle constante partagée :
```python
UNSUPPORTED_VISUAL_EXPLANATION = (
    "Vérification IA indisponible : le support visuel requis n'a pas pu être "
    "fourni intégralement au modèle."
)
```
(déplacée depuis `ai_verifier.py`, qui l'importe désormais d'ici — évite deux
textes qui divergent avec le temps).

**2. `backend/core/uness/gemini_conversion.py`** (`_question()`) — quand
`verification_status` vaut `"unsupported"`, assainir les propositions avant de
les retourner (même logique que `_unsupported_visual_question`, appliquée ici
au niveau dict plutôt qu'aux dataclasses, car `_question()` construit encore
un dict brut à ce stade du pipeline) :
```python
if verification_status == "unsupported":
    propositions = [
        {**p, "verdict_ia": None, "explication_ia": UNSUPPORTED_VISUAL_EXPLANATION,
         "sources_ia": [], "confiance_ia": None, "commentaire_desaccord": "",
         "statut": "incertain"}
        for p in propositions
    ]
```
(placé après le calcul de `propositions = raw.get("propositions", [])`, avant
la construction du dict de retour — les propositions passées à `_proposition()`
plus haut dans la fonction actuelle doivent utiliser cette version assainie,
donc l'ordre des opérations dans `_question()` bouge légèrement : calculer
`verification_status` d'abord, assainir si besoin, *puis* mapper avec
`_proposition()`.)

**3. `backend/core/uness/import_service.py`** (`assert_verified_exam`) —
bypass ciblé, le reste de la fonction ne change pas :
```python
for question in exam.questions:
    if question.verification_status == "unsupported":
        if not question.propositions or any(
            p.reponse_uness is None for p in question.propositions
        ):
            raise ValueError(
                f"Question {question.id} : vérification visuelle indisponible "
                "et réponse officielle UNESS manquante — impossible à importer."
            )
        continue
    # ... vérifications existantes inchangées pour les questions "verified"/"unverified"
```
Le fallback `_effective_answer`/`_choice_answers` existant retombe déjà
correctement sur `reponse_uness` quand `verdict_ia is None` — aucun changement
nécessaire côté `_to_practice_question`/`_question_metadata`.

**4. `frontend/components/qcm_replay.py`** (`_render_rows`, dans
`open_qcm_correction`) — même style que l'avertissement `support_visuel_seul`
existant (ligne ~336), juste après :
```python
if question_metadata.get("verification_status") == "unsupported":
    ui.label(
        "⚠️ Vérification IA non disponible pour cette question — seule la "
        "correction officielle UNESS est garantie exacte."
    ).classes("text-sm text-amber-800 dark:text-amber-300 whitespace-pre-wrap mt-2")
```
Visible uniquement dans la vue de correction (pas pendant la prise du quiz,
comme pour `support_visuel_seul`) — cohérent avec le fait que rien n'est
affiché à l'apprenant avant qu'il ait répondu.

### Effet de bord attendu

Un quiz important déjà bloqué aujourd'hui (comme SQI1) sera importé au
prochain scan sans changement de code côté pipeline de collecte — seul le
prochain passage par `correct_directory` (retry manuel ou automatique)
régénère la question au nouveau format assaini.

## Partie B — Panneau de diagnostic UNESS (Paramètres)

### Modèle de détection

Pour une `source_url` donnée, la liste de référence des quiz attendus est
celle de sa **collecte la plus récente** : on scanne tous les bridges JSON
(fichiers avec une clé `"contents"`, même filtre que `_find_bridge_files`)
sous `UNESS/à_vérifier/` et `UNESS/archives/`, on groupe par
`(source_url, collected_at)`, et on garde le groupe au `collected_at` le plus
grand (tri lexicographique ISO 8601, donc correct) par `source_url`. Les
titres de quiz de ce groupe sont la liste de référence.

Le bouton **Rafraîchir** relance un vrai `import_verified_directory()` (déjà
sûr à rejouer plusieurs fois grâce aux fix de dédup de ce soir) avant de
recalculer le rapport, pour que tout ce qui est importable le soit vraiment —
le statut "⏳ corrigé, en attente d'import" n'existe donc pas comme état
affiché : il est résolu par le refresh lui-même.

Pour chaque titre de la liste de référence, statut déterminé dans cet ordre :

1. **✅ Importé** — le titre (`{course_title} — {quiz}`) apparaît dans
   `local_store.list_annale_sessions(annale_id)` (si l'annale existe).
2. **🔄 En échec, retry programmé** — une entrée `uness_correction_failures`
   `pending` correspond à ce titre (résolution par `_locate_bridge` déjà
   présente dans `gemini_autocorrect.py`, ré-utilisée en lecture seule pour
   retrouver la `source_url` d'une entrée de la table, qui n'en stocke pas
   directement). Affiche `next_retry_at` et `attempts`/3.
3. **❌ Bloqué** — le titre correspond à un fichier listé dans `result["errors"]`
   du dernier `import_verified_directory()` (le fichier reste sur place dans
   `UNESS/vérifiés/` en cas d'échec, donc toujours présent au moment du
   diagnostic). Affiche le message d'erreur. Devrait être rare après la Partie A.
4. **⬜ Jamais tenté** — aucun des cas ci-dessus : collecté mais jamais soumis
   à Gemini (le trou silencieux de ce soir, maintenant loggé mais toujours
   possible en théorie).

Nouveau module dédié pour cette logique de lecture seule, séparé de
`import_service.py` (qui fait des mutations) :

**`backend/core/uness/diagnostics.py`** (nouveau)
```python
def build_report() -> list[dict]:
    """Une entrée par source_url connue (annale existante ou pending_tag),
    avec le détail par quiz. Appelle import_verified_directory() une fois
    (effet de bord assumé : importe tout ce qui est importable) avant de
    construire le rapport."""
```
Retourne une structure du type :
```python
[{
    "source_url": str,
    "annale": dict | None,       # local_store.get_uness_annale(...) ou None si pending_tag
    "titre": str,                 # depuis l'annale, ou dérivé du bridge si pending_tag
    "quizzes": [
        {"title": str, "status": "imported" | "retry_pending" | "blocked" | "never_attempted",
         "detail": dict},         # contenu selon le statut : next_retry_at/attempts, error_message, etc.
    ],
}, ...]
```

### UI — `frontend/pages/settings_cockpit.py` (+ nouveau composant)

Nouvelle section sous le bloc `UNESS` existant, label `.se-label` cohérent
avec les sections `CONNEXIONS`/`APPARENCE`/`UNESS` déjà présentes :

```
DIAGNOSTIC UNESS                                    [↻ Rafraîchir]

Dermatologie 🧴 — Fac. Paris Cité — 2025          ⚠️ 6/8
  ✅ mDP1  ✅ mDP2  ✅ mDP3  ✅ mDP5  ✅ TCS1  ✅ TCS2
  🔄 mDP4 — réponse incomplète (2/3), tentative 2/3, prochain essai 19:04  [Relancer]
  ⬜ (aucun cas actuellement pour cette annale)

Psychiatrie 🧩 — Fac. Paris Cité — 2025           ✅ 8/8

Maladies infectieuses — Fac. Paris Cité — 2025    ⏳ en attente de matière
  8 quiz corrigés, matière à choisir              [Qualifier maintenant]
```

Implémentation dans un composant séparé,
**`frontend/components/uness_diagnostic_panel.py`** (nouveau, pour ne pas
alourdir `settings_cockpit.py` qui fait déjà plusieurs choses) exposant une
fonction `render(container) -> None` appelée depuis `settings_cockpit.py`.

Actions :
- **Relancer** (par quiz `retry_pending`) → `gemini_autocorrect.retry_failed_quiz`
  (reset `attempts=0` comme le bouton existant du bandeau `/annales`), puis
  réimporte et rafraîchit la ligne.
- **Qualifier maintenant** (par groupe `pending_tag`) → réutilise le même
  formulaire matière que `_open_tag_dialog` dans `annales.py` (extraire ce
  dialogue dans une fonction partagée plutôt que le dupliquer, puisqu'il est
  appelé depuis deux pages désormais).
- Pas de bouton dédié pour `never_attempted` dans cette v1 : le champ
  « Corriger dossier existant » du dialogue d'import (`annales.py`) couvre déjà
  ce cas (retraiter tout un dossier de session) — dupliquer l'action ici
  n'apporte rien tant qu'on n'a pas une raison de le faire depuis Paramètres.

### Performance

Le scan des bridges JSON (Partie B, détection de la liste de référence) lit
chaque fichier sous `à_vérifier/` + `archives/` à chaque rafraîchissement —
accepté car cette page n'est pas un chemin chaud (chargée à la demande, pas au
démarrage), et le volume actuel (~200 fichiers) reste largement sous la
seconde. Si le volume grossit significativement, une optimisation possible
serait de persister `expected_quiz_count` au moment de la collecte
(`collector.py` connaît déjà ce nombre) — explicitement hors périmètre v1.

## Gestion des erreurs

- Un titre de quiz qui ne matche aucun des 4 statuts par bug (ex. `_locate_bridge`
  lève une exception inattendue lors de la résolution d'une entrée `failures`)
  tombe dans `never_attempted` avec un statut dégradé plutôt de faire planter
  toute la page — logué en `warning`.
- `build_report()` elle-même est protégée par le même principe de résilience
  que `correct_directory`/`import_verified_directory` (Partie A des fixes de
  ce soir) : une exception sur une `source_url` ne doit pas empêcher le
  rapport des autres.

## Tests

- `tests/test_uness_import.py` : question `unsupported` avec `reponse_uness`
  présente → import réussi, question conservée avec verdict vidé ; question
  `unsupported` sans `reponse_uness` → `ValueError`. Le reste des questions
  `verified` d'un même quiz n'est pas affecté par une question `unsupported`
  voisine.
- `tests/test_gemini_conversion.py` : `_question()` assainit bien les
  propositions d'une question `unsupported` (verdict/confiance à `None`,
  explication = constante partagée).
- Nouveau `tests/test_uness_diagnostics.py` : `build_report()` sur un jeu de
  fixtures (bridges + DB en mémoire) couvrant les 4 statuts + le cas
  `pending_tag`, y compris qu'une collecte plus ancienne du même `source_url`
  n'influence pas la liste de référence (seule la plus récente compte).
- Test manuel : vérifier le rendu du panneau sur les données réelles actuelles
  (Dermatologie 6/8, Psychiatrie 8/8, Maladies infectieuses en attente de
  matière) après implémentation.

## Hors périmètre (v1)

- Pas de persistance d'`expected_quiz_count` à la collecte (cf. section
  Performance) — recalculé par scan à chaque rafraîchissement.
- Pas d'action directe pour `never_attempted` dans le panneau — passer par
  « Corriger dossier existant » sur `/annales`.
- Pas de vue historique (annales `resolved`/anciennes collectes supplantées) —
  seule la collecte la plus récente par `source_url` est prise en compte.
- Pas de debug IA au-delà d'UNESS (QCM ChatGPT/Gemini, autres features IA).
