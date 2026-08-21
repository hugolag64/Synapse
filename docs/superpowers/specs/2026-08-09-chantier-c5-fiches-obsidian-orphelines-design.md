# Chantier C5 — Fiches Obsidian orphelines (numéro d'item manquant)

**Date** : 2026-08-09
**Statut** : design validé, prêt pour plan d'implémentation

## Contexte

Cinquième et dernier sous-chantier de C (fond pédagogique), suite de C1-C4, tous terminés. Demande
initiale (section 5) : « fiches Obsidian sans numéro d'item, donc sans rétrolien ».

**Scénario confirmé par l'utilisateur** : ce sont des fiches créées normalement par Synapse (liées à
un cours Notion, `notion_id` présent en frontmatter), pas des notes manuelles jamais rattachées.

**Cause racine identifiée.** `Course.display_item_number`
(`backend/core/notion/models.py:192-202`) lit **uniquement** `item_number` — jamais `item_lie`, par
choix explicite (« jamais item_lie (UUID Notion) » en commentaire). `templates.py:91` écrit
`"item": getattr(course, "display_item_number", "") or ""` dans le frontmatter à la création de la
fiche. Un audit antérieur (mémoire `project_college_item_authority`) documente déjà ce problème de
données : certaines lignes de la base Cours Notion ont leur propriété `ITEM (number)` vide alors que
`ITEM lié` (relation) est renseignée — confirmé était vrai au moins pour le collège Endocrinologie.
Toute fiche créée depuis un tel cours naît donc orpheline dès sa création.

**Deux volets nécessaires, pas un seul.** Corriger uniquement Notion ne répare pas les fiches déjà
créées : `_push_missing_obsidian_uris()` (`backend/core/background.py:256-329`), le seul mécanisme
de sync qui touche des notes déjà liées (`notion_id` présent), ne gère que le champ `Obsidian` (URI)
— il ne relit ni ne réécrit jamais le champ `item`. `VaultSyncService`
(`backend/core/obsidian/sync.py`) ne s'applique pas non plus : il ignore explicitement les notes
déjà liées (« Ne modifie pas une note déjà liée »).

**Pattern déjà établi à réutiliser.** `scripts/reconcile_colleges.py:58-81` et
`scripts/apply_college_corrections.py:78-95` résolvent déjà exactement ce cas (`item_number` vide →
repli sur `item_lie` via `get_all_items_map()` inversée) pour leurs propres besoins de diagnostic.
`apply_college_corrections.py` établit aussi la convention dry-run / `--apply` avec export JSON du
plan, à reproduire ici.

## Objectif

Les cours Notion sans `ITEM (number)` mais avec `ITEM lié` résolvable sont corrigés à la source, et
les fiches Obsidian déjà créées à partir d'eux retrouvent un `item:` correct dans leur frontmatter —
sans toucher au corps ni aux autres champs.

## Périmètre

### Script 1 — `scripts/reconcile_item_numbers.py`

Diagnostic + correction Notion, dry-run par défaut, `--apply` pour écrire réellement (même
convention que `apply_college_corrections.py:70-71`).

```python
cours_existants = await notion_service.get_all_cours()
items_map = await notion_service.get_all_items_map()          # item_number(int) -> page_id
page_id_to_item_num = {v: k for k, v in items_map.items()}    # page_id -> item_number(int)

corrections = []
for c in cours_existants:
    has_number = bool((c.item_number or "").strip())
    if has_number or not c.item_lie:
        continue
    resolved = page_id_to_item_num.get(c.item_lie)
    if resolved is not None:
        corrections.append({"page_id": c.id, "title": c.title, "item_number": resolved})
```

Dry-run : affiche le compte de corrections, exporte `data/item_number_reconcile_report.json` avec
le détail (`page_id`, `title`, `item_number` résolu). `--apply` : pour chaque correction,
`await notion_service.update_course(page_id, {P.ITEM: {"number": float(item_number)}})`, avec le
même délai `0.35s` entre appels que les scripts existants (limite de débit Notion), résultat exporté
dans `data/item_number_apply_result.json` (comptes créés/erreurs, même structure que
`apply_college_corrections.py:151-159`).

**Rien d'autre n'est modifié** sur les pages Cours corrigées : ni `Collège`, ni titre, ni aucune
autre propriété — seule `ITEM (number)` reçoit la valeur résolue.

### Script 2 — `scripts/heal_obsidian_item_frontmatter.py`

À exécuter **après** le script 1 en mode `--apply` (dépend des données Notion corrigées). Dry-run
par défaut, `--apply` pour écrire réellement dans le vault local.

```python
cours_existants = await notion_service.get_all_cours()   # relu après correction Notion
course_map = {c.id: c for c in cours_existants}

vault = Path(settings.obsidian_vault_path)
candidates = []
for md_path in vault.glob("01 - Cours EDN/*/Cours/*.md"):
    text = md_path.read_text(encoding="utf-8")
    fm_raw, body = _split_frontmatter(text)
    if not fm_raw:
        continue
    fields = _parse_fm_lines(fm_raw)
    fm = dict(fields)
    notion_id = str(fm.get("notion_id", "") or "").strip()
    current_item = str(fm.get("item", "") or "").strip()
    if current_item or not notion_id or notion_id not in course_map:
        continue
    resolved = course_map[notion_id].display_item_number
    if resolved:
        candidates.append({"path": md_path, "fields": fields, "body": body, "item": resolved})
```

Dry-run : liste les fiches candidates (chemin + numéro qui serait écrit), exporte
`data/obsidian_item_heal_report.json`. `--apply` : pour chaque candidate,
`new_fm = _rebuild_fm(fields, {"item": item})` puis réécrit `new_fm + body` dans le fichier —
réutilise les helpers déjà existants (`backend/core/obsidian/templates.py:101-205`), donc corps et
tout autre champ du frontmatter restent identiques par construction (`_rebuild_fm` préserve l'ordre
et ne touche que la clé passée en override).

## Hors périmètre

- `Course.display_item_number` n'est pas modifié — reste « jamais item_lie », c'est une correction de
  données à la source, pas un changement de comportement applicatif. Une fois les deux scripts
  passés, `display_item_number` retourne déjà la bonne valeur sans aucun changement de code.
- Pas de bouton Settings permanent — décision utilisateur, scripts ponctuels comme pour les collèges.
- Aucune modification des notes de type Lacune (`08 - Lacunes/...`), seules les notes de cours
  (`01 - Cours EDN/*/Cours/*.md`) sont concernées — les lacunes ne portent pas de frontmatter `item`
  dans le même sens (à vérifier si un problème analogue existe, mais hors périmètre du signalement
  initial de l'utilisateur).
- Aucun changement à `VaultSyncService` (notes jamais liées à Synapse) — hors du scénario confirmé.

## Risques

- **Ordre d'exécution strict.** Le script 2 lit les données Notion *après* correction — s'il tourne
  avant le script 1 (ou avant que le script 1 ait été passé en `--apply`, pas seulement en dry-run),
  aucune fiche ne sera candidate puisque `display_item_number` sera encore vide côté Notion. Documenté
  explicitement dans le docstring des deux scripts et dans le plan d'implémentation.
- **Vault non configuré.** Si `settings.obsidian_vault_path` est vide (comme déjà géré par
  `_push_missing_obsidian_uris:275-277`), le script 2 doit s'arrêter proprement avec un message clair
  plutôt que planter sur un `Path` invalide.
- **Cours avec `item_lie` pointant vers une page Item introuvable** (page supprimée/déplacée) : le
  script 1 les laisse simplement de côté (`resolved is None` → pas de correction proposée), aucune
  erreur ne doit être levée pour ce cas attendu.

## Tests

- Test unitaire pour la fonction de résolution du script 1 (extraite en fonction testable, ex.
  `find_item_number_corrections(cours, page_id_to_item_num)`) : un cours avec `item_number` vide et
  `item_lie` résolvable produit une correction ; un cours avec `item_number` déjà rempli n'en produit
  aucune même si `item_lie` est présent ; un cours sans `item_lie` du tout n'en produit aucune ; un
  cours avec `item_lie` ne correspondant à aucune page Item connue n'en produit aucune (pas
  d'exception).
- Test unitaire pour la fonction de détection du script 2 (ex.
  `find_frontmatter_heal_candidates(md_paths, course_map)`, avec un vault de test dans `tmp_path`) :
  une fiche avec `notion_id` connu, `item:` vide, et `display_item_number` désormais résolu devient
  candidate ; une fiche avec `item:` déjà rempli n'est pas candidate ; une fiche sans `notion_id` ou
  avec un `notion_id` inconnu n'est pas candidate ; après application, le corps du fichier et les
  autres champs du frontmatter sont strictement identiques à l'original (seule la ligne `item:`
  change).
- Suite complète (`./.venv/Scripts/python.exe -m pytest -q`) avant la première tâche et après la
  dernière.
