# Lot 1 — Correctifs rapides : plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Corriger les cinq irritants d'usage relevés le 10 août 2026 — persistance du mode sombre, lisibilité du panneau télémétrie, barre de défilement de la couverture DP, longueur de la liste « Récents », correction manquante après un Tuteur DP.

**Architecture:** Cinq correctifs indépendants, sans dépendance entre eux. Quatre sont purement statiques et se valident par pytest. Le cinquième (barre de défilement) exige un diagnostic dans le navigateur avant d'être corrigé, parce que le CSS attendu existe déjà dans le code et que la cause de son inefficacité n'est pas déterminable par lecture seule.

**Tech Stack:** Python 3, NiceGUI (Quasar/Vue), pytest, CSS custom properties du design system Synapse.

## Global Constraints

- Tous les libellés visibles sont en français.
- Aucune couleur en dur : uniquement les variables du design system (`var(--surface)`, `var(--border)`, `var(--text)`, `var(--text-muted)`, `var(--text-dim)`, `var(--bg-alt)`, `var(--success)`, `var(--danger)`, `var(--font-mono)`). Une couleur Tailwind figée du type `bg-slate-900/40` ne suit pas le thème et est un défaut, pas un choix.
- Aucun appel facturé à l'API Gemini pendant ce lot.
- Les tests suivent les conventions du dépôt : assertions sur le texte source pour la structure et le CSS d'une page NiceGUI (voir `tests/test_settings_cockpit_ui.py`), `monkeypatch` et `SimpleNamespace` pour la logique (voir `tests/test_cockpit_shell.py`).
- Un commit par tâche. Message en français, préfixe `fix:`.
- Lancer l'application uniquement via l'outil de prévisualisation, configuration `synapse` (port 8082). Jamais via un shell.

## File Structure

| Fichier | Responsabilité | Tâches |
|---|---|---|
| `frontend/pages/settings_cockpit.py` | Page Réglages : persistance du thème, styles du bloc Diagnostics et télémétrie | 1, 2 |
| `frontend/cockpit_shell.py` | Coquille de l'application : liste « Récents » de la sidebar | 3 |
| `frontend/components/ai_practice_panel.py` | Panneau d'entraînement IA : enchaînement session → correction | 4 |
| `frontend/components/dp_coverage_panel.py` | Panneau Couverture DP : conteneur de défilement | 5 |
| `tests/test_settings_dark_mode.py` | *(créé)* Persistance de la préférence de thème | 1 |
| `tests/test_settings_cockpit_ui.py` | Structure et CSS de la page Réglages | 2 |
| `tests/test_cockpit_shell.py` | Logique de la coquille | 3 |
| `tests/test_dp_tutor.py` | Câblage du Tuteur DP | 4 |
| `tests/test_dp_coverage_panel.py` | Panneau Couverture DP | 5 |

---

### Task 1: B1 — Persister le mode sombre

`toggle_dark_mode` (`frontend/pages/settings_cockpit.py:49`) ne modifie que l'objet `ui.dark_mode()` de la page courante et n'écrit jamais la préférence. La coquille relit pourtant `data_store.preferences["dark_mode"]` à chaque rendu de page (`frontend/cockpit_shell.py:246`) : dès la navigation suivante, l'ancienne valeur écrase le choix.

`data_store.set_preference(key, value)` (`backend/state/store.py:297`) normalise, met à jour et écrit sur disque. C'est déjà ce qu'utilise le sélecteur de fuseau horaire à la ligne 197 du même fichier.

**Files:**
- Create: `tests/test_settings_dark_mode.py`
- Modify: `frontend/pages/settings_cockpit.py:49-57`

**Interfaces:**
- Consumes: `data_store.set_preference(key: str, value) -> None` depuis `backend.state.store`, déjà importé ligne 41 de la page.
- Produces: `toggle_dark_mode(value: bool | None = None) -> bool` — signature inchangée, mais la valeur retournée est désormais garantie booléenne et la préférence est persistée avant le retour.

- [ ] **Step 1: Écrire les tests qui échouent**

Créer `tests/test_settings_dark_mode.py` :

```python
import frontend.pages.settings_cockpit as settings_cockpit


class _FakeDarkMode:
    """Reproduit le contrat de nicegui.ui.dark_mode() utilisé par la page."""

    def __init__(self, value: bool = False) -> None:
        self.value = value

    def enable(self) -> None:
        self.value = True

    def disable(self) -> None:
        self.value = False

    def toggle(self) -> None:
        self.value = not self.value


def _patch(monkeypatch, dark: _FakeDarkMode) -> dict:
    saved: dict = {}
    monkeypatch.setattr(settings_cockpit.ui, "dark_mode", lambda: dark)
    monkeypatch.setattr(
        settings_cockpit.data_store,
        "set_preference",
        lambda key, value: saved.__setitem__(key, value),
    )
    return saved


def test_enabling_dark_mode_persists_the_preference(monkeypatch):
    saved = _patch(monkeypatch, _FakeDarkMode(False))

    assert settings_cockpit.toggle_dark_mode(True) is True
    assert saved == {"dark_mode": True}


def test_disabling_dark_mode_persists_the_preference(monkeypatch):
    saved = _patch(monkeypatch, _FakeDarkMode(True))

    assert settings_cockpit.toggle_dark_mode(False) is False
    assert saved == {"dark_mode": False}


def test_toggle_without_argument_persists_the_resolved_value(monkeypatch):
    saved = _patch(monkeypatch, _FakeDarkMode(False))

    assert settings_cockpit.toggle_dark_mode() is True
    assert saved == {"dark_mode": True}
```

- [ ] **Step 2: Lancer les tests et vérifier qu'ils échouent**

```bash
python -m pytest tests/test_settings_dark_mode.py -v
```

Attendu : les trois tests ÉCHOUENT sur `assert saved == {...}`, `saved` valant `{}` — la préférence n'est jamais écrite.

- [ ] **Step 3: Écrire l'implémentation minimale**

Dans `frontend/pages/settings_cockpit.py`, remplacer la fonction ligne 49 :

```python
def toggle_dark_mode(value: bool | None = None) -> bool:
    dark = ui.dark_mode()
    if value is None:
        dark.toggle()
    elif value:
        dark.enable()
    else:
        dark.disable()
    resolved = bool(dark.value)
    # La coquille relit cette préférence à chaque rendu de page : sans
    # persistance, le thème est réinitialisé à la navigation suivante.
    data_store.set_preference("dark_mode", resolved)
    return resolved
```

- [ ] **Step 4: Lancer les tests et vérifier qu'ils passent**

```bash
python -m pytest tests/test_settings_dark_mode.py -v
```

Attendu : 3 passed.

- [ ] **Step 5: Vérifier l'absence de régression sur les préférences**

```bash
python -m pytest tests/test_app_timezone.py tests/test_settings_sprint_preferences.py -v
```

Attendu : tout passe. Ces suites couvrent le même mécanisme `set_preference` / `save_to_disk`.

- [ ] **Step 6: Commit**

```bash
git add tests/test_settings_dark_mode.py frontend/pages/settings_cockpit.py
git commit -m "fix: persister la preference de mode sombre"
```

---

### Task 2: B2 — Rendre le bloc télémétrie lisible et conforme au thème

L'expansion « CONSOMMATION, TÉLÉMÉTRIE & PARTIELS IMPORTÉS » (`frontend/pages/settings_cockpit.py:462`) porte `bg-slate-900/40 text-sm font-semibold` en dur, là où l'expansion voisine « COUVERTURE DP PAR ITEM » (ligne 457) n'a que sa bordure. D'où le fond gris différent.

Le problème dépasse cette seule classe : tout le contenu du bloc, des lignes 474 à 525, est écrit en Tailwind figé sur une palette sombre — `bg-slate-800/50`, `bg-slate-900/60`, `border-slate-800`, `text-slate-200/300/400/500`, `text-emerald-400`, `text-red-400`. En thème clair c'est illisible ; en thème sombre c'est un gris qui ne correspond à aucune autre surface de l'application.

Ce correctif convertit l'ensemble du bloc aux variables du design system.

**Files:**
- Modify: `frontend/pages/settings_cockpit.py` — bloc `_CSS` (à partir de la ligne 65) et corps du panneau (lignes 456-525)
- Test: `tests/test_settings_cockpit_ui.py`

**Interfaces:**
- Consumes: les variables CSS déjà définies par `frontend/design_tokens.py` et utilisées ailleurs dans la même page — `--surface`, `--border`, `--text`, `--text-muted`, `--text-dim`, `--bg-alt`, `--success`, `--danger`, `--font-mono`.
- Produces: les classes `.se-diag-expansion`, `.se-tele-kpis`, `.se-tele-value`, `.se-tele-strong`, `.se-tele-muted`, `.se-tele-section-title`, `.se-tele-list`, `.se-tele-row`, `.se-tele-name`, `.se-tele-cost`, `.se-tele-ok`, `.se-tele-err`. Aucune autre tâche ne les consomme.

- [ ] **Step 1: Écrire les tests qui échouent**

Ajouter à la fin de `tests/test_settings_cockpit_ui.py` :

```python
def test_diagnostics_expansions_share_one_themed_style():
    source = Path("frontend/pages/settings_cockpit.py").read_text(encoding="utf-8")

    assert ".se-diag-expansion {" in source
    assert source.count('"w-full se-diag-expansion"') == 2


def test_telemetry_panel_uses_design_tokens_instead_of_frozen_slate():
    source = Path("frontend/pages/settings_cockpit.py").read_text(encoding="utf-8")

    for frozen in (
        "bg-slate-900/40",
        "bg-slate-800/50",
        "bg-slate-900/60",
        "border-slate-800",
        "border border-slate-700",
        "text-slate-200",
        "text-slate-300",
        "text-slate-400",
        "text-slate-500",
        "text-emerald-400",
        "text-red-400",
    ):
        assert frozen not in source, f"couleur figee restante : {frozen}"

    for token_class in (
        ".se-tele-kpis {",
        ".se-tele-value {",
        ".se-tele-strong {",
        ".se-tele-muted {",
        ".se-tele-section-title {",
        ".se-tele-list {",
        ".se-tele-row {",
        ".se-tele-cost {",
        ".se-tele-ok {",
        ".se-tele-err {",
    ):
        assert token_class in source
```

- [ ] **Step 2: Lancer les tests et vérifier qu'ils échouent**

```bash
python -m pytest tests/test_settings_cockpit_ui.py -v
```

Attendu : les deux nouveaux tests ÉCHOUENT — `.se-diag-expansion {` absent, `bg-slate-900/40` présent.

- [ ] **Step 3: Ajouter les classes au bloc `_CSS`**

Dans `frontend/pages/settings_cockpit.py`, insérer dans la chaîne `_CSS`, juste avant la règle `.se-uness-card` :

```css
.se-diag-expansion { border:1px solid var(--border); border-radius:10px; background:var(--surface); margin-top:12px; overflow:hidden; }
.se-tele-kpis { display:flex; align-items:center; justify-content:space-between; gap:12px;
  border:1px solid var(--border); border-radius:8px; background:var(--bg-alt); padding:12px 14px; }
.se-tele-value { font-size:20px; font-weight:700; color:var(--success); }
.se-tele-strong { font-size:13px; font-weight:600; color:var(--text); }
.se-tele-muted { font-size:11px; color:var(--text-muted); }
.se-tele-section-title { font-size:10px; text-transform:uppercase; letter-spacing:.04em;
  color:var(--text-dim); font-weight:600; margin:14px 0 6px; }
.se-tele-list { display:flex; flex-direction:column; gap:2px; max-height:190px; overflow-y:auto;
  border:1px solid var(--border); border-radius:8px; background:var(--bg-alt); padding:8px 10px; }
.se-tele-row { display:flex; align-items:center; justify-content:space-between; gap:10px;
  font-size:11.5px; padding:5px 0; border-bottom:1px solid var(--border); }
.se-tele-row:last-child { border-bottom:none; }
.se-tele-name { font-weight:600; color:var(--text); min-width:0; overflow:hidden;
  text-overflow:ellipsis; white-space:nowrap; flex:1 1 auto; }
.se-tele-cost { font-family:var(--font-mono); font-weight:700; color:var(--success); flex:0 0 auto; }
.se-tele-ok { font-family:var(--font-mono); font-weight:700; color:var(--success); flex:0 0 auto; }
.se-tele-err { font-family:var(--font-mono); font-weight:700; color:var(--danger); flex:0 0 auto; }
```

- [ ] **Step 4: Uniformiser les deux expansions**

Remplacer les lignes 457-462 :

```python
            with ui.expansion("COUVERTURE DP PAR ITEM", icon="assignment").classes(
                "w-full se-diag-expansion"
            ):
                render_dp_coverage(ui.column().classes("w-full p-4"))

            with ui.expansion(
                "CONSOMMATION, TÉLÉMÉTRIE & PARTIELS IMPORTÉS", icon="analytics"
            ).classes("w-full se-diag-expansion"):
```

- [ ] **Step 5: Convertir le contenu du panneau**

Remplacer le bloc des cartes KPI (lignes 479-488) :

```python
                    with ui.element("div").classes("se-tele-kpis"):
                        with ui.column().classes("gap-0"):
                            ui.label(f"${total_cost:.4f} USD").classes("se-tele-value")
                            ui.label("Coût IA cumulé").classes("se-tele-muted")
                        with ui.column().classes("gap-0 text-right"):
                            ui.label(f"{total_tok:,} tokens").classes("se-tele-strong")
                            ui.label(f"{total_in:,} entrée · {total_out:,} sortie").classes("se-tele-muted")
                        with ui.column().classes("gap-0 text-right"):
                            ui.label(f"{total_calls} appels").classes("se-tele-strong")
                            ui.label(f"{summary.get('total_errors', 0)} erreur(s)").classes("se-tele-muted")
```

Remplacer le bloc « Coûts par Partiel & Activité » (lignes 491-505) :

```python
                    ui.label("Coûts par Partiel & Activité").classes("se-tele-section-title")
                    by_context = usage_data.get("by_context", [])
                    if not by_context:
                        ui.label("Aucune donnée enregistrée.").classes("se-tele-muted")
                    else:
                        with ui.element("div").classes("se-tele-list"):
                            for item in by_context:
                                ctx_name = item.get("context") or item.get("task") or "Génération générale"
                                cost_val = float(item.get("cost", 0.0))
                                tok_val = int(item.get("tokens", 0))
                                calls_val = int(item.get("calls", 0))
                                with ui.element("div").classes("se-tele-row"):
                                    ui.label(str(ctx_name)).classes("se-tele-name")
                                    ui.label(f"{calls_val} appel(s) · {tok_val:,} tok").classes("se-tele-muted")
                                    ui.label(f"${cost_val:.5f}").classes("se-tele-cost")
```

Remplacer le bloc « Historique des derniers appels Gemini » (lignes 508-525) :

```python
                    ui.label("Historique des derniers appels Gemini").classes("se-tele-section-title")
                    if not recent:
                        ui.label("Aucun appel IA enregistré pour le moment.").classes("se-tele-muted")
                    else:
                        with ui.element("div").classes("se-tele-list"):
                            for call in recent:
                                status_class = "se-tele-err" if call.get("error") else "se-tele-ok"
                                status_text = "ERR" if call.get("error") else "OK"
                                c_usd = float(call.get("cost_usd", 0.0))
                                dur = f"{float(call.get('duration_ms', 0)):.0f}ms" if call.get("duration_ms") else "—"
                                ctx_label = str(call.get("context") or call.get("task") or "gemini_generate")
                                with ui.element("div").classes("se-tele-row"):
                                    with ui.row().classes("items-center gap-2 flex-1 min-w-0"):
                                        ui.label(status_text).classes(status_class)
                                        ui.label(ctx_label).classes("se-tele-name")
                                        ui.label(str(call.get("model"))).classes("se-tele-muted")
                                    with ui.row().classes("items-center gap-3 shrink-0"):
                                        ui.label(
                                            f"{call.get('input_tokens', 0) + call.get('output_tokens', 0)} tok"
                                        ).classes("se-tele-muted")
                                        ui.label(dur).classes("se-tele-muted")
                                        ui.label(f"${c_usd:.5f}").classes("se-tele-cost")
```

Le bloc du panneau s'arrête à cette ligne (ligne 527 avant modification). Les deux tests de l'étape 1 verrouillent le résultat : ils échouent tant qu'une couleur figée subsiste dans le fichier.

- [ ] **Step 6: Lancer les tests et vérifier qu'ils passent**

```bash
python -m pytest tests/test_settings_cockpit_ui.py tests/test_settings_domains.py -v
```

Attendu : tout passe. `test_settings_domains.py` vérifie le regroupement en domaines de la page et ne doit pas régresser.

- [ ] **Step 7: Vérifier le rendu dans les deux thèmes**

Ouvrir la prévisualisation (configuration `synapse`), aller sur `/settings`, déplier la section « DIAGNOSTICS ET TÉLÉMÉTRIE ». Vérifier en thème clair puis en thème sombre que les deux expansions ont exactement le même fond et la même bordure, et que chaque texte du panneau télémétrie est lisible.

- [ ] **Step 8: Commit**

```bash
git add tests/test_settings_cockpit_ui.py frontend/pages/settings_cockpit.py
git commit -m "fix: aligner le panneau telemetrie sur les tokens du theme"
```

---

### Task 3: B4 — Limiter la liste « Récents » à trois entrées

`_recent_nav_entries(limit: int = 5)` (`frontend/cockpit_shell.py:199`) alimente le groupe « Récents » de la sidebar.

Attention à un piège : la fonction demande `limit` identifiants à `get_recent_course_ids`, puis écarte ceux dont le cours a disparu du store. Baisser simplement `limit` à 3 produirait souvent moins de trois entrées. Il faut sur-échantillonner puis tronquer après filtrage.

**Files:**
- Modify: `frontend/cockpit_shell.py:199-222`
- Test: `tests/test_cockpit_shell.py`

**Interfaces:**
- Consumes: `get_recent_course_ids(limit: int) -> list[str]` depuis `backend.core.reviews.local_store`.
- Produces: `_recent_nav_entries(limit: int = 3) -> list[tuple[str, str]]` — au plus `limit` couples `(libellé, route)`, les liens morts étant écartés sans réduire le nombre d'entrées rendues.

- [ ] **Step 1: Écrire les tests qui échouent**

Ajouter à `tests/test_cockpit_shell.py` :

```python
def _course(course_id: str, number: str) -> SimpleNamespace:
    return SimpleNamespace(
        id=course_id,
        title=f"Cours {course_id}",
        item_number=number,
        display_item_number="",
    )


def test_recent_nav_entries_are_capped_at_three(monkeypatch):
    courses = [_course(f"c{i}", str(200 + i)) for i in range(6)]
    monkeypatch.setattr(cockpit_shell.data_store, "cours", courses)
    monkeypatch.setattr(
        "backend.core.reviews.local_store.get_recent_course_ids",
        lambda limit: [course.id for course in courses][:limit],
    )

    entries = cockpit_shell._recent_nav_entries()

    assert len(entries) == 3
    assert entries[0] == ("Item 200 · Cours c0", "/cours/c0")


def test_recent_nav_entries_still_fill_three_slots_despite_dead_links(monkeypatch):
    """Un cours supprimé côté Notion ne doit pas amputer la liste."""
    live = [_course("c1", "201"), _course("c3", "203"), _course("c5", "205")]
    recent_ids = ["c0", "c1", "c2", "c3", "c4", "c5"]
    monkeypatch.setattr(cockpit_shell.data_store, "cours", live)
    monkeypatch.setattr(
        "backend.core.reviews.local_store.get_recent_course_ids",
        lambda limit: recent_ids[:limit],
    )

    entries = cockpit_shell._recent_nav_entries()

    assert [route for _label, route in entries] == ["/cours/c1", "/cours/c3", "/cours/c5"]
```

- [ ] **Step 2: Lancer les tests et vérifier qu'ils échouent**

```bash
python -m pytest tests/test_cockpit_shell.py -v
```

Attendu : le premier test ÉCHOUE avec `len(entries) == 5`. Le second ÉCHOUE avec deux entrées seulement (`c1`, `c3`), puisque seuls cinq identifiants sont demandés et que `c0`, `c2`, `c4` sont écartés.

- [ ] **Step 3: Écrire l'implémentation**

Remplacer l'en-tête et la boucle de `_recent_nav_entries` dans `frontend/cockpit_shell.py` :

```python
def _recent_nav_entries(limit: int = 3) -> list[tuple[str, str]]:
    """(libellé, route) des dernières fiches ouvertes.

    Un cours encore présent dans l'historique local mais disparu du store
    (supprimé côté Notion) est ignoré : on ne rend pas de lien mort. On
    sur-échantillonne donc l'historique pour que ces trous ne réduisent pas
    le nombre d'entrées affichées.
    """
    try:
        from backend.core.reviews.local_store import get_recent_course_ids
        course_ids = get_recent_course_ids(limit=limit * 4)
    except Exception:
        return []

    by_id = {c.id: c for c in data_store.cours}
    entries: list[tuple[str, str]] = []
    for course_id in course_ids:
        course = by_id.get(course_id)
        if course is None:
            continue
        number = str(
            getattr(course, "display_item_number", "") or getattr(course, "item_number", "") or ""
        ).strip()
        label = f"Item {number} · {course.title}" if number else course.title
        entries.append((label, f"/cours/{course.id}"))
        if len(entries) >= limit:
            break
    return entries
```

- [ ] **Step 4: Lancer les tests et vérifier qu'ils passent**

```bash
python -m pytest tests/test_cockpit_shell.py -v
```

Attendu : tout passe.

- [ ] **Step 5: Commit**

```bash
git add tests/test_cockpit_shell.py frontend/cockpit_shell.py
git commit -m "fix: limiter la liste des recents a trois entrees"
```

---

### Task 4: B5 — Ouvrir la correction à la fin d'un Tuteur DP

Dans `render_dp_tutor_action`, la fonction interne `_open_session` (`frontend/components/ai_practice_panel.py:268-275`) lance la session avec `on_complete=lambda _sid: None`. Rien ne s'ouvre donc à la fin.

Le flux standard `_open_answer_dialog` (ligne 134) fait déjà exactement ce qu'il faut : il lance la session et enchaîne vers `_open_correction_dialog` via `open_chained_dialog`. Le correctif consiste à réutiliser ce flux plutôt qu'à le dupliquer.

**Files:**
- Modify: `frontend/components/ai_practice_panel.py:268-275`
- Test: `tests/test_dp_tutor.py`

**Interfaces:**
- Consumes: `_open_answer_dialog(session_id: int, refresh) -> None`, défini ligne 134 du même module ; il capture `ui.context.slot` à l'appel et chaîne `on_complete` vers `_open_correction_dialog(completed_id, refresh)`.
- Produces: aucun symbole nouveau. `render_dp_tutor_action` conserve sa signature.

- [ ] **Step 1: Écrire le test qui échoue**

Dans `tests/test_dp_tutor.py`, ajouter la constante de source à côté de `COCKPIT_SOURCE` (en haut du fichier) :

```python
PANEL_SOURCE = (
    Path(__file__).parents[1] / "frontend/components/ai_practice_panel.py"
).read_text(encoding="utf-8")
```

Puis ajouter le test à la fin du fichier :

```python
def test_tutor_dp_chains_into_the_standard_correction_flow():
    """Terminer un Tuteur DP doit ouvrir sa correction, comme une session normale."""
    tutor_body = _extract_function(PANEL_SOURCE, "render_dp_tutor_action")

    assert "_open_answer_dialog(session_id, refresh)" in tutor_body
    assert "on_complete=lambda _sid: None" not in tutor_body
```

- [ ] **Step 2: Lancer le test et vérifier qu'il échoue**

```bash
python -m pytest tests/test_dp_tutor.py -v
```

Attendu : `test_tutor_dp_chains_into_the_standard_correction_flow` ÉCHOUE sur la première assertion — le corps contient encore `open_qcm_session(session_id, on_complete=lambda _sid: None, on_back=lambda: None)`.

- [ ] **Step 3: Écrire l'implémentation**

Dans `frontend/components/ai_practice_panel.py`, remplacer `_open_session` :

```python
                def _open_session() -> None:
                    session_id = state.get("session_id")
                    if not session_id:
                        return
                    dialog.close()
                    ui.notify(f"Tuteur DP #{session_id} enregistré", type="positive")
                    refresh()
                    # Réutilise le flux standard : il enchaîne vers la correction
                    # une fois la session terminée.
                    _open_answer_dialog(session_id, refresh)
```

- [ ] **Step 4: Lancer les tests et vérifier qu'ils passent**

```bash
python -m pytest tests/test_dp_tutor.py tests/test_ai_practice.py -v
```

Attendu : tout passe. `test_ai_practice.py` couvre la génération et le rejeu des sessions et ne doit pas régresser.

- [ ] **Step 5: Vérifier le parcours dans l'application**

Ouvrir la prévisualisation (configuration `synapse`), aller sur une fiche item disposant d'un historique, onglet Entraînement, ouvrir le Tuteur DP, répondre aux questions jusqu'au bout. La correction doit s'ouvrir immédiatement, sans avoir à la chercher dans l'historique.

Ne pas générer de nouvelle session pour ce test : réutiliser un Tuteur DP déjà enregistré via « Reprendre », afin de ne déclencher aucun appel API facturé.

- [ ] **Step 6: Commit**

```bash
git add tests/test_dp_tutor.py frontend/components/ai_practice_panel.py
git commit -m "fix: enchainer la correction apres un tuteur dp"
```

---

### Task 5: B3 — Rétablir la barre de défilement de « Couverture DP par item »

Cette tâche commence par un diagnostic, pas par un correctif. Le CSS attendu existe déjà : `.dpc-scroll` déclare `max-height:520px; overflow-y:scroll` (`frontend/components/dp_coverage_panel.py:28`) et est bien appliqué à la colonne `table` (ligne 104). Puisque `overflow-y:scroll` affiche une barre en permanence, son absence totale signifie que la règle ne s'applique pas ou qu'un parent la neutralise.

Deux hypothèses à départager, dans cet ordre :

1. **La feuille de style n'est pas dans le document.** `ui.add_head_html(..., shared=True)` est appelé pendant la construction de la page (ligne 95). Si l'injection intervient trop tard pour le rendu courant, aucune règle `.dpc-*` ne s'applique.
2. **Un parent neutralise la contrainte de hauteur.** La colonne porteuse du défilement est un élément flex enfant de `ui.column().classes("w-full p-4")`, lui-même dans le contenu d'une `ui.expansion` Quasar.

**Files:**
- Modify: `frontend/components/dp_coverage_panel.py` — bloc `_CSS` et/ou construction du conteneur ligne 104
- Test: `tests/test_dp_coverage_panel.py`

**Interfaces:**
- Consumes: `_coverage_rows(courses, counts) -> list[dict]` et `render(container: ui.element) -> None`, déjà définis dans le module. Leurs signatures ne changent pas.
- Produces: aucun symbole nouveau.

- [ ] **Step 1: Reproduire et diagnostiquer dans le navigateur**

Ouvrir la prévisualisation (configuration `synapse`), aller sur `/settings`, déplier « DIAGNOSTICS ET TÉLÉMÉTRIE » puis « COUVERTURE DP PAR ITEM », filtre collège sur « Tous » (367 items).

Exécuter dans la page :

```js
(() => {
  const el = document.querySelector('.dpc-scroll');
  if (!el) return { found: false };
  const cs = getComputedStyle(el);
  return {
    found: true,
    maxHeight: cs.maxHeight,
    overflowY: cs.overflowY,
    clientHeight: el.clientHeight,
    scrollHeight: el.scrollHeight,
    parentDisplay: getComputedStyle(el.parentElement).display,
    styleTagPresent: [...document.querySelectorAll('style')].some(s => s.textContent.includes('.dpc-scroll')),
  };
})()
```

Lecture du résultat :

- `styleTagPresent: false` ou `found: true` avec `maxHeight: "none"` → hypothèse 1, la feuille de style n'est pas dans le document.
- `maxHeight: "520px"` mais `clientHeight` proche de `scrollHeight` → hypothèse 2, la contrainte est écrasée par la chaîne de parents.

Consigner le résultat obtenu : il justifie le correctif de l'étape 3.

- [ ] **Step 2: Écrire le test qui échoue**

Ajouter à `tests/test_dp_coverage_panel.py`, avec `from pathlib import Path` en tête de fichier :

```python
def test_styles_are_injected_once_at_import_time():
    """La feuille doit être posée à l'import, pas pendant la construction de la page."""
    source = Path("frontend/components/dp_coverage_panel.py").read_text(encoding="utf-8")

    assert "def ensure_styles() -> None:" in source
    render_body = source[source.index("def render("):]
    assert "ui.add_head_html" not in render_body
    assert "ensure_styles()" in render_body


def test_scroll_container_declares_a_fixed_height_and_visible_scrollbar():
    """Le tableau doit défiler dans son propre cadre, pas entraîner la page."""
    source = Path("frontend/components/dp_coverage_panel.py").read_text(encoding="utf-8")

    assert "max-height:520px" in source
    assert "overflow-y:scroll" in source
    assert "flex:0 0 auto" in source
    # Le cadre interne ne doit pas masquer le débordement du conteneur qui défile.
    assert ".dpc-table { border:1px solid var(--border); border-radius:8px; overflow:hidden;" not in source
```

- [ ] **Step 3: Écrire le correctif**

Les deux hypothèses reçoivent leur correctif : elles ne s'excluent pas, et durcir l'une n'a pas d'effet de bord sur l'autre. Le diagnostic de l'étape 1 sert à savoir laquelle était en cause, information consignée à la tâche 6.

*Injection de la feuille de style.* Sur le modèle de `frontend/components/responsive_drawer.py:26`, remplacer l'appel `ui.add_head_html` de la ligne 95 par une fonction dédiée, définie après le bloc `_CSS` :

```python
_injected = {"done": False}


def ensure_styles() -> None:
    """Injecte le CSS du panneau une seule fois par processus."""
    if _injected["done"]:
        return
    ui.add_head_html(f"<style>{_CSS}</style>", shared=True)
    _injected["done"] = True
```

Dans `render`, remplacer la ligne `ui.add_head_html(f"<style>{_CSS}</style>", shared=True)` par `ensure_styles()`.

*Contrainte de hauteur.* Dans le bloc `_CSS`, remplacer les règles `.dpc-table` et `.dpc-scroll` par :

```css
.dpc-table { border:1px solid var(--border); border-radius:8px; min-width:0; }
.dpc-scroll { max-height:520px; overflow-y:scroll; overflow-x:hidden; min-width:0; flex:0 0 auto;
  scrollbar-gutter:stable; scrollbar-width:thin; scrollbar-color:var(--border-strong) var(--bg-alt);
  overscroll-behavior:contain; }
```

`flex:0 0 auto` est l'ajout décisif : sans lui, la zone de défilement est un élément flex étirable dont le parent peut annuler la contrainte de hauteur. `max-height` est conservé plutôt qu'une hauteur ferme, pour qu'une liste courte — filtre « Seulement sans DP » sur un collège restreint — n'affiche pas un grand cadre vide. Retirer `overflow:hidden` de `.dpc-table` évite que le cadre interne rogne ses propres lignes.

- [ ] **Step 4: Lancer les tests et vérifier qu'ils passent**

```bash
python -m pytest tests/test_dp_coverage_panel.py -v
```

Attendu : tout passe.

- [ ] **Step 5: Vérifier dans le navigateur**

Recharger `/settings`, rouvrir le panneau, filtre « Tous ». Relancer le script de l'étape 1 et vérifier que `clientHeight` vaut environ 520 et reste nettement inférieur à `scrollHeight`. Contrôler visuellement qu'une barre de défilement apparaît dans le panneau et que la molette fait défiler le tableau, pas la page.

Vérifier ensuite le cas d'une liste courte : cocher « Seulement sans DP » sur un collège restreint. Le cadre doit se refermer sur ses quelques lignes sans laisser de vide, `clientHeight` devenant égal à `scrollHeight`.

- [ ] **Step 6: Commit**

```bash
git add tests/test_dp_coverage_panel.py frontend/components/dp_coverage_panel.py
git commit -m "fix: retablir le defilement du panneau couverture dp"
```

---

### Task 6: Recette finale du lot

Les cinq correctifs touchent trois surfaces différentes. Cette tâche vérifie qu'ils cohabitent, et en particulier que la persistance du thème (tâche 1) n'a pas d'effet de bord sur les styles convertis (tâche 2).

**Files:**
- Aucune modification de code attendue. Si un défaut apparaît, il est corrigé ici et le commit est rattaché à cette tâche.

**Interfaces:**
- Consumes: les livrables des tâches 1 à 5.
- Produces: aucun.

- [ ] **Step 1: Lancer la suite de tests complète**

```bash
python -m pytest tests/ -q
```

Attendu : aucun nouvel échec par rapport à l'état de départ de la branche. Le dépôt comporte des échecs préexistants dans deux modules dépréciés (erreurs de collecte identifiées lors de l'audit du 3 août) : les relever et vérifier qu'ils sont inchangés, sans chercher à les corriger dans ce lot.

- [ ] **Step 2: Recette manuelle des cinq correctifs**

Ouvrir la prévisualisation (configuration `synapse`) et vérifier dans l'ordre :

1. **Mode sombre** — basculer en sombre depuis `/settings`, naviguer vers `/items` puis revenir, arrêter et relancer l'application : le thème sombre est toujours actif.
2. **Télémétrie** — les deux expansions de « DIAGNOSTICS ET TÉLÉMÉTRIE » ont le même fond et la même bordure, en thème clair comme en thème sombre ; tous les textes du panneau sont lisibles.
3. **Couverture DP** — barre de défilement présente dans le panneau, la page ne défile pas.
4. **Récents** — au plus trois entrées dans la sidebar après avoir ouvert cinq fiches différentes.
5. **Tuteur DP** — reprendre un Tuteur DP existant et le terminer : la correction s'ouvre immédiatement.

- [ ] **Step 3: Capturer la preuve visuelle**

Prendre une capture d'écran de `/settings`, section « DIAGNOSTICS ET TÉLÉMÉTRIE » dépliée, en thème sombre puis en thème clair. Les joindre au compte rendu.

- [ ] **Step 4: Consigner le résultat**

Créer `docs/RECETTE_LOT1_2026-08-10.md` avec, pour chacun des cinq correctifs : le symptôme d'origine, la cause identifiée, le correctif appliqué, et le résultat observé en recette. Mentionner explicitement l'hypothèse retenue pour B3 à l'issue du diagnostic.

- [ ] **Step 5: Commit**

```bash
git add docs/RECETTE_LOT1_2026-08-10.md
git commit -m "docs: consigner la recette du lot 1"
```
