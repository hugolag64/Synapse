# Design — Correction automatique d'annales UNESS via Gemini API

## Contexte et objectif

Aujourd'hui, corriger une annale UNESS demande de copier-coller manuellement un JSON
"bridge" (HTML brut + prompt) dans ChatGPT ou Gemini web, récupérer la réponse, la
sauvegarder dans `UNESS/vérifiés/`, puis cliquer "Scanner les JSON existants".

Objectif : remplacer l'étape manuelle par un appel direct à l'API Gemini (modèle
`gemini-3-flash-preview`, déjà configuré dans `.env` via `GEMINI_FLASH_MODEL`),
déclenché depuis un bouton dans la modale "Importer une annale UNESS", en pointant
vers le dossier du partiel à corriger.

Décisions validées avec l'utilisateur avant ce design :
- Modèle : `gemini-3-flash-preview` (config existante, `AIModel.FLASH`). Pas de
  changement de modèle ni de nouveau réglage dédié.
- Un clic corrige **tout le dossier** collé (potentiellement plusieurs sous-parties
  d'un même partiel : mDP1, mDP2, KFP...), pas un fichier à la fois.
- Les images collectées sont **dupliquées** dans le dossier des JSON bridges (en plus
  de la copie de staging existante, qui reste inchangée) — un seul dossier à
  utiliser pour le flux manuel (glisser dans ChatGPT/Gemini web) comme pour le flux
  API, sans risque d'oubli.

## Simulation de coût (référence, tarif Google au 2026-07-31)

| | Input / M tokens | Output / M tokens |
|---|---|---|
| Gemini 3 Flash Preview | 0,25 $ | 1,50 $ |

- Par sous-partie (15k-25k tokens in, 2k-4k tokens out) : ≈ 0,007 $ à 0,012 $
- Par partiel complet (5 à 7 sous-parties) : ≈ 0,035 $ à 0,085 $
- Pour 100 partiels complets : ≈ 3,5 $ à 8,5 $

Un free tier existe aussi pour ce modèle preview (quota plus restreint que Gemini
2.5 Flash), donc un usage ponctuel (quelques annales de test) peut ne rien coûter.

## Architecture

Un seul nouveau module orchestre l'appel API ; **rien dans la logique de
fusion/validation existante ne change** (`gemini_conversion.py`, `import_service.py`
restent intacts). Le nouveau module se contente de produire, à la place d'un
copier-coller humain, exactement le même type de fichier JSON brut dans
`UNESS/vérifiés/` — le pipeline existant (scan → conversion → validation → import →
archivage) le traite ensuite sans savoir qu'il vient d'une IA ou d'un humain.

```
[Dossier UNESS/à_vérifier/session-<stamp>/]
        │  (JSON bridges + images dupliquées)
        ▼
backend/core/uness/gemini_autocorrect.py   ← NOUVEAU
        │  1 appel Gemini par quiz du dossier
        ▼
UNESS/vérifiés/<slug>.json  (réponse IA brute, format inchangé)
        │
        ▼
import_verified_directory()   ← EXISTANT, inchangé
        │
        ▼
Session de practice importée + archivage
```

## Composants

### 1. `backend/core/uness/gemini_autocorrect.py` (nouveau)

```python
def correct_directory(folder: Path) -> dict:
    # -> {"corrected": [...], "errors": [...], "input_tokens": int, "output_tokens": int}
```

- Liste les `*.json` du dossier qui ressemblent à un bridge (dict avec clé
  `"contents"` — même critère que `find_bridge_for_title` dans
  `gemini_conversion.py`).
- Pour chaque quiz dans `bridge["contents"]` :
  - Texte envoyé à Gemini = `bridge.get("prompt")` (fallback
    `prompts/uness_correction_prompt.txt`) + le JSON `{title, html}` de ce quiz.
  - Images : pour chaque `images[].filename` du quiz, cherche le fichier par **nom
    de base** directement dans `folder` (puisque les images y sont désormais
    dupliquées) ; si absent, log un avertissement et continue sans cette image (le
    prompt gère déjà ce cas : `accessible_ia=false` / question `unsupported`).
  - Appelle `GeminiClient().generate(text, AIModel.FLASH, response_format="json",
    images=[...])`.
  - Parse la réponse (`json.loads`), écrit le JSON brut tel quel dans
    `UNESS/vérifiés/<slug>-<stamp>.json`.
  - Cumule `input_tokens`/`output_tokens` (déjà renvoyés par `AIResponse`).
- Toute erreur (réseau, JSON invalide, image manquante) est capturée **par quiz**,
  ajoutée à `errors`, sans interrompre le reste du dossier — même tolérance que
  `import_verified_directory`.

### 2. `scripts/uness/collector.py` (modifié)

Après la collecte, en plus de la copie existante vers
`UNESS/images/session-<stamp>/<stamp>/` (**inchangée**, c'est elle que
`import_service._cleanup_staged_images` nettoie après import), ajoute une
**duplication** des mêmes images directement dans `review_dir`
(= `UNESS/à_vérifier/session-<stamp>/`, là où sont déjà les JSON bridges). Un seul
dossier à coller/glisser désormais, que ce soit pour le flux manuel (ChatGPT/Gemini
web) ou pour le nouveau bouton API.

### 3. `frontend/pages/annales.py` (modifié)

Dans `_open_import_dialog`, sous l'input URL existant, ajout d'une section :
- `ui.separator()` + label "Ou corriger un dossier existant avec Gemini"
- `folder_input = ui.input(label="Dossier du partiel (JSON + images)",
  placeholder="UNESS/à_vérifier/session-...")`
- Bouton **"Corriger avec Gemini"** (icône `auto_awesome`)

Handler `_run_gemini_autocorrect()` (async) :
- Désactive le bouton, affiche "Correction Gemini en cours…"
- `result = await asyncio.to_thread(correct_directory, Path(folder_input.value))`
  (appel réseau synchrone, donc exécuté dans un thread pour ne pas bloquer la boucle
  d'événements NiceGUI)
- Affiche un résumé : `"{n} quiz corrigés, {e} erreur — ~{tokens_in} tokens entrée /
  {tokens_out} sortie (≈ {cout_estime}$)"` (coût estimé via les tarifs Gemini 3 Flash
  Preview en constante dans le module : 0,25 $/M in, 1,50 $/M out — commentée comme
  "tarif Google au 2026-07-31, à revérifier périodiquement")
- Si au moins une correction a réussi, enchaîne automatiquement sur
  `_finalize_scan()` (exactement le même appel que le bouton "Scanner les JSON
  existants") pour valider/importer.

## Gestion des erreurs

- Dossier vide ou introuvable → message clair, aucun appel Gemini.
- Erreur Gemini sur un quiz → n'empêche pas les autres quiz du dossier ; remontée
  dans `errors` et affichée à l'utilisateur.
- Réponse Gemini mal formée (JSON invalide) → erreur par quiz, rien n'est écrit dans
  `vérifiés/` pour ce quiz.
- La validation stricte existante (`assert_verified_exam` dans `import_service.py`)
  s'applique ensuite sans changement : une correction IA incomplète ou incohérente
  est rejetée exactement comme si elle avait été collée manuellement.

## Tests

- `tests/test_gemini_autocorrect.py` (nouveau) : `GeminiClient.generate` mocké
  (aucun appel réseau réel) — cas nominal 1 quiz, dossier multi-quiz, image
  manquante, réponse JSON invalide, erreur API sur un quiz parmi plusieurs.
- `tests/test_uness_collector.py` : ajout d'une assertion que les images sont bien
  dupliquées dans le dossier `à_vérifier/session-*` en plus du staging existant.
- Aucun changement dans `test_gemini_conversion.py` / les tests d'import : la
  logique qu'ils couvrent n'est pas touchée.

## Hors périmètre (v1)

- Pas de nouvelle dépendance (réutilise `GeminiClient` existant).
- Pas de parallélisation des appels Gemini (séquentiel, plus simple à déboguer et à
  borner en erreurs/coût).
- Pas de champ de configuration supplémentaire (clé API et modèle déjà dans `.env`).
- Pas de changement au format canonique `UnessExam` ni aux règles de validation.
