# Tuteur DP, Flash-Zero et Prépa — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Finaliser les trois fonctionnalités locales encore incomplètes : Tuteur DP fiable et guidé, Flash-Zero corrigé question par question, et hub Prépa organisé par fournisseur avec le raccourci Masterclass EDNpro.

**Architecture:** Le service de pratique reste la source de vérité pour la validation et la persistance des sessions. Le Tuteur DP ajoute un retry borné autour de la génération sans jamais persister une réponse invalide ; son interface pilote les étapes de configuration, génération et ouverture. Flash-Zero adopte un état explicite question → correction → question suivante → résumé. Prépa conserve son catalogue SQLite mais construit désormais une vue imbriquée par fournisseur, puis par catégorie.

**Tech Stack:** Python, SQLite via `backend.core.reviews.local_store`, NiceGUI, pytest, CSS inline existant du cockpit.

## Global Constraints

- Ne pas modifier la collecte automatique des sessions personnelles EDNpro/Hypocampus : cette piste est abandonnée.
- Ne pas toucher aux modifications utilisateur existantes dans `UNESS/vérifiés/.imported.json` et `docs/SYNAPSE_AI_CONTEXT.md`.
- Les réponses IA DP doivent respecter exactement le nombre demandé et la répartition fermée/ouvert avant toute persistance.
- Le nombre DP par défaut reste 5, mais il doit être configurable dans l’interface.
- La croix Flash-Zero signifie uniquement « ignorer le Flash-Zero du jour » ; elle ne ferme pas le wizard.
- Les textes et composants doivent rester cohérents avec les primitives Linear/Synapse existantes : bordures fines, surfaces neutres, accent indigo, états lisibles, pas de modale visuellement isolée.

---

### Task 1: Durcir la génération Tuteur DP et ajouter le retry borné

**Files:**
- Modify: `backend/core/practice/service.py`
- Test: `tests/test_ai_practice.py`

**Interfaces:**
- Consumes: `PracticeSessionSpec`, `_prompt_for`, `_parse_questions`, `AIService.generate`.
- Produces: `PracticeService.generate_questions(spec, context="", max_attempts=2)` et `create_tutor_dp_session(..., total_questions=5, max_attempts=2)`.

- [ ] **Step 1: Write the failing tests**

Ajouter des tests avec un faux service IA qui renvoie d’abord un mauvais nombre puis une réponse valide. Vérifier que deux appels sont effectués, que la session est persistée uniquement au second succès, et qu’un second mauvais résultat lève `PracticeGenerationError` sans créer de session. Vérifier également que `total_questions` est rejeté hors de l’intervalle 1–10.

```python
def test_dp_generation_retries_count_mismatch_before_persisting(practice_db):
    ...
    assert fake.calls == 2
    assert len(local_store.get_ai_practice_sessions(limit=10)) == 1

def test_dp_generation_does_not_persist_after_exhausted_retry(practice_db):
    ...
    with pytest.raises(PracticeGenerationError, match="nombre"):
        service.create_tutor_dp_session(..., total_questions=5, max_attempts=2)
    assert local_store.get_ai_practice_sessions(limit=10) == []
```

- [ ] **Step 2: Run the focused tests to verify they fail**

Run: `.venv\Scripts\python.exe -m pytest tests/test_ai_practice.py -q`

Expected: FAIL because `max_attempts` is not accepted and the service currently calls the provider once.

- [ ] **Step 3: Implement the minimal retry contract**

Ajouter une validation bornée de `max_attempts`, construire une instruction de reprise mentionnant la contrainte violée, rappeler `AIService.generate`, puis reparcourir `_parse_questions`. Ne déplacer `create_ai_practice_session` qu’après une génération valide. Conserver l’exception existante pour que l’UI affiche une cause exploitable.

- [ ] **Step 4: Run the focused tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_ai_practice.py -q`

Expected: PASS.

- [ ] **Step 5: Commit the service change**

```powershell
git add backend/core/practice/service.py tests/test_ai_practice.py
git commit -m "fix: retry invalid DP generation responses"
```

---

### Task 2: Transformer le Tuteur DP en wizard NiceGUI

**Files:**
- Modify: `frontend/components/ai_practice_panel.py`
- Modify: `frontend/pages/course_detail_cockpit.py`
- Test: `tests/test_ai_practice.py`

**Interfaces:**
- Consumes: `PracticeService.create_tutor_dp_session`, `build_dp_tutor_context`, item history and gaps.
- Produces: `render_dp_tutor_action(...)` avec étapes `context`, `options`, `generating`, `ready` et lancement uniquement après succès.

- [ ] **Step 1: Write the failing UI-contract tests**

Tester par inspection source et comportement que le wizard expose une sélection de nombre (3, 5, 8, 10), affiche une étape de contexte, utilise `max_attempts=2`, affiche un état de génération, et ne ferme/ou n’ouvre pas la session avant la persistance réussie. Vérifier que le contexte d’un historique réutilise le dossier et non seulement les cinq premiers prompts.

- [ ] **Step 2: Run the focused tests to verify they fail**

Run: `.venv\Scripts\python.exe -m pytest tests/test_ai_practice.py -q`

Expected: FAIL because the current UI contains a single dialog and passes `total_questions=5` directement.

- [ ] **Step 3: Implement the wizard**

Remplacer la modale monolithique par une carte de wizard avec progression visuelle et actions « Retour », « Continuer », « Générer » et « Annuler ». Le premier écran présente la cible (item, erreurs, lacunes), le second permet le nombre et le rappel de la difficulté EDN, le troisième verrouille les contrôles pendant l’appel, et le dernier propose « Ouvrir la session ». Les erreurs restent dans le wizard et indiquent le retry épuisé. Ne jamais déclencher `refresh()` ou `open_qcm_session` avant un `session_id` valide.

- [ ] **Step 4: Run the focused tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_ai_practice.py -q`

Expected: PASS.

- [ ] **Step 5: Commit the wizard change**

```powershell
git add frontend/components/ai_practice_panel.py frontend/pages/course_detail_cockpit.py tests/test_ai_practice.py
git commit -m "feat: add guided DP tutor wizard"
```

---

### Task 3: Refaire le wizard Flash-Zero avec correction immédiate

**Files:**
- Modify: `frontend/components/flash_zero_cockpit.py`
- Modify: `frontend/components/flash_zero_dialog.py`
- Test: `tests/test_flash_zero_cockpit.py`
- Test: `tests/test_flash_zero_integration.py`

**Interfaces:**
- Consumes: `FlashZeroService.get_morning_quiz`, `FlashZeroQuestion`, `complete_daily_flash_zero`, `dismiss_daily_flash_zero`.
- Produces: un flux d’état `question`, `correction`, `complete` dans `open_flash_zero_quiz` et un libellé d’ignorance explicite sur la carte.

- [ ] **Step 1: Write the failing tests**

Vérifier que le code du wizard possède une étape de correction séparée, conserve l’index tant que l’utilisateur n’a pas cliqué sur « Question suivante », affiche l’explication et la bonne réponse, et produit un résumé avec score et erreurs zéro éliminatoire. Vérifier aussi que le contrôle de la carte contient « Ignorer » et n’appelle pas une action de fermeture du wizard.

- [ ] **Step 2: Run the focused tests to verify they fail**

Run: `.venv\Scripts\python.exe -m pytest tests/test_flash_zero_cockpit.py tests/test_flash_zero_integration.py -q`

Expected: FAIL because la version actuelle valide puis incrémente immédiatement et ne possède pas d’étape de correction dédiée.

- [ ] **Step 3: Implement the wizard state machine and Linear UI**

Ajouter un état local `phase`, `selected_idx`, `answered`, `score`, `zero_errors` et `results`. Afficher une barre de progression, un en-tête compact, une carte de question, puis une carte de correction colorée selon le résultat. Le bouton de validation devient désactivé après réponse ; « Question suivante » avance explicitement. La dernière étape affiche le score, le détail des erreurs et l’action de fermeture normale du wizard. Garder la croix de la carte comme action d’ignorance séparée.

- [ ] **Step 4: Run the focused tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_flash_zero_cockpit.py tests/test_flash_zero_integration.py -q`

Expected: PASS.

- [ ] **Step 5: Commit the Flash-Zero change**

```powershell
git add frontend/components/flash_zero_cockpit.py frontend/components/flash_zero_dialog.py tests/test_flash_zero_cockpit.py tests/test_flash_zero_integration.py
git commit -m "feat: add Flash-Zero correction wizard"
```

---

### Task 4: Organiser Prépa par fournisseur et ajouter Masterclass EDNpro

**Files:**
- Modify: `backend/core/prep/catalog.py`
- Modify: `frontend/pages/prepa.py`
- Test: `tests/test_prep_catalog.py`
- Test: `tests/test_prepa_page.py`

**Interfaces:**
- Consumes: `list_prep_providers`, `list_prep_shortcuts`, `record_prep_access`.
- Produces: `build_prepa_view(shortcuts, providers=None)` avec `provider_sections`, chaque section contenant ses catégories et raccourcis.

- [ ] **Step 1: Write the failing tests**

Vérifier que le catalogue EDNpro contient `Masterclass` avec l’URL exacte `https://ednpro.app/masterclass`, et que la vue retourne les fournisseurs dans l’ordre du catalogue, avec les raccourcis imbriqués sous le bon site. Vérifier qu’EDNi apparaît comme fournisseur désactivé même sans raccourci.

```python
def test_ednpro_masterclass_is_seeded(prep_db):
    rows = list_prep_shortcuts("EDNpro")
    assert any(row["title"] == "Masterclass" and row["url"] == "https://ednpro.app/masterclass" for row in rows)

def test_prepa_view_is_provider_first():
    view = build_prepa_view(shortcuts, providers)
    assert [section["provider"] for section in view["provider_sections"]] == ["EDNpro", "Hypocampus", "EDNi"]
```

- [ ] **Step 2: Run the focused tests to verify they fail**

Run: `.venv\Scripts\python.exe -m pytest tests/test_prep_catalog.py tests/test_prepa_page.py -q`

Expected: FAIL because Masterclass is absent and the current view groups globally by category.

- [ ] **Step 3: Implement the provider-first catalogue and page**

Ajouter le raccourci Masterclass aux defaults. Faire évoluer `build_prepa_view` pour fusionner le catalogue fournisseur et les lignes SQLite, puis produire des sections provider-first ; dans chaque section, trier les catégories selon une séquence stable (`accueil`, `masterclass`, `entrainement`, `annales`, `iconographie`, `lca`, `videos`) et les raccourcis par titre/id. Remplacer la section globale de la page par une carte/site par fournisseur, avec en-tête, lien plateforme, badge « bientôt » et grille interne de raccourcis.

- [ ] **Step 4: Run the focused tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_prep_catalog.py tests/test_prepa_page.py -q`

Expected: PASS.

- [ ] **Step 5: Commit the Prépa change**

```powershell
git add backend/core/prep/catalog.py frontend/pages/prepa.py tests/test_prep_catalog.py tests/test_prepa_page.py
git commit -m "feat: organize prep hub by provider"
```

---

### Task 5: Vérification globale, audit et handoff

**Files:**
- Modify: `docs/AUDIT_2026-08-03.md`

- [ ] **Step 1: Run the focused regression suite**

Run: `.venv\Scripts\python.exe -m pytest tests/test_ai_practice.py tests/test_flash_zero_cockpit.py tests/test_flash_zero_integration.py tests/test_prep_catalog.py tests/test_prepa_page.py -q`

Expected: PASS.

- [ ] **Step 2: Run the complete test suite**

Run: `.venv\Scripts\python.exe -m pytest -q`

Expected: PASS with no regression outside the changed features.

- [ ] **Step 3: Update the audit**

Ajouter une entrée datée indiquant le retry DP et le wizard, la correction détaillée Flash-Zero, l’organisation provider-first de Prépa et l’ajout Masterclass. Mentionner explicitement que la collecte des sessions personnelles Hypocampus/EDNpro a été abandonnée et que l’import public EDNpro existant est conservé.

- [ ] **Step 4: Inspect the final diff and status**

Run: `git diff --check; git status --short; git diff --stat`

Expected: aucune erreur de whitespace ; les deux fichiers utilisateur préexistants restent non staged ; seuls les fichiers du lot sont dans les commits dédiés.

- [ ] **Step 5: Commit the audit**

```powershell
git add docs/AUDIT_2026-08-03.md
git commit -m "docs: record tutor flash and prep delivery"
```

