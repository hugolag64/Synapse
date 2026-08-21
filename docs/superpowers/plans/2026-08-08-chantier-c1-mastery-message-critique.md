# Chantier C1 — Correction du message trompeur « Socle Rang A critique » Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop `get_course_mastery()` from adding the reason "Socle Rang A critique (<40%)" when
the "critique" level was triggered by a low general score alone, with no Rang A evidence for the
item.

**Architecture:** One-line conditional fix in `backend/core/reviews/mastery.py`, mirroring the
pattern already used by the adjacent `fragile` branch two lines below. No new function, no new
parameter, no data model change.

**Tech Stack:** Python, pytest, existing `local_store`/`knowledge` test fixtures (`ks.set_item_state`,
`ls.upsert_lisa_oic`, `ls.save_oic_attempt`, `ls.add_study_session`).

## Global Constraints

- The `if score < 40 or (...)` condition that sets `level = "critique"` (mastery.py:276-278) is not
  touched — only the `reasons.append(...)` line inside that block becomes conditional.
- No generic replacement message is added for the `score < 40`-only case (user decision) — the
  specific reasons already accumulated earlier in the function (e.g. "confiance basse", "QCM raté")
  remain the only signal in that case.
- The `fragile` branch (mastery.py:281-286) is not touched — it's already correct and serves as the
  reference pattern.
- Full suite (`./.venv/Scripts/python.exe -m pytest -q`) run before Step 1 and after the last step,
  zero regressions.

---

### Task 1: Make the "critique" Rang A message conditional

**Files:**
- Modify: `backend/core/reviews/mastery.py:275-280`
- Test: `tests/test_knowledge_mastery.py`

**Interfaces:**
- Consumes: nothing new — `_has_rang_a_evidence` (bool) and `score_rang_a` (int | None) are already
  computed earlier in `get_course_mastery()` (lines 92 and 258-261) and already in scope at line 279.
- Produces: no new symbols. Behavior change only: `CourseProgressSnapshot.reasons` no longer
  contains `"Socle Rang A critique (<40%)"` unless `_has_rang_a_evidence` is true and
  `score_rang_a < 40`.

- [ ] **Step 1: Run the full suite to record the baseline**

Run: `./.venv/Scripts/python.exe -m pytest -q`
Expected: PASS, 1147 tests (the count left by chantier B4). Step 6 compares against this plus 2 net
new tests.

- [ ] **Step 2: Write the two new tests**

In `tests/test_knowledge_mastery.py`, insert two new tests directly after
`test_cours_sans_preuve_rang_a_n_est_pas_fragile_sur_le_seuil_rang_a` (currently ending at line 73)
and before `test_les_trois_crans_donnent_trois_niveaux_distincts` (currently starting at line 76).
Replace:

```python
def test_cours_sans_preuve_rang_a_n_est_pas_fragile_sur_le_seuil_rang_a():
    ks.set_item_state("course-1", "solide")
    snap = get_course_mastery(
        _course(first_read=datetime.date.today(), nb_lectures=2),
    )

    assert snap.score is not None
    assert 60 <= snap.score < 75
    assert snap.level != "fragile"
    assert "Sécurité Rang A non atteinte (<75%)" not in snap.reasons


def test_les_trois_crans_donnent_trois_niveaux_distincts():
```

with:

```python
def test_cours_sans_preuve_rang_a_n_est_pas_fragile_sur_le_seuil_rang_a():
    ks.set_item_state("course-1", "solide")
    snap = get_course_mastery(
        _course(first_read=datetime.date.today(), nb_lectures=2),
    )

    assert snap.score is not None
    assert 60 <= snap.score < 75
    assert snap.level != "fragile"
    assert "Sécurité Rang A non atteinte (<75%)" not in snap.reasons


def test_critique_par_score_general_sans_preuve_rang_a_omet_le_message():
    """Score général bas (confiance basse), aucune donnée OIC de Rang A pour
    l'item : le niveau critique est déclenché par la branche `score < 40`
    seule, donc le message Rang A ne doit pas apparaître."""
    import backend.core.reviews.local_store as ls

    ls.add_study_session(course_id="course-1", activity_types=["révision"], confidence=1)
    course = _course(first_read=datetime.date.today(), nb_lectures=1)
    sessions = ls.get_sessions_by_course().get("course-1", [])
    snap = get_course_mastery(course, sessions=sessions)

    assert snap.score == 30  # 50 - 5 (1 lecture) - 15 (confiance basse)
    assert snap.level == "critique"
    assert "Socle Rang A critique (<40%)" not in snap.reasons


def test_critique_par_rang_a_conserve_le_message():
    """OIC de Rang A échoué (mastered=0) : score_rang_a chute bien en dessous
    de 40 même si le score général ne l'est pas — le message Rang A doit
    rester présent, c'est le cas où il est légitime."""
    import backend.core.reviews.local_store as ls

    ls.upsert_lisa_oic("course-1", [
        {"oic_code": "OIC-1", "intitule": "O1", "rang": "A", "rubrique": "Déf", "ordre": 1},
    ])
    oic_id = ls.get_lisa_oic("course-1")[0]["id"]
    ls.save_oic_attempt(oic_id, 20, "[]")  # < OIC_SUCCESS_SCORE (70) : reste non maîtrisé

    snap = get_course_mastery(_course(first_read=datetime.date.today(), nb_lectures=2))

    assert snap.level == "critique"
    assert "Socle Rang A critique (<40%)" in snap.reasons


def test_les_trois_crans_donnent_trois_niveaux_distincts():
```

- [ ] **Step 3: Run the new tests to verify they fail for the right reason**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_knowledge_mastery.py -v -k critique`

Expected:
- `test_critique_par_score_general_sans_preuve_rang_a_omet_le_message` — FAIL: `"Socle Rang A
  critique (<40%)" not in snap.reasons` is `False` (current code adds the message unconditionally
  whenever `level == "critique"`, regardless of which branch triggered it).
- `test_critique_par_rang_a_conserve_le_message` — PASS already. This test is a non-regression
  guard, not a red/green driver: the current (buggy) code already adds the message whenever
  `level == "critique"` fires, which includes this Rang-A-caused case. It stays green through Step 4
  — its job is to catch a future regression, not to prove the fix.

- [ ] **Step 4: Apply the fix**

In `backend/core/reviews/mastery.py`, replace:

```python
    if score < 40 or (
        _has_rang_a_evidence and score_rang_a is not None and score_rang_a < 40
    ):
        level = "critique"
        reasons.append("Socle Rang A critique (<40%)")
    elif score < 60 or (
```

with:

```python
    if score < 40 or (
        _has_rang_a_evidence and score_rang_a is not None and score_rang_a < 40
    ):
        level = "critique"
        if _has_rang_a_evidence and score_rang_a is not None and score_rang_a < 40:
            reasons.append("Socle Rang A critique (<40%)")
    elif score < 60 or (
```

- [ ] **Step 5: Run the new tests to verify they pass**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_knowledge_mastery.py -v -k critique`
Expected: both `test_critique_par_score_general_sans_preuve_rang_a_omet_le_message` and
`test_critique_par_rang_a_conserve_le_message` PASS.

- [ ] **Step 6: Run the full suite**

Run: `./.venv/Scripts/python.exe -m pytest -q`
Expected: PASS, 1149 tests (1147 baseline + 2 net new), zero regressions. No existing test asserts
the literal string `"Socle Rang A critique"` (confirmed by a repo-wide grep during the design phase),
so no other test should need updating.

- [ ] **Step 7: Update the tracking doc**

In `docs/UI_REFONTE_ETAT_DES_LIEUX.md`, mark C1 as terminé (commit hash, tests before → after) in
the same table format used for A/B1-B4, and update the "▶ REPRISE" header to point at C2 (or
whichever sub-chantier is picked next) as the next open work. This file stays uncommitted, per the
established convention for this series of chantiers.

- [ ] **Step 8: Commit**

```bash
git add backend/core/reviews/mastery.py tests/test_knowledge_mastery.py
git commit -m "fix: only show Rang A critique reason when Rang A evidence actually triggered it"
```

---

## Self-Review Notes

- **Spec coverage:** "Bug" and "Correction" sections of the spec → Step 4. "Décision utilisateur"
  (no generic replacement message) → reflected in Step 4's diff (nothing added in the `else` case)
  and in Global Constraints. "Tests" section of the spec (both the omission test and the mirror
  non-regression test) → Step 2.
- **Placeholder scan:** none found — every step has literal code, exact commands, exact expected
  output, including the honest caveat in Step 3 that the mirror test doesn't go red (it's a
  non-regression guard, not a TDD driver for this change).
- **Type/name consistency:** no new symbols introduced; the two new test function names are used
  consistently between Step 2 (definition) and Step 3/5 (the `-k critique` filter matches both,
  verified against their names: `test_critique_par_score_general_sans_preuve_rang_a_omet_le_message`
  and `test_critique_par_rang_a_conserve_le_message`, both containing "critique").
