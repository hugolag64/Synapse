# Chantier C4 — Flash-Zero génératif

**Date** : 2026-08-08
**Statut** : design validé, prêt pour plan d'implémentation

## Contexte

Quatrième sous-chantier de C (fond pédagogique), suite de C1/C2/C3, tous terminés. Demande initiale
de l'utilisateur (section 1) : « impression que ce sont les mêmes questions d'un jour à l'autre »
pour Flash-Zero. Périmètre de départ (section 5) : `backend/core/practice/flash_zero_service.py:63`,
banque de 10 questions figée en dur, à remplacer par de la génération IA.

**Vérification du diagnostic.** `FlashZeroService.get_morning_quiz(count=10)`
(`flash_zero_service.py:51-186`) construit `canonical_flash_bank`, une liste **littéralement figée**
de 10 `FlashZeroQuestion` (fz-001 à fz-010). Le tri par priorité (erreurs récentes/répétées, via
`build_flash_zero_priority`) ne fait que réordonner ces 10 questions — avec `count=10` demandé sur
une banque de 10, `(targeted + fallback)[:count]` renvoie systématiquement les 10 mêmes questions,
tous les jours. L'impression de l'utilisateur est exacte, pas une impression.

**Enjeu de sécurité.** Contrairement à C1-C3, ce chantier introduit une vraie génération IA sur du
contenu médical à haut risque : les « zéros éliminatoires » sont des règles absolues (« ne jamais
faire X ») où une hallucination serait dangereuse à apprendre par cœur. Décisions utilisateur prises
en amont de cette spec :
- **Hybride, jamais un remplacement.** Les 10 questions canoniques (rédigées à la main, fiables)
  restent le socle intouché. L'IA vient uniquement **ajouter** de nouvelles questions au fil du
  temps — la banque grandit, elle ne se substitue jamais au socle validé.
- **Signalement doux, pas de gate bloquant.** Une question générée par l'IA entre directement dans
  la rotation, avec un badge visuel si l'IA s'auto-signale incertaine — même logique que le badge
  « À vérifier » déjà existant sur les cas DP/KFP importés (`ai_practice_panel.py`).
- **Déclenchement automatique, une fois par jour, 3 questions.** Décision explicite de l'utilisateur
  malgré sa préférence générale de limiter les appels IA automatiques — assumée pour cette
  fonctionnalité précise, bornée à 1 appel IA maximum par jour.

## Objectif

Le pool de questions Flash-Zero s'enrichit chaque jour de nouvelles questions ciblées sur les
erreurs récentes de l'utilisateur, sans jamais remplacer ni dégrader la fiabilité de la banque
canonique existante.

## Périmètre

### 1. Nouveau type de tâche IA — `backend/core/ai/routing.py`

Ajout de `AITask.FLASH_ZERO = "flash_zero"` à l'énumération existante (`routing.py:8-19`). Aucune
entrée n'est ajoutée à la liste `FLASH_LITE` de `model_for_task()` (`routing.py:64-68`) : la tâche
tombe donc dans la branche par défaut `AIModel.FLASH`, le tier le plus fiable — cohérent avec DP/KFP
qui partagent déjà ce choix pour du contenu à enjeu clinique.

### 2. Stockage des questions générées — `backend/core/reviews/local_store.py`

Nouvelle table, ajoutée au script de création de schéma existant (même style que `lisa_oic`) :

```sql
CREATE TABLE IF NOT EXISTS flash_zero_ai_questions (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    item_number         TEXT    NOT NULL,
    item_title          TEXT    NOT NULL,
    question_text       TEXT    NOT NULL,
    choices_json        TEXT    NOT NULL,
    correct_idx         INTEGER NOT NULL,
    explanation         TEXT    NOT NULL,
    is_zero_eliminatoire INTEGER NOT NULL DEFAULT 0,
    category            TEXT    NOT NULL,
    generated_at        TEXT    NOT NULL,
    review_reason       TEXT    NOT NULL DEFAULT ''
);
```

`review_reason` vide = pas de doute signalé par l'IA ; non-vide = le badge « Généré par IA · non
relu » s'affiche avec ce texte. Deux nouvelles fonctions, même style que `upsert_lisa_oic` /
`get_lisa_oic` :

- `save_flash_zero_ai_questions(questions: list[dict]) -> None` — insère un lot de questions
  générées (une ligne par question).
- `get_flash_zero_ai_questions(limit: int = 200) -> list[dict]` — relit le pool complet, plus
  récentes en premier.

### 3. Génération ciblée — `backend/core/practice/flash_zero_service.py`

Nouvelle méthode sur `FlashZeroService`, construite sur le même patron que
`PracticeService.__init__`/`generate_questions` (`backend/core/practice/service.py:108-157`) :
`ai_service: AIService | None = None` par défaut, import tardif de `GeminiClient` si absent.

```python
def generate_daily_questions(self, *, count: int = 3, item_number: str | None = None) -> list[dict]:
    """Génère jusqu'à `count` nouvelles questions Flash-Zero ciblées sur les items
    en tête de la priorité d'erreurs récentes. Ne modifie jamais canonical_flash_bank."""
```

Cible : les `count` premiers items de `build_flash_zero_priority(signals_since(item_number=item_number, days=30, store=self.store))`
— exactement la même source de priorité que `get_morning_quiz` utilise déjà. **Si aucun signal
d'erreur récent n'existe, aucune génération n'a lieu ce jour-là** — pas de remplissage sur du
hors-sujet aléatoire.

Prompt : un appel IA par item ciblé (comme `_recover_partial_questions` le fait déjà pour les lots
partiels), demandant une question au format `FlashZeroQuestion` (item_number, item_title,
question_text, 4 choix, correct_idx, explanation, is_zero_eliminatoire, category) en JSON, avec
consigne explicite :
- ne générer une question que si le fait clinique est un « toujours/jamais » manuel bien établi
  (zéro éliminatoire réel ou erreur de Rang A classique), jamais une nuance discutable ;
- retourner en plus un champ `"uncertain": true/false` — si `true`, la question est acceptée mais
  marquée pour signalement (`review_reason` rempli avec un message générique).

Validation stricte à la réception (même rigueur que `_parse_questions`) : JSON bien formé,
`correct_idx` dans la plage des choix, `choices` contient au moins 2 entrées, `explanation` et
`question_text` non vides, `is_zero_eliminatoire` interprétable en booléen. **Une question
individuelle invalide est silencieusement écartée** (pas d'exception qui ferait échouer tout le
lot) — contrairement à `generate_questions` (session QCM/DP initiée par l'utilisateur, qui doit
réussir intégralement ou échouer clairement), ici c'est un enrichissement de fond, best-effort.

### 4. Déclenchement quotidien — `backend/features/daily_routine.py`

Nouvelle fonction `ensure_daily_flash_zero_generation() -> None`, appelée juste après
`ensure_morning_flash_zero()` dans `run_daily_routine()` (`daily_routine.py:115`). Garde-fou
d'idempotence : réutilise la table `routine_checks` déjà existante
(`date`, `item_name`, `checked` — voir `complete_daily_flash_zero`), avec
`item_name = f"flash_zero_ai_gen:{timezone_name}"`. Le marqueur est posé **dès la tentative**
(succès ou échec de génération), pour ne jamais dépasser un appel IA par jour même en cas d'erreur
réseau/IA — pas de réessai automatique le même jour.

### 5. Intégration dans le quiz — `backend/core/practice/flash_zero_service.py:51-186`

`FlashZeroQuestion` (dataclass, `flash_zero_service.py:32-42`) gagne deux champs optionnels avec
valeur par défaut, pour rester compatible avec les 10 questions canoniques existantes qui ne les
renseignent pas :

```python
source: str = "canonical"   # "canonical" | "ai"
review_reason: str = ""     # non vide => badge "Généré par IA · non relu"
```

`get_morning_quiz()` combine `canonical_flash_bank` (inchangé) avec les questions IA relues via
`self.store.get_flash_zero_ai_questions()` (accessible car `self.store` vaut `local_store` par
défaut, exactement comme `self.store.get_item_pedagogical_history` déjà utilisé plus haut dans la
même méthode), converties en `FlashZeroQuestion(source="ai", ...)`. Le pool combiné passe ensuite
dans la même logique `targeted` / `fallback` / `random.shuffle` déjà en place
(`flash_zero_service.py:176-186`), inchangée.

### 6. Badge dans le wizard — `frontend/components/flash_zero_cockpit.py`

Dans `open_flash_zero_quiz` (`flash_zero_cockpit.py:50-145`), quand `question.review_reason` est
non vide, un badge discret apparaît sous l'en-tête de la question (même famille visuelle que le
badge « À vérifier » de `ai_practice_panel.py`, texte ambre/amber, pas rouge — ce n'est pas une
erreur confirmée, juste un signalement) :

```python
if question.review_reason:
    ui.label(f"⚡ Généré par IA · {question.review_reason}").classes("text-xs text-amber-600 mt-1")
```

## Hors périmètre

- Aucun changement à `canonical_flash_bank` : les 10 questions restent identiques, jamais modifiées
  ni supprimées par ce chantier.
- Aucune interface de validation/suppression manuelle des questions générées par l'IA — décision
  utilisateur : signalement doux uniquement, pas de gate ni d'écran de review dédié.
- Aucune limite de taille sur le pool IA cumulé (`flash_zero_ai_questions` grandit indéfiniment,
  ~3 lignes/jour maximum) — pas de purge ni d'archivage dans ce chantier.
- `color=indigo` sur les boutons « Valider »/« Question suivante » du wizard
  (`flash_zero_cockpit.py:119,142`) : couleur décorative repérée en explorant le fichier, mais hors
  demande de ce chantier — à traiter séparément si besoin.

## Risques

- **Coût IA récurrent, assumé.** Jusqu'à 3 appels IA (`AIModel.FLASH`) par jour, tous les jours, si
  l'utilisateur a des signaux d'erreur récents. Décision utilisateur explicite malgré sa préférence
  générale de limiter les appels automatiques — voir Contexte.
- **Qualité variable du contenu généré.** Le signalement doux n'empêche pas une question incorrecte
  non auto-détectée par l'IA d'apparaître sans badge. Risque accepté par l'utilisateur en choisissant
  l'option légère plutôt que le gate de validation obligatoire.
- **Nouveaux champs sur une dataclass frozen.** `FlashZeroQuestion(frozen=True)` gagne `source` et
  `review_reason` avec valeurs par défaut — toute construction existante (les 10 questions
  canoniques, qui ne passent pas ces deux arguments) continue de fonctionner sans modification.

## Tests

- `tests/test_flash_zero_integration.py` : nouveau test — `generate_daily_questions()` avec un store
  factice sans aucun signal d'erreur ne fait aucun appel IA et retourne une liste vide.
- Nouveau test — `generate_daily_questions()` avec des signaux d'erreur sur 2 items distincts génère
  au plus 2 questions (borné par le nombre d'items ciblés, pas par `count` seul), chacune avec
  `item_number` correspondant à un item ciblé.
- Nouveau test — une réponse IA malformée pour un item (JSON invalide, `correct_idx` hors plage) est
  écartée silencieusement ; les autres questions valides du même lot sont quand même retournées.
- Nouveau test — `get_morning_quiz()` avec des questions IA stockées en base inclut au moins une
  question `source="ai"` dans le pool combiné, sans que les 10 questions canoniques disparaissent.
- Nouveau test — `ensure_daily_flash_zero_generation()` est idempotente : deux appels le même jour
  ne déclenchent qu'un seul appel IA (mock comptabilisé).
- Suite complète (`./.venv/Scripts/python.exe -m pytest -q`) avant la première tâche et après la
  dernière.
