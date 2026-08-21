# Chantier B2 — Les deux wizards

**Date** : 2026-08-07
**Statut** : design validé, prêt pour plan d'implémentation

## Contexte

Suite du chantier B1 (densité & tokens, terminé — 7 commits, 1125 tests). Voir
[docs/UI_REFONTE_ETAT_DES_LIEUX.md](../../UI_REFONTE_ETAT_DES_LIEUX.md) pour la vue d'ensemble.

B1 a corrigé les pages-liste (largeur, fond de carte, résidus Tailwind). B2 s'attaque aux deux
seuls composants explicitement signalés comme des « wizards » ratés : le dialogue mnémo/image et
le dialogue de validation de séance. Contrairement à B1, aucun de ces deux fichiers n'a jamais été
retokenisé — ce sont des survivances de l'interface Tailwind d'avant la refonte Linear.

## Objectif

Rendre les deux wizards conformes au design system (réactifs au thème, zéro emoji, palette de
couleurs limitée à l'accent + rouge/ambre/vert sémantique), sans changer leur structure ni leur
comportement de soumission.

## Règle de conversion des couleurs (appliquée aux deux wizards)

Le design system n'autorise que deux registres de couleur :
- **Sélection sans signification propre** (l'utilisateur a coché cette option parmi d'autres
  équivalentes) → `color=primary` quand actif, style neutre (`_chip_off()`/gris) sinon. `primary`
  hérite de l'accent réellement configuré (`ui.colors(primary="#5e6ad2", ...)` dans
  `cockpit_shell.py`) — contrairement à un nom Quasar arbitraire (`indigo`, `violet`, `teal`…) qui
  ne correspond pas forcément à cet accent et n'a de toute façon aucune raison sémantique d'être
  différent d'une option à l'autre.
- **Sémantique réelle** (urgence, santé, résultat) → `positive`/`warning`/`negative`, jamais
  d'autre couleur. Quand un groupe de puces encode déjà correctement cette sémantique, il n'est
  **pas** touché.

Décision utilisateur explicite : la confiance (1 à 5) n'est **pas** traitée comme un dégradé
sémantique rouge→vert malgré la tentation (elle ressemble à un signal de santé) — elle reçoit le
traitement neutre, pour ne garder aucune exception à la règle.

## Périmètre

### 1. Wizard mnémo/image — `frontend/components/obsidian_quick_edit_dialog.py`

**État actuel (94 lignes).** Toute la modale est câblée en Tailwind brut et **toujours sombre**,
indépendamment du thème choisi par l'utilisateur :

| Ligne | Défaut |
|---|---|
| 25 | `ui.card().classes("w-full max-w-lg p-6 bg-slate-900 text-white rounded-xl shadow-2xl border border-slate-700")` — fond, texte et bordure figés en sombre |
| 26 | `f"💡 Ajouter à Obsidian — Item {...}"` — emoji dans le titre |
| 31 | `options={"mnemo": "💡 Moyen Mnémotechnique / À savoir", "piege": "⚠️ Piège EDN / Zéro au dossier"}` — emojis dans les libellés du sélecteur |
| 33 | `.props("inline color=indigo")` — couleur Quasar arbitraire |
| 39 | `.props("outlined dark rows=3")` — `dark` forcé sur le textarea, indépendant du thème réel |
| 57 | `ui.label("📷 Image / Schéma (optionnel)")` — emoji |
| 62 | `.props("accept='image/*' flat bordered dark")` — `dark` forcé sur l'upload |

**Décision.**
- Ligne 25 : `background:var(--bg); color:var(--text); border:1px solid var(--border);
  border-radius:var(--radius-lg); box-shadow:var(--shadow-popover);` via `.style(...)`, classes
  Tailwind de structure (`w-full max-w-lg p-6`) conservées.
- Ligne 26 : retrait de l'emoji, titre `f"Ajouter à Obsidian — Item {...}"`.
- Ligne 31 : retrait des emojis des deux libellés (`"Moyen Mnémotechnique / À savoir"`,
  `"Piège EDN / Zéro au dossier"`). Une icône Quasar par option (`lightbulb`, `warning`) peut être
  ajoutée via un `ui.row` icône+label si le composant `ui.radio` de NiceGUI le permet simplement ;
  sinon les libellés textuels seuls suffisent — pas d'obligation d'icône, seule l'absence d'emoji
  est requise par le design system.
- Ligne 33 : `color=indigo` → `color=primary`.
- Ligne 39 : `.props("outlined dark rows=3")` → `.props("outlined rows=3")`.
- Ligne 57 : retrait de l'emoji, `ui.label("Image / Schéma (optionnel)")`.
- Ligne 62 : `.props("accept='image/*' flat bordered dark")` → `.props("accept='image/*' flat bordered")`.
- Les classes de texte Tailwind restantes (`text-indigo-400`, `text-slate-400`, `text-slate-200`)
  passent aux tokens équivalents (`color:var(--accent)`, `color:var(--text-muted)`,
  `color:var(--text)`) via `.style(...)`.

**Hors périmètre.** Aucun changement de structure (mêmes champs, même logique de soumission dans
`submit()`), aucun changement du service `obsidian_service.append_mnemonic_or_image`.

### 2. Wizard de validation de séance — `frontend/pages/dashboard/_dialogs.py::open_session_feedback_dialog`

**État actuel (lignes 210-539, la plus grande modale du dépôt).**

**Centrage.** Ligne 245 : la carte porte `self-end mr-0` — elle est ancrée en bas-droite de
l'écran au lieu d'être centrée comme toutes les autres modales du cockpit. C'est la cause exacte
du symptôme « pas centrée ».

**Couleurs décoratives.** Six groupes de puces, dont quatre utilisent des couleurs sans rapport
avec une sémantique réelle :

| Groupe | Config / appel | Couleurs actuelles | Traitement |
|---|---|---|---|
| Activité (7 options, ligne 231) | `_chip_on("indigo")` appelé en dur (construction de la puce, bascule on, bascule off) | `indigo` | → `_chip_on("primary")` partout où « indigo » apparaît pour ce groupe |
| Durée (7 présets + custom, ligne 233) | idem, `_chip_on("indigo")` appelé en dur | `indigo` | → `_chip_on("primary")` |
| Confiance (5 niveaux, `_CONF_CONFIG` ligne 358) | couleur par tuple | rouge/orange/bleu/sarcelle/vert | → `"primary"` pour les 5 (décision utilisateur : traitement neutre, pas de dégradé) |
| Difficulté (`DIFF_OPTS` ligne 234) | couleur par tuple | `positive`/`warning`/`negative` | **inchangé** — sémantique correcte |
| Résultat QCM (`QCM_OPTS` ligne 235) | couleur par tuple | `grey`/`positive`/`warning`/`negative` | **inchangé** — sémantique correcte |
| Catégorie d'erreur/piège (`_ERR_CATS` ligne 442) | couleur par tuple | `grey`/rouge/orange/orange foncé/bleu/violet/indigo/rose/sarcelle/gris-bleu | → `"primary"` pour les 9 catégories réelles ; le `grey` du premier tuple (`None`, `"—"`) reste inchangé — c'est l'option « aucune catégorie », pas une catégorie décorative |

**Vérification de complétude — attention à la portée.** La chaîne littérale `"indigo"` apparaît
**huit fois** dans le fichier aux lignes 305, 311, 314, 328, 341, 343, 352 (Activité et Durée,
y compris le gestionnaire de durée personnalisée) et 449 (`_ERR_CATS`, catégorie
« physiopathologie ») — toutes à l'intérieur du corps de `open_session_feedback_dialog` (lignes
210-539), donc toutes à convertir en `"primary"`. **Une neuvième occurrence existe ligne 56**, mais
dans `open_sr_help_dialog` (l'autre wizard du même fichier, explicitement hors périmètre — voir
plus bas) : un remplacement global sur tout le fichier la toucherait par erreur. Le remplacement
doit être scopé au corps de `open_session_feedback_dialog`, jamais fait sur le fichier entier.

**Tokens de couleur générale.** Tous les `bg-white dark:bg-slate-900`, `text-slate-900
dark:text-slate-50`, `text-slate-500`, `border-slate-100 dark:border-slate-800`,
`bg-slate-50 dark:bg-slate-800/50` du composant (en-tête, corps, pied sticky) passent aux tokens
équivalents.

**Décision — carte.** Ligne 244-248, remplacer :
```python
        with ui.card().classes(
            "w-[520px] max-w-[calc(100vw-24px)] max-h-[calc(100vh-24px)] self-end mr-0 "
            "flex flex-col rounded-none sm:rounded-lg p-0 overflow-hidden bg-white "
            "dark:bg-slate-900 border border-slate-200 dark:border-slate-800 shadow-xl"
        ):
```
par une carte centrée, tokens, sans le comportement « coin bas-droite » ni le carré forcé sur
mobile (`rounded-none sm:rounded-lg` devient `rounded-lg` partout — cohérent avec le plafond de
rayon 8px du design system, aucune raison de le supprimer sur mobile) :
```python
        with ui.card().classes(
            "w-[520px] max-w-[calc(100vw-24px)] max-h-[calc(100vh-24px)] "
            "flex flex-col rounded-lg p-0 overflow-hidden"
        ).style(
            "background:var(--bg); border:1px solid var(--border); box-shadow:var(--shadow-popover);"
        ):
```

**Hors périmètre.** Aucun changement de structure (mêmes sections Activité/Durée/Confiance/
Difficulté/Détails avancés/Situer l'item), aucun changement de `submit_session_feedback` ni de
`default_feedback_state` (`session_feedback.py`, `session_feedback_ui.py` — logique pure, non
touchée). Les trois autres dialogues du même fichier (`open_sr_help_dialog`, `show_bilan_session`,
`open_lacune_inline_dialog`) ont des défauts similaires (Tailwind brut, emojis 🎉🔁) mais n'ont pas
été signalés par l'utilisateur — non touchés, pour ne pas élargir la demande.

## Risques

- **Wizard de validation de séance** : fichier de 330 lignes avec beaucoup de couleurs répétées
  sur des tuples de configuration (`_CONF_CONFIG`, `_ERR_CATS`) — risque d'en oublier une en
  cours de remplacement. Un test de source vérifiant l'absence de chaque couleur Quasar
  arbitraire (`indigo`, `red`, `orange`, `blue`, `teal`, `violet`, `pink`, `deep-orange`,
  `blue-grey`) dans la fonction couvre ce risque.
- **Retrait de `self-end mr-0`** : c'est un changement de comportement visible immédiatement à
  chaque validation de séance (le geste le plus fréquent de l'app) — à vérifier visuellement
  avant de considérer la tâche terminée.
- Aucun risque fonctionnel : les deux wizards gardent leurs champs, leur validation et leurs
  callbacks inchangés.

## Tests

- Test de présence des tokens (absence de `bg-slate-900`, `text-white` en dur, `dark` forcé sur
  les props) dans `obsidian_quick_edit_dialog.py`.
- Test d'absence d'emoji dans les libellés de `obsidian_quick_edit_dialog.py`.
- Test d'absence de `self-end` dans `open_session_feedback_dialog`.
- Test d'absence de chaque couleur Quasar arbitraire remplacée, et de présence de `color=primary`
  à leur place, dans `open_session_feedback_dialog`.
- Test confirmant que `DIFF_OPTS` et `QCM_OPTS` gardent `positive`/`warning`/`negative` (non-
  régression — s'assurer qu'un remplacement trop large ne les touche pas par erreur).
- Suite complète (`pytest -q`) avant/après pour confirmer l'absence de régression.
