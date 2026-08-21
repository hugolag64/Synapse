# Chantier B4 — Déplacement structurel du Tuteur DP

**Date** : 2026-08-07
**Statut** : design validé, prêt pour plan d'implémentation

## Contexte

Dernier sous-chantier de B (suite de A, B1, B2, B3, tous terminés — voir
[docs/UI_REFONTE_ETAT_DES_LIEUX.md](../../UI_REFONTE_ETAT_DES_LIEUX.md)). Le bloc « Tuteur DP » est
actuellement rendu en dur dans l'onglet Historique (`_tab_history`,
`frontend/pages/course_detail_cockpit.py:1023-1145`), alors que c'est de l'entraînement actif — il
appartient à l'onglet QCM (`_tab_qcm`, même fichier, lignes 884-949), à côté de la Série QCM
adaptative.

## Objectif

Déplacer le bloc Tuteur DP de l'onglet Historique vers l'onglet QCM, sans changer son comportement
fonctionnel, et harmoniser sa couleur décorative indigo vers le token `primary`/`--accent` du design
system — même règle que le chantier B2.

## Périmètre

### 1. Extraction en fonction dédiée — `frontend/pages/course_detail_cockpit.py`

Le bloc actuellement inline dans `_tab_history` (lignes 1107-1142 : calcul de `item_number`,
récupération de `dp_history` via `local_store.get_ai_practice_history`, construction de `errors` et
`gap_details` à partir de `lacunes`, puis rendu de la liste des 5 dernières sessions DP ou du bouton
de première ouverture) devient une fonction privée dédiée :

```python
def _render_dp_tutor(course, lacunes) -> None:
    item_number = str(getattr(course, "item_number", "") or getattr(course, "display_item_number", "") or "")
    ai_history = local_store.get_ai_practice_history(item_number=item_number, limit=30) if item_number else []
    dp_history = [entry for entry in ai_history if str(entry["session"].get("practice_kind", "")).lower() == "dp"]
    errors = [
        {"category": _row_get(l, "category") or "non_classe", "detail": _row_get(l, "detail") or ""}
        for l in lacunes
    ]
    gap_details = [str(_row_get(l, "detail") or "") for l in lacunes]
    with ui.column().classes("w-full gap-2 ci-reco"):
        ui.label("TUTEUR DP").classes("ci-reco-meta")
        if dp_history:
            for entry in dp_history[:5]:
                session = entry["session"]
                questions = entry.get("questions", [])
                dossier_context = "\n".join(str(q.get("prompt") or "") for q in questions[:5])
                ui.button(
                    f"Ouvrir le Tuteur DP · Session #{session['id']}",
                    on_click=lambda session=session, dossier_context=dossier_context: render_dp_tutor_action(
                        item_number=item_number,
                        dp_session={**session, "dossier_context": dossier_context, "course_id": course.id, "course_title": course.title},
                        errors=errors,
                        gap_details=gap_details,
                        refresh=lambda: None,
                    ),
                ).props("flat color=primary align=left")
        else:
            ui.button(
                "Ouvrir le Tuteur DP sur cet Item",
                on_click=lambda: render_dp_tutor_action(
                    item_number=item_number,
                    dp_session={"course_id": course.id, "course_title": course.title, "dossier_context": ""},
                    errors=errors,
                    gap_details=gap_details,
                    refresh=lambda: None,
                ),
            ).props("unelevated color=primary")
```

Seuls deux changements par rapport au bloc d'origine : le conteneur passe de
`ui.column().classes("w-full gap-2 mt-5 p-4 rounded-xl border border-indigo-200 dark:border-indigo-900 bg-indigo-50/40 dark:bg-indigo-950/20")`
à `ui.column().classes("w-full gap-2 ci-reco")`, et les deux `color=indigo` deviennent `color=primary`.
Tout le reste (logique de récupération de l'historique, structure des boutons, callbacks) est
identique au bloc actuel.

**Pourquoi `.ci-reco`.** C'est déjà la classe du bloc voisin « Série QCM adaptative »
(`course_detail_cockpit.py:141`, fond `var(--accent-wash)`) — réutiliser la même classe donne aux
deux blocs un habillage visuel cohérent sans introduire de nouvelle règle CSS, et fait disparaître
les deux derniers `color=indigo` (prop Quasar) du fichier restés après B1/B2. La classe Tailwind
`text-indigo-500` du bloc Typologie des erreurs (ligne 1035, hors périmètre) n'est pas concernée —
voir section Hors périmètre.

### 2. Suppression du bloc dans `_tab_history`

Les lignes 1107-1142 de `_tab_history` sont supprimées intégralement. La fonction se termine juste
après la boucle de rendu de la timeline (juste après l'actuel `ui.label(ev["dur"])...` du bloc
`ACTIVITÉ RÉCENTE`). Signature de `_tab_history(course, sessions, qcm_sessions, lacunes,
review_hist)` **inchangée** — `review_hist` et les autres paramètres restent utilisés par le reste
de la fonction (timeline, typologie des erreurs).

### 3. Appel dans `_tab_qcm`

Dans `_tab_qcm(course, qcm_summary, qcm_sessions, lacunes, mastery_score=None)`
(`course_detail_cockpit.py:884-949`), `_render_dp_tutor(course, lacunes)` est appelé juste après le
bloc résumé QCM (« Dernier QCM » / « Moyenne », lignes 897-905) et **avant** le commentaire
`# Série adaptative : dérivée des lacunes récurrentes réelles` (ligne 907).

**Pourquoi avant, pas après.** Le bloc Série adaptative contient un `return` prématuré (ligne 924,
`if not weighted: ... return`) quand l'item n'a aucune lacune récurrente. Si le Tuteur DP était placé
après ce bloc sans modification, il n'apparaîtrait jamais pour ces items — un vrai bug de régression
silencieuse. Le placer avant évite complètement le problème sans toucher à la logique de la Série
adaptative, qui reste hors périmètre de ce chantier.

Aucun nouveau paramètre à faire remonter : `course` et `lacunes` sont déjà des paramètres de
`_tab_qcm`. `render_dp_tutor_action` et `local_store` sont déjà importés en tête de fichier
(ligne 27 et ligne 57).

## Hors périmètre du chantier B4

- Le `return` prématuré du bloc Série adaptative (ligne 924) n'est pas corrigé — seulement contourné
  par l'ordre de placement. Une correction (`if/else` au lieu d'un `return`) resterait à faire
  séparément si un jour un autre bloc doit apparaître *après* la Série adaptative.
- La couleur `text-indigo-500` du bloc « Typologie des erreurs » (`_tab_history`, ligne 1035) n'est
  pas touchée — bloc différent, hors demande utilisateur pour B4.
- Aucun changement à `render_dp_tutor_action`, `PracticeService`, ou tout autre code backend lié au
  Tuteur DP — uniquement le placement et le style du point d'entrée dans le cockpit.
- Aucun changement à la structure des onglets (`t_qcm`, `t_hist`) ni à leur ordre.

## Risques

- **Test existant à mettre à jour.** `tests/test_dp_tutor.py::test_item_history_exposes_tutor_dp_action`
  (lignes 9-15) vérifie littéralement que la chaîne `"_tab_history(course,"` apparaît dans le fichier
  source — ce test encode l'ancien emplacement et doit être mis à jour (voir section Tests) sous
  peine de rester vert pour une mauvaise raison ou de casser sans rapport avec le vrai changement.
- **Portée du remplacement indigo→primary.** La chaîne `"indigo"` apparaît ailleurs dans le fichier
  (ligne 1035, bloc Typologie des erreurs) pour un usage volontairement hors périmètre. Toute
  vérification automatisée de l'absence d'`indigo` doit être scopée au corps de `_render_dp_tutor`
  (via `inspect.getsource(_render_dp_tutor)`), pas un grep global du fichier — même piège que celui
  documenté dans le spec B2.

## Tests

- Mise à jour de `tests/test_dp_tutor.py::test_item_history_exposes_tutor_dp_action` : renommé
  `test_item_qcm_exposes_tutor_dp_action`, l'assertion `"_tab_history(course," in source` devient
  `"_render_dp_tutor(course, lacunes)" in source` (présence de l'appel depuis `_tab_qcm`), l'assertion
  `"render_dp_tutor_action" in source` est conservée.
- Nouveau test : `_render_dp_tutor` n'apparaît plus dans le corps de `_tab_history` (scope via
  `inspect.getsource(_tab_history)`, absence de `"TUTEUR DP"` ou de l'appel à la fonction).
- Nouveau test : le corps de `_render_dp_tutor` (`inspect.getsource`) ne contient aucune occurrence de
  `"color=indigo"` ni de classes `indigo` Tailwind, et contient `"color=primary"` (×2) et `"ci-reco"`.
- Suite complète (`./.venv/Scripts/python.exe -m pytest -q`) avant la première tâche et après la
  dernière, comme pour A/B1/B2/B3.
