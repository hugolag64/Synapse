# UNESS Gériatrie — hardening fix report

Date: 2026-07-30
Base revision: `cb45519`

## Implemented

- Hardened recursive secret URL rejection at model construction, save, import, and pre-prompt boundaries. The detector now catches direct URLs, fragment-routed callbacks such as `#/callback?access_token=...`, HTTP(S) URLs embedded in arbitrary text, relative image URLs with secret parameters, URL user-info, and signed URL parameters such as `X-Amz-Signature` and `X-Goog-Signature`.
- Added an explicit question-level `verification_status` contract: `unverified`, `verified`, or `unsupported`. It round-trips through canonical JSON and imported QCM metadata.
- Changed unavailable or partially unsupported visual verification to an explicit unsupported result. No AI call is made, every AI verdict remains `null`, proposition status remains indeterminate (`incertain`, unless already manually validated), and a non-authoritative explanation records why visual verification was unavailable.
- Rejected `verification_status: unsupported` and other non-verified question states from the verified import path before they can be used as AI corrections.
- Added bounded multimodal admission: at most 4 image parts, at most 10 MiB per image, and at most 20 MiB total per question. Excess images are marked `unsupported`; otherwise admissible images are truthfully relabelled `not_provided_to_ai` when the complete visual set cannot be sent.
- Replaced filename-derived MIME trust with content inspection. PNG structure and CRCs are checked, JPEG structure is checked, and constrained GIF/WebP signatures are recognized. Fake, truncated, mismatched, or otherwise unsupported content is never marked `provided_to_ai`.
- Added a visible React QCM warning for unsupported visual verification: “Vérification IA visuelle indisponible” and “Aucun verdict IA…”.
- Expanded regression coverage for direct, fragment, embedded-text, signed, persistence-boundary, pre-prompt, and image-source secret URLs; unsupported visual state/import/UI; count and total-byte limits; and corrupt image content.

## Verification

### Relevant Python UNESS/QCM/AI suites

```powershell
$testFiles = Get-ChildItem tests -File | Where-Object {
  $_.Name -like 'test_uness*.py' -or
  $_.Name -like 'test_qcm*.py' -or
  $_.Name -like 'test_ai*.py' -or
  $_.Name -eq 'test_gemini_client.py'
} | Select-Object -ExpandProperty FullName
.\.venv\Scripts\python.exe -m pytest @testFiles -q
```

Result: `187 passed in 4.70s`.

### Complete Python suite

```powershell
.\.venv\Scripts\python.exe -m pytest tests -q
```

Result: `829 passed, 1 failed, 1 warning in 26.40s`.

The single failure is outside this hardening scope:
`tests/test_knowledge_mastery.py::test_anki_presence_seule_ne_promeut_pas_le_niveau_de_preparation_edn`
expects `à consolider`, while the current knowledge-mastery code returns `fragile`.
The failure reproduces in isolation and none of the scoped files touch knowledge mastery.

### React tests

```text
npm test -- --run
```

Result: `1` test file passed, `4` tests passed.

### React production build

```text
npm run build
```

Result: success; `16` modules transformed and production assets emitted.

### Ruff

```text
ruff check backend/core/uness/models.py backend/core/uness/ai_verifier.py \
  backend/core/uness/import_service.py tests/test_uness_models.py \
  tests/test_uness_ai_verifier.py tests/test_uness_import.py \
  tests/test_uness_smoke_fixture.py
```

Result: `All checks passed!`

## Scope protection

The worktree contained unrelated user edits and deletions before this task. They were
left untouched. The scoped commit contains only UNESS hardening implementation, its
Python and React regressions, regenerated QCM production assets, and this report.
