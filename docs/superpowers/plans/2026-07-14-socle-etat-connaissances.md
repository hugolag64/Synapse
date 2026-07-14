# Socle « état des connaissances » — Plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Permettre à Synapse de représenter un collège validé académiquement dont les items n'ont jamais été évalués, et de rendre ces items planifiables via un niveau déclaré qui se dégrade avec le temps et s'efface devant les preuves réelles.

**Architecture:** Nouveau module `backend/core/knowledge/` (models / store / service) portant deux tables SQLite (`college_status`, `item_state`). `mastery.py` interroge ce service pour obtenir une « graine » de score et la fusionner avec son score calculé actuel. Aucune écriture Notion. L'UI gagne quatre points de saisie (page Collèges, écran de triage, fiche cours, modale de session).

**Tech Stack:** Python 3, SQLite (sqlite3 + `sqlite3.Row`), NiceGUI, pytest, loguru.

**Spec de référence:** `docs/superpowers/specs/2026-07-14-socle-etat-connaissances-design.md`

## Global Constraints

- **Aucune écriture Notion.** Ces données sont locales, comme les stages.
- **Partage de connexion SQLite :** `knowledge/store.py` importe `_conn` et `_now` depuis `backend.core.reviews.local_store`. Il ne crée **jamais** sa propre connexion, sinon la fixture de test `isolated_db` (qui monkeypatche `local_store.DB_PATH` et `local_store._DB`) ne l'isolerait pas.
- **`sqlite3.Row` n'a pas de `.get()`.** Toujours `row["col"]`, jamais `row.get("col")` (bug déjà rencontré dans ce projet).
- **Nom de collège = clé Notion avec emoji à la fin** (`Cardiovasculaire ❤️`), conforme à `COLLEGE_MAPPING`.
- **Constantes (valeurs exactes, définies une seule fois dans `models.py`) :**
  - `SEED_SCORES = {"solide": 70, "correct": 50, "flou": 30}`
  - `DECAY_PER_30D = 2.0`
  - `SEED_FLOOR = 25`
  - `OIC_SUCCESS_SCORE = 70`
  - `RANG_A_BADGE_THRESHOLD = 0.80`
- **Statuts de collège :** `non_etudie` (défaut) · `en_cours` · `valide`. Aucun autre.
- **Niveaux déclarés :** `solide` · `correct` · `flou`. Aucun autre.
- **Tests :** `pytest`, avec la fixture `isolated_db` copiée depuis `tests/test_local_store.py:12-25`.

---

### Task 1: Modèle et mathématiques de la graine

Module pur, sans I/O. C'est le cœur calculatoire : il doit être juste avant que quoi que ce soit d'autre s'y branche.

**Files:**
- Create: `backend/core/knowledge/__init__.py` (vide)
- Create: `backend/core/knowledge/models.py`
- Test: `tests/test_knowledge_models.py`

**Interfaces:**
- Consumes: rien.
- Produces:
  - `SEED_SCORES: dict[str, int]`, `DECAY_PER_30D: float`, `SEED_FLOOR: int`, `OIC_SUCCESS_SCORE: int`, `RANG_A_BADGE_THRESHOLD: float`
  - `DECLARED_LEVELS: tuple[str, ...]`, `COLLEGE_STATUSES: tuple[str, ...]`
  - `@dataclass CollegeStatus(college: str, status: str, validated_at: date | None, updated_at: str)`
  - `@dataclass ItemState(course_id: str, context: str, declared_level: str, declared_at: date, source: str, updated_at: str)`
  - `@dataclass SeedSnapshot(declared_level: str | None, seed_score: int | None, n_evidence: int)`
  - `decayed_seed(level: str, declared_at: date, until: date) -> int`
  - `blend(seed: int | None, computed: int | None, n_evidence: int) -> int | None`
  - `level_from_seed(score: int) -> str`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_knowledge_models.py`:

```python
"""Tests unitaires — knowledge.models (graine, dégradation, fusion)."""
import datetime

from backend.core.knowledge.models import (
    SEED_SCORES, SEED_FLOOR, DECAY_PER_30D,
    decayed_seed, blend, level_from_seed,
)


def _d(y, m, d) -> datetime.date:
    return datetime.date(y, m, d)


# ── Dégradation ───────────────────────────────────────────────────────────────

def test_seed_le_jour_de_la_declaration_vaut_la_valeur_nominale():
    day = _d(2026, 7, 14)
    assert decayed_seed("solide", day, day) == 70
    assert decayed_seed("correct", day, day) == 50
    assert decayed_seed("flou", day, day) == 30


def test_seed_se_degrade_de_2_points_par_30_jours():
    start = _d(2026, 7, 14)
    assert decayed_seed("solide", start, start + datetime.timedelta(days=30)) == 68
    assert decayed_seed("solide", start, start + datetime.timedelta(days=90)) == 64


def test_seed_ne_descend_jamais_sous_le_plancher():
    start = _d(2020, 1, 1)
    assert decayed_seed("solide", start, _d(2026, 7, 14)) == SEED_FLOOR
    assert decayed_seed("flou", start, _d(2026, 7, 14)) == SEED_FLOOR


def test_seed_ignore_une_date_future_de_declaration():
    """Robustesse : une declared_at dans le futur ne doit pas gonfler la graine."""
    today = _d(2026, 7, 14)
    future = _d(2026, 12, 31)
    assert decayed_seed("correct", future, today) == SEED_SCORES["correct"]


# ── Fusion graine / évidence ──────────────────────────────────────────────────

def test_sans_preuve_la_graine_est_le_score():
    assert blend(seed=70, computed=40, n_evidence=0) == 70


def test_une_preuve_donne_moitie_moitie():
    assert blend(seed=70, computed=40, n_evidence=1) == 55


def test_trois_preuves_diluent_la_graine_au_quart():
    # 0.25 * 70 + 0.75 * 40 = 47.5 → 48 (arrondi)
    assert blend(seed=70, computed=40, n_evidence=3) == 48


def test_sans_graine_le_score_calcule_passe_tel_quel():
    assert blend(seed=None, computed=42, n_evidence=5) == 42


def test_sans_graine_ni_score_calcule_le_resultat_est_none():
    assert blend(seed=None, computed=None, n_evidence=0) is None


def test_graine_seule_sans_score_calcule():
    """Ancien item déclaré, jamais lu : le calculé est None, la graine survit."""
    assert blend(seed=50, computed=None, n_evidence=0) == 50


# ── Niveau depuis la graine ───────────────────────────────────────────────────

def test_level_from_seed_mappe_les_trois_crans():
    assert level_from_seed(SEED_SCORES["flou"]) == "critique"      # 30
    assert level_from_seed(SEED_SCORES["correct"]) == "fragile"    # 50
    assert level_from_seed(SEED_SCORES["solide"]) == "à consolider"  # 70
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_knowledge_models.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'backend.core.knowledge'`

- [ ] **Step 3: Write the implementation**

Create `backend/core/knowledge/__init__.py` (fichier vide).

Create `backend/core/knowledge/models.py`:

```python
"""
knowledge.models — Synapse
--------------------------
Modèle d'état des connaissances : statut d'un collège, niveau déclaré d'un item,
et mathématiques de la « graine » de maîtrise.

Module pur : aucune I/O, aucune dépendance projet.

Principe : un niveau déclaré n'est pas un score, c'est un a priori qui s'efface.
  - il se dégrade avec le temps écoulé depuis la déclaration (decayed_seed) ;
  - il est dilué par les preuves réelles — sessions, QCM, évals OIC (blend).
"""
from __future__ import annotations

import datetime
from dataclasses import dataclass


# ── Constantes ────────────────────────────────────────────────────────────────

DECLARED_LEVELS: tuple[str, ...] = ("solide", "correct", "flou")
COLLEGE_STATUSES: tuple[str, ...] = ("non_etudie", "en_cours", "valide")

SEED_SCORES: dict[str, int] = {"solide": 70, "correct": 50, "flou": 30}

# Un « solide » atteint le plancher en ~22 mois, un « correct » en ~12 mois :
# l'horizon EDN (~2 ans) est couvert sans que rien ne stagne en haut de l'échelle.
DECAY_PER_30D: float = 2.0
SEED_FLOOR: int = 25

# Une tentative OIC à ce score ou au-dessus vaut réussite (passe mastered = 1).
OIC_SUCCESS_SCORE: int = 70

# Part d'OIC de rang A réussis à partir de laquelle le badge « Rang A ✓ » est acquis.
RANG_A_BADGE_THRESHOLD: float = 0.80


# ── Dataclasses ───────────────────────────────────────────────────────────────

@dataclass
class CollegeStatus:
    college: str
    status: str                          # non_etudie | en_cours | valide
    validated_at: datetime.date | None
    updated_at: str


@dataclass
class ItemState:
    course_id: str
    context: str                         # college | ue
    declared_level: str                  # solide | correct | flou
    declared_at: datetime.date
    source: str                          # triage | reprise
    updated_at: str


@dataclass
class SeedSnapshot:
    """Ce que mastery.py a besoin de savoir sur l'état déclaré d'un item."""
    declared_level: str | None
    seed_score: int | None
    n_evidence: int


# ── Mathématiques de la graine ────────────────────────────────────────────────

def decayed_seed(level: str, declared_at: datetime.date, until: datetime.date) -> int:
    """
    Graine dégradée : la valeur nominale du niveau, diminuée de DECAY_PER_30D
    points par tranche de 30 jours écoulés, avec un plancher à SEED_FLOOR.

    `until` est la date d'arrêt de la dégradation : la date de la première preuve
    réelle si elle existe, aujourd'hui sinon (cf. service.get_seed_snapshot).
    """
    base = SEED_SCORES.get(level)
    if base is None:
        raise ValueError(f"Niveau déclaré inconnu : {level!r}")

    elapsed_days = max(0, (until - declared_at).days)   # une date future ne gonfle rien
    decay = DECAY_PER_30D * (elapsed_days / 30.0)
    return max(SEED_FLOOR, int(round(base - decay)))


def blend(seed: int | None, computed: int | None, n_evidence: int) -> int | None:
    """
    Fusionne la graine et le score calculé par mastery.py.

    Le poids de la graine décroît avec le nombre de preuves réelles :
        0 preuve → 100 %, 1 → 50 %, 2 → 33 %, 3 → 25 %.
    La graine est diluée, jamais effacée brutalement.
    """
    if seed is None:
        return computed
    if computed is None:
        return seed

    w = 1.0 / (1.0 + max(0, n_evidence))
    return int(round(w * seed + (1.0 - w) * computed))


def level_from_seed(score: int) -> str:
    """
    Niveau affiché d'un item déclaré mais sans aucune preuve réelle.

    Utilise les noms de PROGRESSION_COLORS existants — on n'introduit pas de
    nouveau niveau dans l'échelle. Les trois crans atterrissent ainsi :
        flou (30) → critique · correct (50) → fragile · solide (70) → à consolider
    """
    if score < 40:
        return "critique"
    if score < 60:
        return "fragile"
    return "à consolider"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_knowledge_models.py -v`
Expected: PASS — 11 tests.

- [ ] **Step 5: Commit**

```bash
git add backend/core/knowledge/__init__.py backend/core/knowledge/models.py tests/test_knowledge_models.py
git commit -m "feat(knowledge): modèle d'état et mathématiques de la graine de maîtrise"
```

---

### Task 2: Persistance — tables `college_status` et `item_state`

**Files:**
- Create: `backend/core/knowledge/store.py`
- Test: `tests/test_knowledge_store.py`

**Interfaces:**
- Consumes: `models.CollegeStatus`, `models.ItemState`, `models.COLLEGE_STATUSES`, `models.DECLARED_LEVELS` ; `local_store._conn`, `local_store._now`.
- Produces:
  - `init_knowledge_tables() -> None`
  - `set_college_status(college: str, status: str) -> None`
  - `get_college_status(college: str) -> str`  (`"non_etudie"` si absent)
  - `get_all_college_statuses() -> dict[str, str]`
  - `set_item_state(course_id: str, level: str, context: str = "college", source: str = "reprise") -> None`
  - `get_item_state(course_id: str, context: str = "college") -> ItemState | None`
  - `get_all_item_states(context: str = "college") -> dict[str, ItemState]`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_knowledge_store.py`:

```python
"""Tests unitaires — knowledge.store (persistance SQLite)."""
import datetime
import pytest


# ── Fixture : DB temporaire isolée (même pattern que tests/test_local_store.py) ──

@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    import backend.core.reviews.local_store as ls
    import backend.core.knowledge.store as ks

    test_db = tmp_path / "test.db"
    monkeypatch.setattr(ls, "DB_PATH", test_db)
    monkeypatch.setattr(ls, "_DB", None)
    ls.init_db()
    ks.init_knowledge_tables()
    yield
    if ls._DB is not None:
        ls._DB.close()
    monkeypatch.setattr(ls, "_DB", None)


import backend.core.knowledge.store as ks


# ── college_status ────────────────────────────────────────────────────────────

def test_college_inconnu_est_non_etudie():
    assert ks.get_college_status("Cardiovasculaire ❤️") == "non_etudie"


def test_valider_un_college_le_persiste_avec_sa_date():
    ks.set_college_status("Cardiovasculaire ❤️", "valide")
    assert ks.get_college_status("Cardiovasculaire ❤️") == "valide"

    statuses = ks.get_all_college_statuses()
    assert statuses["Cardiovasculaire ❤️"] == "valide"


def test_set_college_status_refuse_un_statut_inconnu():
    with pytest.raises(ValueError):
        ks.set_college_status("Cardiovasculaire ❤️", "presque_valide")


def test_repasser_un_college_a_non_etudie_efface_validated_at():
    ks.set_college_status("Pneumologie 🫁", "valide")
    ks.set_college_status("Pneumologie 🫁", "non_etudie")
    assert ks.get_college_status("Pneumologie 🫁") == "non_etudie"


# ── item_state ────────────────────────────────────────────────────────────────

def test_item_sans_declaration_est_none():
    assert ks.get_item_state("course-1") is None


def test_declarer_un_item_le_persiste():
    ks.set_item_state("course-1", "correct", source="triage")
    st = ks.get_item_state("course-1")

    assert st.declared_level == "correct"
    assert st.source == "triage"
    assert st.declared_at == datetime.date.today()
    assert st.context == "college"


def test_redeclarer_un_item_ecrase_le_niveau_precedent():
    ks.set_item_state("course-1", "flou")
    ks.set_item_state("course-1", "solide")
    assert ks.get_item_state("course-1").declared_level == "solide"


def test_set_item_state_refuse_un_niveau_inconnu():
    with pytest.raises(ValueError):
        ks.set_item_state("course-1", "moyen")


def test_les_contextes_college_et_ue_sont_independants():
    ks.set_item_state("course-1", "solide", context="college")
    ks.set_item_state("course-1", "flou", context="ue")

    assert ks.get_item_state("course-1", "college").declared_level == "solide"
    assert ks.get_item_state("course-1", "ue").declared_level == "flou"


def test_get_all_item_states_ne_renvoie_que_le_contexte_demande():
    ks.set_item_state("course-1", "solide", context="college")
    ks.set_item_state("course-2", "flou", context="ue")

    states = ks.get_all_item_states("college")
    assert set(states.keys()) == {"course-1"}


def test_repasser_un_college_a_non_etudie_ne_detruit_pas_les_niveaux_declares():
    """Garde-fou : le statut du collège et l'état des items sont indépendants."""
    ks.set_college_status("Cardiovasculaire ❤️", "valide")
    ks.set_item_state("course-1", "solide")

    ks.set_college_status("Cardiovasculaire ❤️", "non_etudie")

    assert ks.get_item_state("course-1").declared_level == "solide"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_knowledge_store.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'backend.core.knowledge.store'`

- [ ] **Step 3: Write the implementation**

Create `backend/core/knowledge/store.py`:

```python
"""
knowledge.store — Synapse
-------------------------
Persistance SQLite de l'état des connaissances :
  - college_status : statut académique d'un collège (déclaré)
  - item_state     : niveau déclaré d'un item (solide / correct / flou)

Réutilise la connexion de local_store : une seule base, une seule connexion,
et la fixture de test isolated_db isole les deux modules d'un coup.

Aucune écriture Notion : ce sont des données de pilotage personnel.
"""
from __future__ import annotations

import datetime
from loguru import logger

from backend.core.reviews.local_store import _conn, _now
from backend.core.knowledge.models import (
    CollegeStatus, ItemState, COLLEGE_STATUSES, DECLARED_LEVELS,
)


# ── Initialisation ────────────────────────────────────────────────────────────

def init_knowledge_tables() -> None:
    """Crée les tables du domaine « connaissances » si elles n'existent pas."""
    with _conn() as con:
        con.executescript("""
            CREATE TABLE IF NOT EXISTS college_status (
                college      TEXT PRIMARY KEY,
                status       TEXT NOT NULL DEFAULT 'non_etudie',
                validated_at TEXT,
                updated_at   TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS item_state (
                course_id      TEXT NOT NULL,
                context        TEXT NOT NULL DEFAULT 'college',
                declared_level TEXT NOT NULL,
                declared_at    TEXT NOT NULL,
                source         TEXT NOT NULL DEFAULT 'reprise',
                updated_at     TEXT NOT NULL,
                PRIMARY KEY (course_id, context)
            );

            CREATE INDEX IF NOT EXISTS idx_item_state_ctx ON item_state(context);
        """)
    logger.debug("knowledge : tables college_status et item_state initialisées.")


# ── college_status ────────────────────────────────────────────────────────────

def set_college_status(college: str, status: str) -> None:
    """Déclare le statut académique d'un collège. Statuts : non_etudie | en_cours | valide."""
    if status not in COLLEGE_STATUSES:
        raise ValueError(f"Statut de collège inconnu : {status!r}")

    validated_at = datetime.date.today().isoformat() if status == "valide" else None

    with _conn() as con:
        con.execute(
            """INSERT INTO college_status (college, status, validated_at, updated_at)
                    VALUES (?, ?, ?, ?)
               ON CONFLICT(college) DO UPDATE SET
                    status       = excluded.status,
                    validated_at = excluded.validated_at,
                    updated_at   = excluded.updated_at""",
            (college, status, validated_at, _now()),
        )


def get_college_status(college: str) -> str:
    """Statut d'un collège. Un collège absent de la table est réputé non_etudie."""
    with _conn() as con:
        row = con.execute(
            "SELECT status FROM college_status WHERE college = ?", (college,)
        ).fetchone()
    return row["status"] if row else "non_etudie"


def get_all_college_statuses() -> dict[str, str]:
    """{college: status} pour tous les collèges déclarés."""
    with _conn() as con:
        rows = con.execute("SELECT college, status FROM college_status").fetchall()
    return {r["college"]: r["status"] for r in rows}


# ── item_state ────────────────────────────────────────────────────────────────

def set_item_state(
    course_id: str,
    level: str,
    context: str = "college",
    source: str = "reprise",
) -> None:
    """Déclare (ou redéclare) le niveau ressenti d'un item."""
    if level not in DECLARED_LEVELS:
        raise ValueError(f"Niveau déclaré inconnu : {level!r}")

    today = datetime.date.today().isoformat()

    with _conn() as con:
        con.execute(
            """INSERT INTO item_state
                    (course_id, context, declared_level, declared_at, source, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT(course_id, context) DO UPDATE SET
                    declared_level = excluded.declared_level,
                    declared_at    = excluded.declared_at,
                    source         = excluded.source,
                    updated_at     = excluded.updated_at""",
            (course_id, context, level, today, source, _now()),
        )


def _row_to_item_state(row) -> ItemState:
    return ItemState(
        course_id=row["course_id"],
        context=row["context"],
        declared_level=row["declared_level"],
        declared_at=datetime.date.fromisoformat(row["declared_at"]),
        source=row["source"],
        updated_at=row["updated_at"],
    )


def get_item_state(course_id: str, context: str = "college") -> ItemState | None:
    """État déclaré d'un item, ou None s'il est encore « à situer »."""
    with _conn() as con:
        row = con.execute(
            "SELECT * FROM item_state WHERE course_id = ? AND context = ?",
            (course_id, context),
        ).fetchone()
    return _row_to_item_state(row) if row else None


def get_all_item_states(context: str = "college") -> dict[str, ItemState]:
    """{course_id: ItemState} — chargement par lot, pour éviter N requêtes."""
    with _conn() as con:
        rows = con.execute(
            "SELECT * FROM item_state WHERE context = ?", (context,)
        ).fetchall()
    return {r["course_id"]: _row_to_item_state(r) for r in rows}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_knowledge_store.py -v`
Expected: PASS — 11 tests.

- [ ] **Step 5: Commit**

```bash
git add backend/core/knowledge/store.py tests/test_knowledge_store.py
git commit -m "feat(knowledge): tables college_status et item_state"
```

---

### Task 3: Une éval OIC réussie passe `mastered = 1`

C'est le chaînon manquant identifié dans la spec : aujourd'hui `save_oic_attempt()` (`local_store.py:2616`) enregistre un `session_score` sans jamais toucher au flag `mastered`, qui n'est modifiable qu'à la main (`toggle_lisa_oic_mastery`, ligne 2597). La couverture rang A serait donc structurellement vide.

**Files:**
- Modify: `backend/core/reviews/local_store.py:2616-2625` (fonction `save_oic_attempt`)
- Test: `tests/test_knowledge_oic.py`

**Interfaces:**
- Consumes: `models.OIC_SUCCESS_SCORE`.
- Produces: `save_oic_attempt` conserve sa signature `(oic_id: int, session_score: int, questions_json: str) -> int` et gagne l'effet de bord `mastered = 1` si `session_score >= OIC_SUCCESS_SCORE`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_knowledge_oic.py`:

```python
"""Tests — une évaluation OIC réussie marque l'OIC comme maîtrisé."""
import pytest

from backend.core.knowledge.models import OIC_SUCCESS_SCORE


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    import backend.core.reviews.local_store as ls
    import backend.core.knowledge.store as ks

    test_db = tmp_path / "test.db"
    monkeypatch.setattr(ls, "DB_PATH", test_db)
    monkeypatch.setattr(ls, "_DB", None)
    ls.init_db()
    ks.init_knowledge_tables()
    yield
    if ls._DB is not None:
        ls._DB.close()
    monkeypatch.setattr(ls, "_DB", None)


import backend.core.reviews.local_store as ls


def _seed_one_oic(course_id: str = "course-1", rang: str = "A") -> int:
    """Insère un OIC et renvoie son id."""
    ls.upsert_lisa_oic(course_id, [
        {"oic_code": "OIC-001", "intitule": "Objectif test", "rang": rang,
         "rubrique": "Définition", "ordre": 1},
    ])
    oics = ls.get_lisa_oic(course_id)
    return oics[0]["id"]


def _mastered(oic_id: int) -> int:
    with ls._conn() as con:
        return con.execute(
            "SELECT mastered FROM lisa_oic WHERE id = ?", (oic_id,)
        ).fetchone()["mastered"]


def test_une_tentative_reussie_passe_mastered_a_1():
    oic_id = _seed_one_oic()
    ls.save_oic_attempt(oic_id, OIC_SUCCESS_SCORE, "[]")
    assert _mastered(oic_id) == 1


def test_une_tentative_ratee_ne_passe_pas_mastered():
    oic_id = _seed_one_oic()
    ls.save_oic_attempt(oic_id, OIC_SUCCESS_SCORE - 1, "[]")
    assert _mastered(oic_id) == 0


def test_une_tentative_ratee_ne_demastere_pas_un_oic_deja_acquis():
    """Un échec ponctuel ne doit pas effacer une réussite antérieure."""
    oic_id = _seed_one_oic()
    ls.save_oic_attempt(oic_id, 90, "[]")
    ls.save_oic_attempt(oic_id, 20, "[]")
    assert _mastered(oic_id) == 1


def test_la_tentative_est_bien_enregistree():
    oic_id = _seed_one_oic()
    ls.save_oic_attempt(oic_id, 85, "[]")
    attempts = ls.get_oic_attempts(oic_id)
    assert len(attempts) == 1
    assert attempts[0]["session_score"] == 85
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_knowledge_oic.py -v`
Expected: FAIL — `test_une_tentative_reussie_passe_mastered_a_1` échoue avec `assert 0 == 1`.

- [ ] **Step 3: Write the implementation**

Dans `backend/core/reviews/local_store.py`, remplacer la fonction `save_oic_attempt` (ligne 2616) par :

```python
def save_oic_attempt(oic_id: int, session_score: int, questions_json: str) -> int:
    """
    Enregistre une tentative d'évaluation OIC. Retourne l'id inséré.

    Une tentative à OIC_SUCCESS_SCORE ou au-dessus marque l'OIC comme maîtrisé.
    Un échec ultérieur ne le démarque pas : la réussite est acquise, c'est la
    dégradation de la maîtrise de l'item qui porte l'oubli.
    """
    from backend.core.knowledge.models import OIC_SUCCESS_SCORE

    with _conn() as con:
        cur = con.execute(
            """INSERT INTO oic_attempts (oic_id, session_score, questions_json, attempted_at)
               VALUES (?, ?, ?, ?)""",
            (oic_id, session_score, questions_json, _now()),
        )
        if session_score >= OIC_SUCCESS_SCORE:
            con.execute("UPDATE lisa_oic SET mastered = 1 WHERE id = ?", (oic_id,))
        return cur.lastrowid
```

L'import est local à la fonction, délibérément : `knowledge.store` importe déjà `local_store`, et un import au niveau du module créerait un cycle. `knowledge.models` est un module pur sans dépendance, donc l'import local est sûr.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_knowledge_oic.py -v`
Expected: PASS — 4 tests.

- [ ] **Step 5: Vérifier la non-régression des tests OIC existants**

Run: `python -m pytest tests/test_oic_evaluator.py tests/test_local_store.py -v`
Expected: PASS (mêmes résultats qu'avant la modification).

- [ ] **Step 6: Commit**

```bash
git add backend/core/reviews/local_store.py tests/test_knowledge_oic.py
git commit -m "feat(oic): une évaluation réussie (>= 70) marque l'OIC comme maîtrisé"
```

---

### Task 4: Service — graine, preuves et couverture OIC

Le service est la seule porte d'entrée du domaine. `mastery.py` ne parlera qu'à lui.

**Files:**
- Create: `backend/core/knowledge/service.py`
- Test: `tests/test_knowledge_service.py`

**Interfaces:**
- Consumes: `knowledge.store` (tout), `knowledge.models` (tout), `local_store._conn`.
- Produces:
  - `get_seed_snapshot(course_id: str, context: str = "college", today: date | None = None) -> SeedSnapshot`
  - `first_evidence_date(course_id: str) -> date | None`
  - `count_evidence(course_id: str) -> int`
  - `oic_coverage(course_id: str) -> dict` → `{"rang_a_total": int, "rang_a_ok": int, "rang_a_pct": float, "rang_b_total": int, "rang_b_ok": int, "rang_b_pct": float}`
  - `badge_from_coverage(cov: dict) -> bool`
  - `has_rang_a_badge(course_id: str) -> bool`
  - `is_to_situate(course_id: str, colleges: list[str], context: str = "college") -> bool`
  - `college_triage_progress(college: str, course_ids: list[str], context: str = "college") -> tuple[int, int]` → `(situés, total)`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_knowledge_service.py`:

```python
"""Tests unitaires — knowledge.service (graine, preuves, couverture OIC)."""
import datetime
import pytest

from backend.core.knowledge.models import SEED_FLOOR, RANG_A_BADGE_THRESHOLD


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    import backend.core.reviews.local_store as ls
    import backend.core.knowledge.store as ks

    test_db = tmp_path / "test.db"
    monkeypatch.setattr(ls, "DB_PATH", test_db)
    monkeypatch.setattr(ls, "_DB", None)
    ls.init_db()
    ks.init_knowledge_tables()
    yield
    if ls._DB is not None:
        ls._DB.close()
    monkeypatch.setattr(ls, "_DB", None)


import backend.core.reviews.local_store as ls
import backend.core.knowledge.store as ks
import backend.core.knowledge.service as ksv


def _declare_at(course_id: str, level: str, days_ago: int) -> None:
    """Déclare un item avec une declared_at rétrodatée."""
    ks.set_item_state(course_id, level)
    past = (datetime.date.today() - datetime.timedelta(days=days_ago)).isoformat()
    with ls._conn() as con:
        con.execute(
            "UPDATE item_state SET declared_at = ? WHERE course_id = ?", (past, course_id)
        )


def _seed_oics(course_id: str, rangs: list[str]) -> list[int]:
    ls.upsert_lisa_oic(course_id, [
        {"oic_code": f"OIC-{i}", "intitule": f"Objectif {i}", "rang": r,
         "rubrique": "Définition", "ordre": i}
        for i, r in enumerate(rangs)
    ])
    return [o["id"] for o in ls.get_lisa_oic(course_id)]


# ── Graine ────────────────────────────────────────────────────────────────────

def test_item_non_declare_na_pas_de_graine():
    snap = ksv.get_seed_snapshot("course-1")
    assert snap.declared_level is None
    assert snap.seed_score is None
    assert snap.n_evidence == 0


def test_item_declare_sans_preuve_a_sa_graine_nominale():
    ks.set_item_state("course-1", "solide")
    snap = ksv.get_seed_snapshot("course-1")
    assert snap.declared_level == "solide"
    assert snap.seed_score == 70
    assert snap.n_evidence == 0


def test_la_graine_se_degrade_avec_le_temps_ecoule():
    _declare_at("course-1", "solide", days_ago=90)
    assert ksv.get_seed_snapshot("course-1").seed_score == 64


def test_la_graine_dun_item_tres_ancien_atteint_le_plancher():
    _declare_at("course-1", "solide", days_ago=365 * 3)
    assert ksv.get_seed_snapshot("course-1").seed_score == SEED_FLOOR


# ── Preuves ───────────────────────────────────────────────────────────────────

def test_une_session_compte_comme_une_preuve():
    ks.set_item_state("course-1", "solide")
    ls.add_study_session(course_id="course-1", activity_types=["révision"])
    assert ksv.get_seed_snapshot("course-1").n_evidence == 1


def test_la_degradation_gele_a_la_date_de_la_premiere_preuve():
    """Une preuve réelle arrête l'horloge : au-delà, c'est l'évidence qui pilote."""
    _declare_at("course-1", "solide", days_ago=90)
    ls.add_study_session(course_id="course-1", activity_types=["révision"])

    snap = ksv.get_seed_snapshot("course-1")
    # La session est d'aujourd'hui → until = aujourd'hui → 90 j de dégradation.
    # Le test vérifie surtout que first_evidence_date est bien pris en compte.
    assert ksv.first_evidence_date("course-1") == datetime.date.today()
    assert snap.seed_score == 64


def test_une_tentative_oic_compte_comme_une_preuve():
    ks.set_item_state("course-1", "solide")
    oic_ids = _seed_oics("course-1", ["A"])
    ls.save_oic_attempt(oic_ids[0], 40, "[]")
    assert ksv.get_seed_snapshot("course-1").n_evidence == 1


# ── Couverture OIC ────────────────────────────────────────────────────────────

def test_couverture_oic_vide_pour_un_cours_sans_oic():
    cov = ksv.oic_coverage("course-1")
    assert cov["rang_a_total"] == 0
    assert cov["rang_a_pct"] == 0.0
    assert ksv.has_rang_a_badge("course-1") is False


def test_couverture_rang_a_compte_les_oic_reussis():
    oic_ids = _seed_oics("course-1", ["A", "A", "A", "A", "B"])
    for oid in oic_ids[:4]:
        ls.save_oic_attempt(oid, 90, "[]")   # 4 rang A réussis sur 4

    cov = ksv.oic_coverage("course-1")
    assert cov["rang_a_total"] == 4
    assert cov["rang_a_ok"] == 4
    assert cov["rang_a_pct"] == 1.0
    assert cov["rang_b_total"] == 1
    assert cov["rang_b_ok"] == 0


def test_le_badge_rang_a_se_declenche_au_seuil():
    oic_ids = _seed_oics("course-1", ["A"] * 5)
    for oid in oic_ids[:4]:
        ls.save_oic_attempt(oid, 90, "[]")   # 4/5 = 80 %

    assert ksv.oic_coverage("course-1")["rang_a_pct"] >= RANG_A_BADGE_THRESHOLD
    assert ksv.has_rang_a_badge("course-1") is True


def test_le_badge_rang_a_ne_se_declenche_pas_sous_le_seuil():
    oic_ids = _seed_oics("course-1", ["A"] * 5)
    for oid in oic_ids[:3]:
        ls.save_oic_attempt(oid, 90, "[]")   # 3/5 = 60 %
    assert ksv.has_rang_a_badge("course-1") is False


def test_le_rang_b_ne_declenche_jamais_le_badge():
    oic_ids = _seed_oics("course-1", ["B", "B", "B"])
    for oid in oic_ids:
        ls.save_oic_attempt(oid, 100, "[]")
    assert ksv.has_rang_a_badge("course-1") is False


# ── Triage ────────────────────────────────────────────────────────────────────

def test_un_item_dun_college_valide_non_declare_est_a_situer():
    ks.set_college_status("Cardiovasculaire ❤️", "valide")
    assert ksv.is_to_situate("course-1", ["Cardiovasculaire ❤️"]) is True


def test_un_item_declare_nest_plus_a_situer():
    ks.set_college_status("Cardiovasculaire ❤️", "valide")
    ks.set_item_state("course-1", "correct")
    assert ksv.is_to_situate("course-1", ["Cardiovasculaire ❤️"]) is False


def test_un_item_dun_college_non_valide_nest_pas_a_situer():
    assert ksv.is_to_situate("course-1", ["Cardiovasculaire ❤️"]) is False


def test_avancement_du_triage():
    ks.set_item_state("course-1", "solide")
    ks.set_item_state("course-2", "flou")
    situes, total = ksv.college_triage_progress(
        "Cardiovasculaire ❤️", ["course-1", "course-2", "course-3"]
    )
    assert (situes, total) == (2, 3)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_knowledge_service.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'backend.core.knowledge.service'`

- [ ] **Step 3: Write the implementation**

Create `backend/core/knowledge/service.py`:

```python
"""
knowledge.service — Synapse
---------------------------
Porte d'entrée unique du domaine « état des connaissances ».

mastery.py ne parle qu'à ce module : il ne connaît ni le SQL, ni les tables.

Responsabilités :
  - calculer la graine dégradée d'un item (get_seed_snapshot)
  - compter les preuves réelles et dater la première (count_evidence, first_evidence_date)
  - agréger la couverture OIC et le badge « Rang A ✓ » (oic_coverage, has_rang_a_badge)
  - exposer l'avancement du triage d'un collège (college_triage_progress)
"""
from __future__ import annotations

import datetime

from backend.core.reviews.local_store import _conn
from backend.core.knowledge import store as ks
from backend.core.knowledge.models import (
    SeedSnapshot, RANG_A_BADGE_THRESHOLD, decayed_seed,
)


# ── Preuves réelles ───────────────────────────────────────────────────────────

def first_evidence_date(course_id: str) -> datetime.date | None:
    """
    Date de la première preuve réelle (session, QCM, tentative OIC), ou None.

    C'est la date à laquelle la dégradation de la graine s'arrête : au-delà,
    c'est l'évidence qui pilote le score, plus le temps.
    """
    with _conn() as con:
        row = con.execute(
            """
            SELECT MIN(d) AS first_d FROM (
                SELECT MIN(session_date) AS d FROM study_sessions WHERE course_id = ?
                UNION ALL
                SELECT MIN(session_date) AS d FROM qcm_sessions   WHERE course_id = ?
                UNION ALL
                SELECT MIN(a.attempted_at) AS d
                    FROM oic_attempts a
                    JOIN lisa_oic o ON o.id = a.oic_id
                   WHERE o.course_id = ?
            )
            """,
            (course_id, course_id, course_id),
        ).fetchone()

    raw = row["first_d"] if row else None
    if not raw:
        return None
    # session_date est une date ISO, attempted_at un timestamp ISO : on tronque.
    return datetime.date.fromisoformat(str(raw)[:10])


def count_evidence(course_id: str) -> int:
    """Nombre de preuves réelles : sessions + QCM + tentatives OIC."""
    with _conn() as con:
        row = con.execute(
            """
            SELECT
                (SELECT COUNT(*) FROM study_sessions WHERE course_id = ?)
              + (SELECT COUNT(*) FROM qcm_sessions   WHERE course_id = ?)
              + (SELECT COUNT(*) FROM oic_attempts a
                    JOIN lisa_oic o ON o.id = a.oic_id
                   WHERE o.course_id = ?) AS n
            """,
            (course_id, course_id, course_id),
        ).fetchone()
    return int(row["n"] or 0)


# ── Graine ────────────────────────────────────────────────────────────────────

def get_seed_snapshot(
    course_id: str,
    context: str = "college",
    today: datetime.date | None = None,
) -> SeedSnapshot:
    """
    Ce que mastery.py a besoin de savoir : le niveau déclaré, sa graine dégradée,
    et le nombre de preuves réelles qui vont la diluer.

    Un item non déclaré renvoie un snapshot vide (seed_score = None) : il reste
    « à situer », il n'hérite d'aucun score par défaut.
    """
    today = today or datetime.date.today()
    state = ks.get_item_state(course_id, context)

    if state is None:
        return SeedSnapshot(declared_level=None, seed_score=None, n_evidence=0)

    n = count_evidence(course_id)
    until = first_evidence_date(course_id) or today

    return SeedSnapshot(
        declared_level=state.declared_level,
        seed_score=decayed_seed(state.declared_level, state.declared_at, until),
        n_evidence=n,
    )


# ── Couverture OIC ────────────────────────────────────────────────────────────

def oic_coverage(course_id: str) -> dict:
    """
    Couverture des objectifs de connaissance d'un item.

    Le rang A conditionne le badge ; le rang B est affiché sans jamais rien
    conditionner — l'ériger en condition transformerait un bonus en dette infinie.
    """
    with _conn() as con:
        rows = con.execute(
            "SELECT rang, mastered FROM lisa_oic WHERE course_id = ?", (course_id,)
        ).fetchall()

    def _tally(rang: str) -> tuple[int, int]:
        subset = [r for r in rows if (r["rang"] or "").strip().upper() == rang]
        return len(subset), sum(1 for r in subset if r["mastered"])

    a_total, a_ok = _tally("A")
    b_total, b_ok = _tally("B")

    return {
        "rang_a_total": a_total,
        "rang_a_ok":    a_ok,
        "rang_a_pct":   (a_ok / a_total) if a_total else 0.0,
        "rang_b_total": b_total,
        "rang_b_ok":    b_ok,
        "rang_b_pct":   (b_ok / b_total) if b_total else 0.0,
    }


def badge_from_coverage(cov: dict) -> bool:
    """
    Badge « Rang A ✓ » à partir d'une couverture déjà chargée.

    Existe pour que mastery.py — qui tourne sur plusieurs centaines de cours —
    n'ait pas à requêter la couverture une seconde fois juste pour le badge.
    """
    if cov["rang_a_total"] == 0:
        return False
    return cov["rang_a_pct"] >= RANG_A_BADGE_THRESHOLD


def has_rang_a_badge(course_id: str) -> bool:
    """Badge « Rang A ✓ » : au moins un OIC de rang A, et >= 80 % réussis."""
    return badge_from_coverage(oic_coverage(course_id))


# ── Triage ────────────────────────────────────────────────────────────────────

def is_to_situate(course_id: str, colleges: list[str], context: str = "college") -> bool:
    """
    Un item est « à situer » s'il appartient à un collège validé
    et n'a encore reçu aucun niveau déclaré. État calculé, jamais stocké.
    """
    statuses = ks.get_all_college_statuses()
    in_validated = any(statuses.get(c) == "valide" for c in (colleges or []))
    if not in_validated:
        return False
    return ks.get_item_state(course_id, context) is None


def college_triage_progress(
    college: str,
    course_ids: list[str],
    context: str = "college",
) -> tuple[int, int]:
    """(nombre d'items situés, nombre total d'items) pour un collège."""
    states = ks.get_all_item_states(context)
    situes = sum(1 for cid in course_ids if cid in states)
    return situes, len(course_ids)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_knowledge_service.py -v`
Expected: PASS — 16 tests.

- [ ] **Step 5: Commit**

```bash
git add backend/core/knowledge/service.py tests/test_knowledge_service.py
git commit -m "feat(knowledge): service — graine dégradée, preuves et couverture OIC"
```

---

### Task 5: Branchement dans `mastery.py`

Le point d'articulation. Deux changements, tous deux petits, dans `backend/core/reviews/mastery.py`.

1. **Lever le verrou :** aujourd'hui un cours sans `date_1ere_lecture` sort en `score = None` (ligne 77-82) — c'est ce qui rend les anciens collèges invisibles. Un item **déclaré** doit désormais traverser ce verrou.
2. **Fusionner :** avant la détermination du niveau (ligne 137), fusionner le score calculé avec la graine.

**Files:**
- Modify: `backend/core/reviews/mastery.py` (dataclass ligne 15-27, verrou ligne 77-82, fusion ligne 135-137)
- Test: `tests/test_knowledge_mastery.py`

**Interfaces:**
- Consumes: `knowledge.service.get_seed_snapshot`, `knowledge.service.oic_coverage`, `knowledge.service.has_rang_a_badge`, `knowledge.models.blend`, `knowledge.models.level_from_seed`.
- Produces: `CourseProgressSnapshot` gagne trois champs — `declared_level: str | None = None`, `oic_coverage_a: float = 0.0`, `has_rang_a_badge: bool = False`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_knowledge_mastery.py`:

```python
"""Tests — mastery.py exploite la graine déclarée (knowledge)."""
import datetime
import pytest
from types import SimpleNamespace


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    import backend.core.reviews.local_store as ls
    import backend.core.knowledge.store as ks

    test_db = tmp_path / "test.db"
    monkeypatch.setattr(ls, "DB_PATH", test_db)
    monkeypatch.setattr(ls, "_DB", None)
    ls.init_db()
    ks.init_knowledge_tables()
    yield
    if ls._DB is not None:
        ls._DB.close()
    monkeypatch.setattr(ls, "_DB", None)


import backend.core.knowledge.store as ks
from backend.core.reviews.mastery import get_course_mastery


def _course(course_id="course-1", first_read=None, nb_lectures=0):
    """Faux cours : ancien item d'un collège validé, jamais lu dans Synapse."""
    return SimpleNamespace(
        id=course_id,
        title="Item test",
        url_pdf="http://pdf",
        url_pdf_ue=None,
        date_1ere_lecture=first_read,
        date_1ere_lecture_ue=None,
        nb_lectures=nb_lectures,
        nb_lectures_ue=0,
        anki=False,
        qcm_done=False,
        college=["Cardiovasculaire ❤️"],
    )


# ── Le verrou est levé pour un item déclaré ───────────────────────────────────

def test_item_non_declare_et_jamais_lu_reste_sans_score():
    """Non-régression : un item non déclaré garde score = None (état 'à lire')."""
    snap = get_course_mastery(_course())
    assert snap.score is None
    assert snap.level == "à lire"


def test_item_declare_et_jamais_lu_recoit_la_graine_comme_score():
    ks.set_item_state("course-1", "solide")
    snap = get_course_mastery(_course())
    assert snap.score == 70
    assert snap.level == "à consolider"
    assert snap.declared_level == "solide"


def test_les_trois_crans_donnent_trois_niveaux_distincts():
    for level, expected_score, expected_label in [
        ("solide", 70, "à consolider"),
        ("correct", 50, "fragile"),
        ("flou", 30, "critique"),
    ]:
        ks.set_item_state("course-x", level)
        snap = get_course_mastery(_course("course-x"))
        assert snap.score == expected_score
        assert snap.level == expected_label


# ── La fusion avec les preuves réelles ────────────────────────────────────────

def test_une_preuve_reelle_dilue_la_graine_de_moitie():
    import backend.core.reviews.local_store as ls

    ks.set_item_state("course-1", "solide")            # graine 70
    ls.add_study_session(course_id="course-1", activity_types=["révision"], confidence=1)

    course = _course(first_read=datetime.date.today(), nb_lectures=1)
    sessions = ls.get_sessions_by_course().get("course-1", [])
    snap = get_course_mastery(course, sessions=sessions)

    # calculé : 50 - 5 (1 lecture) - 15 (confiance basse) = 30
    # fusion  : 0.5 * 70 + 0.5 * 30 = 50
    assert snap.score == 50


def test_sans_declaration_le_score_calcule_est_inchange():
    """Non-régression : un cours normal n'est pas affecté par le nouveau code."""
    import backend.core.reviews.local_store as ls

    ls.add_study_session(course_id="course-1", activity_types=["révision"], confidence=1)
    course = _course(first_read=datetime.date.today(), nb_lectures=1)
    sessions = ls.get_sessions_by_course().get("course-1", [])
    snap = get_course_mastery(course, sessions=sessions)

    assert snap.score == 30   # 50 - 5 - 15, aucune graine
    assert snap.declared_level is None


# ── Couverture OIC exposée dans le snapshot ───────────────────────────────────

def test_le_snapshot_expose_la_couverture_oic_et_le_badge():
    import backend.core.reviews.local_store as ls

    ks.set_item_state("course-1", "solide")
    ls.upsert_lisa_oic("course-1", [
        {"oic_code": "OIC-1", "intitule": "O1", "rang": "A", "rubrique": "Déf", "ordre": 1},
    ])
    oic_id = ls.get_lisa_oic("course-1")[0]["id"]
    ls.save_oic_attempt(oic_id, 90, "[]")

    snap = get_course_mastery(_course())
    assert snap.oic_coverage_a == 1.0
    assert snap.has_rang_a_badge is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_knowledge_mastery.py -v`
Expected: FAIL — `test_item_declare_et_jamais_lu_recoit_la_graine_comme_score` échoue (`snap.score is None`), et les tests sur `declared_level` échouent avec `AttributeError`.

- [ ] **Step 3: Implémenter — dataclass**

Dans `backend/core/reviews/mastery.py`, ajouter trois champs à `CourseProgressSnapshot` (après `next_action`, ligne 27) :

```python
@dataclass
class CourseProgressSnapshot:
    course_id: str
    context: Literal["college", "ue"]
    level: str
    score: int | None
    has_pdf: bool
    has_first_read: bool
    nb_lectures: int
    qcm_done: bool
    anki_done: bool
    reasons: list[str] = field(default_factory=list)
    next_action: str = ""
    # ── Socle « état des connaissances » ──────────────────────────────────────
    declared_level: str | None = None      # solide | correct | flou
    oic_coverage_a: float = 0.0            # part d'OIC de rang A réussis
    has_rang_a_badge: bool = False
```

- [ ] **Step 4: Implémenter — lever le verrou et fusionner**

Toujours dans `get_course_mastery()` :

**(a)** Juste après le bloc `sessions = sessions or []` (ligne 59), charger la graine :

```python
    sessions = sessions or []

    # ── Socle « état des connaissances » ──────────────────────────────────────
    # Un item déclaré (ancien collège validé) possède une graine de score qui se
    # dégrade avec le temps et se dilue devant les preuves réelles.
    from backend.core.knowledge.service import (
        get_seed_snapshot, oic_coverage, badge_from_coverage,
    )
    from backend.core.knowledge.models import blend, level_from_seed

    seed = get_seed_snapshot(course.id, context)
    _cov = oic_coverage(course.id)          # une seule lecture, réutilisée pour le badge
    _extra = {
        "declared_level":   seed.declared_level,
        "oic_coverage_a":   _cov["rang_a_pct"],
        "has_rang_a_badge": badge_from_coverage(_cov),
    }
```

**(b)** Remplacer le verrou « pas de première lecture » (lignes 77-82) par :

```python
    if not has_first_read:
        # Item déclaré sans preuve réelle : la graine tient lieu de score.
        # C'est ce qui rend planifiables les items des anciens collèges validés.
        if seed.seed_score is not None and seed.n_evidence == 0:
            return CourseProgressSnapshot(
                course_id=course.id, context=context,
                level=level_from_seed(seed.seed_score), score=seed.seed_score,
                has_pdf=has_pdf, has_first_read=has_first_read, nb_lectures=nb_lectures,
                qcm_done=qcm_done, anki_done=anki_done,
                reasons=[f"Niveau déclaré : {seed.declared_level}"],
                next_action="Réviser", **_extra,
            )
        if seed.seed_score is None:
            return CourseProgressSnapshot(
                course_id=course.id, context=context, level="à lire", score=None,
                has_pdf=has_pdf, has_first_read=has_first_read, nb_lectures=nb_lectures,
                qcm_done=qcm_done, anki_done=anki_done,
                reasons=["Première lecture manquante"], next_action="1ère lecture",
                **_extra,
            )
        # Item déclaré ET porteur de preuves : on poursuit vers le calcul normal.
```

**(c)** Ajouter `**_extra` au premier `return` (le cas « à préparer », lignes 71-75) :

```python
    if not has_pdf and not has_first_read:
        return CourseProgressSnapshot(
            course_id=course.id, context=context, level="à préparer", score=None,
            has_pdf=has_pdf, has_first_read=has_first_read, nb_lectures=nb_lectures,
            qcm_done=qcm_done, anki_done=anki_done, reasons=["Pas de PDF lié"],
            next_action="Lier PDF", **_extra,
        )
```

**(d)** Fusionner juste avant la détermination du niveau (ligne 135, `score = max(0, min(100, score))`) :

```python
    score = max(0, min(100, score))

    # Fusion graine / évidence : le poids de la graine décroît avec les preuves.
    if seed.seed_score is not None:
        score = blend(seed.seed_score, score, seed.n_evidence)
        reasons.append(f"Niveau déclaré : {seed.declared_level}")
```

**(e)** Ajouter `**_extra` au `return` final (ligne 162) :

```python
    return CourseProgressSnapshot(
        course_id=course.id,
        context=context,
        level=level,
        score=score,
        has_pdf=has_pdf,
        has_first_read=has_first_read,
        nb_lectures=nb_lectures,
        qcm_done=qcm_done,
        anki_done=anki_done,
        reasons=reasons[:3],
        next_action=next_action,
        **_extra,
    )
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_knowledge_mastery.py -v`
Expected: PASS — 6 tests.

- [ ] **Step 6: Commit**

```bash
git add backend/core/reviews/mastery.py tests/test_knowledge_mastery.py
git commit -m "feat(mastery): fusionner la graine déclarée avec le score calculé"
```

---

### Task 6: Non-régression du moteur de révisions

Le test le plus important du bloc. Un item déclaré devient planifiable **mais ne doit générer aucune tâche J3/J7/J14/J30** faute de `date_1ere_lecture` — son cycle d'entretien est le sujet du bloc 2. Si ce test passe, on sait que le bloc 1 n'a modifié la date, la priorité ou le statut d'aucune tâche existante.

**Files:**
- Test: `tests/test_knowledge_no_regression.py`
- Modify: aucun fichier de production. Si un test échoue ici, le bug est dans la Task 5.

**Interfaces:**
- Consumes: `ReviewService.generate_reviews`, `knowledge.store.set_item_state`.
- Produces: rien.

- [ ] **Step 1: Write the tests**

Create `tests/test_knowledge_no_regression.py`:

```python
"""
Non-régression — le socle « état des connaissances » ne touche pas aux tâches JX.

Un item déclaré (ancien collège validé) devient planifiable, mais ne produit
aucune tâche J3/J7/J14/J30 : la génération JX exige une date_1ere_lecture qu'il
n'a pas. Son cycle d'entretien relève du bloc 2 (moteur de planification).
"""
import datetime
import pytest
from types import SimpleNamespace


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    import backend.core.reviews.local_store as ls
    import backend.core.knowledge.store as ks

    test_db = tmp_path / "test.db"
    monkeypatch.setattr(ls, "DB_PATH", test_db)
    monkeypatch.setattr(ls, "_DB", None)
    ls.init_db()
    ks.init_knowledge_tables()
    yield
    if ls._DB is not None:
        ls._DB.close()
    monkeypatch.setattr(ls, "_DB", None)


import backend.core.knowledge.store as ks
from backend.core.reviews.service import ReviewService


def _course(course_id, first_read=None):
    return SimpleNamespace(
        id=course_id, title=f"Item {course_id}", item_number="230",
        college=["Cardiovasculaire ❤️"],
        url_pdf="http://pdf", url_pdf_ue=None,
        agregation_fiche_edn=None,
        date_1ere_lecture=first_read, date_1ere_lecture_ue=None,
        nb_lectures=1 if first_read else 0, nb_lectures_ue=0,
        lecture_j3_college=None, lecture_j7_college=None,
        lecture_j14_college=None, lecture_j30_college=None,
        lecture_j3_ue=None, lecture_j7_ue=None,
        lecture_j14_ue=None, lecture_j30_ue=None,
        anki=False, qcm_done=False, course_status="À lire",
    )


@pytest.fixture
def fake_store(monkeypatch):
    import backend.state.store as store_mod
    fake = SimpleNamespace(cours=[], active_stage=None, semantic_graph={})
    monkeypatch.setattr(store_mod, "data_store", fake)
    return fake


def test_item_declare_sans_premiere_lecture_ne_genere_aucune_tache_jx(fake_store):
    ks.set_college_status("Cardiovasculaire ❤️", "valide")
    ks.set_item_state("old-1", "solide")
    fake_store.cours = [_course("old-1")]

    tasks = ReviewService().generate_reviews("college")
    assert tasks == []


def test_un_cours_normal_genere_toujours_ses_taches_jx(fake_store):
    """Le comportement existant est intact."""
    fake_store.cours = [_course("new-1", first_read=datetime.date.today() - datetime.timedelta(days=10))]

    tasks = ReviewService().generate_reviews("college")
    types = {t.review_type for t in tasks}
    assert types == {"J3", "J7", "J14", "J30"}


def test_declarer_un_cours_deja_lu_ne_change_ni_ses_dates_ni_ses_types(fake_store):
    """Une déclaration peut déplacer le score, jamais les échéances."""
    first_read = datetime.date.today() - datetime.timedelta(days=10)
    fake_store.cours = [_course("new-1", first_read=first_read)]

    before = {(t.review_type, t.due_date) for t in ReviewService().generate_reviews("college")}

    ks.set_item_state("new-1", "flou")
    after = {(t.review_type, t.due_date) for t in ReviewService().generate_reviews("college")}

    assert before == after
```

- [ ] **Step 2: Run tests**

Run: `python -m pytest tests/test_knowledge_no_regression.py -v`
Expected: PASS — 3 tests. **Si l'un échoue, ne pas modifier le test : corriger la Task 5.**

- [ ] **Step 3: Run the full suite**

Run: `python -m pytest tests/ -v`
Expected: PASS, à l'exception des 5 échecs pré-existants connus (scraper LiSA et sync des lacunes). Aucun **nouvel** échec.

- [ ] **Step 4: Commit**

```bash
git add tests/test_knowledge_no_regression.py
git commit -m "test(knowledge): non-régression — aucune tâche JX parasite pour un item déclaré"
```

---

### Task 7: UI — statut du collège et avancement du triage

**Files:**
- Modify: `frontend/pages/colleges.py` (helper `_compute_stats` ligne 70 ; en-tête d'onglet dans `_show()`)
- Vérification: manuelle (NiceGUI)

**Interfaces:**
- Consumes: `knowledge.store.get_college_status`, `knowledge.store.set_college_status`, `knowledge.service.college_triage_progress`.
- Produces: rien pour les autres tâches.

- [ ] **Step 1: Enrichir `_compute_stats`**

Dans `frontend/pages/colleges.py`, ajouter les imports en tête de fichier :

```python
from backend.core.knowledge import store as knowledge_store
from backend.core.knowledge import service as knowledge_service
```

Puis étendre `_compute_stats` (ligne 70) :

```python
def _compute_stats(name: str) -> dict:
    courses = data_store.get_cours_for_college(name)
    total = len(courses)
    started = sum(1 for c in courses if c.date_1ere_lecture)
    pct = started / total if total > 0 else 0.0

    status = knowledge_store.get_college_status(name)
    situes, n_items = knowledge_service.college_triage_progress(
        name, [c.id for c in courses]
    )

    return {
        "total":   total,
        "started": started,
        "pct":     pct,
        "level":   _college_level(pct),
        "status":  status,             # non_etudie | en_cours | valide
        "situes":  situes,
        "n_items": n_items,
    }
```

- [ ] **Step 2: Ajouter le sélecteur de statut dans l'en-tête d'onglet**

Dans `_show()`, à l'intérieur du bloc qui rend l'onglet du collège sélectionné (juste sous le titre du collège), insérer :

```python
            # ── Statut académique du collège ──────────────────────────────────
            _st = all_stats[tab]

            with ui.row().classes("items-center gap-3 mb-4"):
                STATUS_LABELS = {
                    "non_etudie": "Non étudié",
                    "en_cours":   "En cours",
                    "valide":     "Validé",
                }

                def _on_status_change(e, _name=tab):
                    knowledge_store.set_college_status(_name, e.value)
                    review_service.invalidate_cache()
                    ui.notify(f"{_name} : {STATUS_LABELS[e.value]}", type="positive")
                    _refresh_view()

                ui.select(
                    options=STATUS_LABELS,
                    value=_st["status"],
                    on_change=_on_status_change,
                ).props("dense outlined").classes("w-40")

                if _st["status"] == "valide":
                    ui.label(
                        f"{_st['situes']} items situés sur {_st['n_items']}"
                    ).classes("text-xs text-slate-500")

                    ui.button(
                        "Trier maintenant",
                        on_click=lambda _name=tab: ui.navigate.to(f"/triage/{_name}"),
                    ).props("flat dense size=sm color=indigo")
```

Ajouter l'import de `review_service` en tête de fichier s'il n'y est pas déjà :

```python
from backend.core.reviews.service import review_service
```

- [ ] **Step 3: Vérification manuelle**

Lancer l'app (`python main.py`), aller sur `/colleges`, sélectionner Cardiovasculaire, passer le statut à **Validé**.

Attendu : le libellé « 0 items situés sur N » apparaît, ainsi que le bouton *Trier maintenant*. Recharger la page : le statut est conservé.

- [ ] **Step 4: Commit**

```bash
git add frontend/pages/colleges.py
git commit -m "feat(ui): statut académique du collège et avancement du triage"
```

---

### Task 8: UI — écran de triage groupé

**Files:**
- Create: `frontend/pages/triage.py`
- Modify: `main.py` (enregistrement de la route)
- Vérification: manuelle

**Interfaces:**
- Consumes: `knowledge.store.set_item_state`, `knowledge.store.get_all_item_states`, `data_store.get_cours_for_college`.
- Produces: route `/triage/{college}`, appelée par le bouton de la Task 7.

- [ ] **Step 1: Créer la page**

Create `frontend/pages/triage.py` :

```python
"""
triage.py — Écran de triage groupé d'un collège validé
------------------------------------------------------
Option A de la spec : attribuer en une passe un niveau déclaré aux items d'un
collège validé. Toujours facultatif — le triage progressif (au fil des sessions)
reste le chemin par défaut.

Quittable à tout moment : ce qui est trié est acquis, le reste reste « à situer ».
"""
from urllib.parse import unquote

from nicegui import ui

from frontend.theme import frame
from backend.state.store import data_store
from backend.core.knowledge import store as knowledge_store
from backend.core.reviews.service import review_service


LEVELS = [
    ("solide",  "Solide",  "positive"),
    ("correct", "Correct", "warning"),
    ("flou",    "Flou",    "negative"),
]


@ui.page("/triage/{college}")
@frame("Triage")
def triage_page(college: str):
    college = unquote(college)

    if not data_store.is_loaded:
        ui.label("Chargement des données…").classes("text-slate-500")
        return

    courses = data_store.get_cours_for_college(college)
    if not courses:
        ui.label(f"Aucun item dans {college}.").classes("text-slate-500")
        return

    root = ui.column().classes("w-full gap-0")

    def _render():
        states = knowledge_store.get_all_item_states("college")
        situes = sum(1 for c in courses if c.id in states)

        root.clear()
        with root:
            ui.label(f"Triage — {college}").classes(
                "synapse-display text-[22px] font-extrabold text-slate-900 "
                "dark:text-slate-50 tracking-tight"
            )
            ui.label(
                f"{situes} items situés sur {len(courses)} · "
                "les items non triés restent « à situer » et te seront proposés au fil des révisions."
            ).classes("text-xs text-slate-500 mb-4")

            for c in courses:
                current = states.get(c.id)

                with ui.row().classes(
                    "items-center justify-between w-full gap-3 py-2 "
                    "border-b border-slate-100 dark:border-slate-800"
                ):
                    item_txt = f"ITEM {c.item_number} — " if c.item_number else ""
                    ui.label(f"{item_txt}{c.title}").classes(
                        "text-sm text-slate-800 dark:text-slate-100 flex-1 truncate"
                    )

                    with ui.row().classes("gap-1 shrink-0"):
                        for level, label, color in LEVELS:
                            selected = current is not None and current.declared_level == level

                            def _set(_cid=c.id, _level=level):
                                knowledge_store.set_item_state(
                                    _cid, _level, context="college", source="triage"
                                )
                                review_service.invalidate_cache()
                                _render()

                            ui.button(label, on_click=_set).props(
                                f"unelevated rounded size=sm color={color}"
                                if selected else
                                "outline rounded size=sm color=grey"
                            )

            ui.button(
                "Retour aux collèges",
                on_click=lambda: ui.navigate.to("/colleges"),
            ).props("flat dense color=indigo").classes("mt-4")

    _render()
```

- [ ] **Step 2: Enregistrer la route**

Dans `main.py`, à côté des autres imports de pages (`from frontend.pages import ...`), ajouter `triage` à la liste des modules importés. NiceGUI enregistre la route au moment de l'import du module — aucun autre câblage n'est nécessaire.

- [ ] **Step 3: Vérification manuelle**

Lancer l'app, aller sur `/colleges`, valider Cardiovasculaire, cliquer *Trier maintenant*.

Attendu : la liste des items apparaît ; cliquer *Correct* sur un item met le bouton en surbrillance et incrémente le compteur « N items situés ». Revenir aux collèges : le compteur y est aussi à jour.

- [ ] **Step 4: Commit**

```bash
git add frontend/pages/triage.py main.py
git commit -m "feat(ui): écran de triage groupé d'un collège validé"
```

---

### Task 9: UI — niveau déclaré et couverture OIC sur la fiche cours

**Files:**
- Modify: `frontend/pages/course_detail.py`
- Vérification: manuelle

**Interfaces:**
- Consumes: `knowledge.store.get_item_state`, `knowledge.store.set_item_state`, `knowledge.service.oic_coverage`, `knowledge.service.has_rang_a_badge`.
- Produces: rien.

- [ ] **Step 1: Ajouter le bloc « état déclaré »**

Dans `frontend/pages/course_detail.py`, ajouter les imports :

```python
from backend.core.knowledge import store as knowledge_store
from backend.core.knowledge import service as knowledge_service
from backend.core.reviews.service import review_service
```

Puis, dans le rendu de la fiche (sous l'en-tête du cours), insérer un bloc rendu par cette fonction, à appeler avec le cours courant :

```python
def _render_knowledge_block(course) -> None:
    """Niveau déclaré (modifiable à tout moment) + couverture OIC."""
    container = ui.column().classes("w-full gap-2 mb-4")

    def _render():
        state = knowledge_store.get_item_state(course.id, "college")
        cov = knowledge_service.oic_coverage(course.id)
        badge = knowledge_service.has_rang_a_badge(course.id)

        container.clear()
        with container:
            with ui.row().classes("items-center gap-2"):
                ui.label("Niveau déclaré").classes(
                    "text-xs font-semibold text-slate-500 uppercase tracking-wide"
                )
                if state is None:
                    ui.badge("À situer").props("color=grey outline")

            with ui.row().classes("items-center gap-1"):
                for level, label, color in [
                    ("solide", "Solide", "positive"),
                    ("correct", "Correct", "warning"),
                    ("flou", "Flou", "negative"),
                ]:
                    selected = state is not None and state.declared_level == level

                    def _set(_level=level):
                        knowledge_store.set_item_state(
                            course.id, _level, context="college", source="triage"
                        )
                        review_service.invalidate_cache()
                        _render()

                    ui.button(label, on_click=_set).props(
                        f"unelevated rounded size=sm color={color}"
                        if selected else
                        "outline rounded size=sm color=grey"
                    )

            if cov["rang_a_total"] or cov["rang_b_total"]:
                with ui.row().classes("items-center gap-3 mt-1"):
                    ui.label(
                        f"OIC rang A : {cov['rang_a_ok']}/{cov['rang_a_total']} "
                        f"({int(cov['rang_a_pct'] * 100)} %)"
                    ).classes("text-xs text-slate-500")

                    if cov["rang_b_total"]:
                        ui.label(
                            f"rang B : {cov['rang_b_ok']}/{cov['rang_b_total']}"
                        ).classes("text-xs text-slate-400")

                    if badge:
                        ui.badge("Rang A ✓").props("color=green")

    _render()
```

- [ ] **Step 2: Vérification manuelle**

Ouvrir la fiche d'un item d'un collège validé et non trié.

Attendu : le badge « À situer » apparaît ; cliquer *Solide* le fait disparaître et met le bouton en surbrillance. Si l'item a des OIC évalués, la couverture rang A s'affiche, et le badge « Rang A ✓ » apparaît au-delà de 80 %.

- [ ] **Step 3: Commit**

```bash
git add frontend/pages/course_detail.py
git commit -m "feat(ui): niveau déclaré et couverture OIC sur la fiche cours"
```

---

### Task 10: UI — la modale de session situe les items « à situer »

C'est le cœur de l'option B, et le chemin par défaut du triage progressif : la déclaration devient un sous-produit d'une vraie révision, pas une corvée de saisie.

**Files:**
- Modify: `frontend/pages/dashboard/_dialogs.py` (fonction `open_session_feedback_dialog`, ligne 203)
- Vérification: manuelle

**Interfaces:**
- Consumes: `knowledge.service.is_to_situate`, `knowledge.store.set_item_state`.
- Produces: rien.

- [ ] **Step 1: Ajouter le champ conditionnel**

Dans `frontend/pages/dashboard/_dialogs.py`, ajouter les imports :

```python
from backend.core.knowledge import store as knowledge_store
from backend.core.knowledge import service as knowledge_service
```

Dans `open_session_feedback_dialog()`, juste après la construction de `state_fb` (ligne ~225), ajouter :

```python
    # ── Socle « état des connaissances » ──────────────────────────────────────
    # Si l'item vient d'un collège validé et n'a pas encore de niveau déclaré,
    # la séance est l'occasion de le situer — un clic, dans un écran déjà ouvert.
    _to_situate = knowledge_service.is_to_situate(task.course_id, task.college or [])
    state_fb.declared_level = None
```

Puis, dans le corps de la modale (à la suite du bloc des chips de difficulté), insérer :

```python
            if _to_situate:
                with ui.element("div").classes("px-6 py-3"):
                    ui.label("Où en es-tu sur cet item ?").classes(
                        "text-xs font-semibold text-slate-500 uppercase tracking-wide mb-2"
                    )
                    with ui.row().classes("gap-1"):
                        for _lvl, _lbl, _col in [
                            ("solide", "Solide", "positive"),
                            ("correct", "Correct", "warning"),
                            ("flou", "Flou", "negative"),
                        ]:
                            def _pick(_l=_lvl):
                                state_fb.declared_level = _l
                                _render_declared()

                            _b = ui.button(_lbl, on_click=_pick)
                            _b.props(_chip_off())
                            _declared_buttons[_lvl] = _b

                    def _render_declared():
                        for _l, _btn in _declared_buttons.items():
                            _col = {"solide": "positive", "correct": "warning",
                                    "flou": "negative"}[_l]
                            _btn.props(
                                _chip_on(_col) if state_fb.declared_level == _l
                                else _chip_off()
                            )
```

Déclarer `_declared_buttons: dict = {}` juste avant le `with ui.dialog()`.

- [ ] **Step 2: Persister à la validation**

Dans le handler de validation de la modale (celui qui appelle `validate_fn`), avant l'appel :

```python
        if state_fb.declared_level:
            knowledge_store.set_item_state(
                task.course_id, state_fb.declared_level,
                context=task.context, source="reprise",
            )
```

- [ ] **Step 3: Vérification manuelle**

Valider une session sur un item d'un collège validé non encore trié, depuis le dashboard.

Attendu : la modale affiche « Où en es-tu sur cet item ? » avec les trois crans. Après validation, rouvrir une session sur le même item : le champ **n'apparaît plus** (l'item est situé). Le compteur de triage du collège a augmenté de 1.

- [ ] **Step 4: Commit**

```bash
git add frontend/pages/dashboard/_dialogs.py
git commit -m "feat(ui): situer un item « à situer » depuis la modale de séance"
```

---

### Task 11: UI — badge « à situer » sur la CourseCard

**Files:**
- Modify: `frontend/components/course_card.py` (zone des badges, autour de la ligne 315 où les OIC sont déjà comptés)
- Vérification: manuelle

**Interfaces:**
- Consumes: `knowledge.service.is_to_situate`.
- Produces: rien.

- [ ] **Step 1: Ajouter le badge**

Dans `frontend/components/course_card.py`, ajouter l'import :

```python
from backend.core.knowledge import service as knowledge_service
```

Dans la zone de rendu des badges (à côté du badge OIC existant, ligne ~315) :

```python
            if knowledge_service.is_to_situate(course.id, list(course.college or [])):
                ui.badge("À situer").props("color=grey outline").tooltip(
                    "Collège validé, niveau pas encore déclaré"
                )
```

- [ ] **Step 2: Vérification manuelle**

Ouvrir `/colleges` sur un collège validé.

Attendu : les items non triés portent le badge « À situer » ; il disparaît dès qu'un niveau est déclaré.

- [ ] **Step 3: Lancer la suite complète**

Run: `python -m pytest tests/ -v`
Expected: PASS, hors les 5 échecs pré-existants connus. Aucun nouvel échec.

- [ ] **Step 4: Commit**

```bash
git add frontend/components/course_card.py
git commit -m "feat(ui): badge « à situer » sur la carte cours"
```

---

## Vérification finale (critères d'acceptation de la spec)

- [ ] Cocher « Cardiovasculaire ❤️ = validé » rend ses items visibles **sans aucune autre saisie**.
- [ ] Un item « à situer » peut recevoir son niveau soit par l'écran de triage, soit au fil d'une session — les deux chemins produisent le même état en base.
- [ ] Un item déclaré `solide` voit son score baisser avec le temps (vérifiable en rétrodatant `declared_at` en base).
- [ ] Une éval OIC réussie fait plus bouger le score qu'une déclaration ; trois preuves réelles rendent la déclaration négligeable.
- [ ] **Aucune tâche du dashboard ne change de date, de priorité ou de statut du fait de ce bloc** (Task 6).
