# UNESS Gériatrie — visual integrity fix report

Date: 2026-07-30
Base revision: `a181f6c`

## Review blockers resolved

1. **Verified questions now require verified image delivery**
   - `assert_verified_exam()` rejects every attached image whose
     `metadata.verification_status` is not exactly `provided_to_ai`.
   - Regression coverage includes `unsupported`, `not_provided_to_ai`, and a
     missing status on a question otherwise marked `verified`.
   - The verified import fixture now records the required per-image status.

2. **Image validation now uses a real decoder**
   - PNG, JPEG, GIF, and WebP bytes are opened with Pillow, structurally
     verified, and fully decoded (including every frame) before admission.
   - The detected Pillow format must also be in the explicit supported-format
     allowlist.
   - Decoder, syntax, value, and decompression-bomb failures produce
     `unsupported`; corrupt bytes are not included in an AI request.
   - Pillow `10.4.0` is now an explicit project dependency in both dependency
     manifests.
   - Crafted PNG, JPEG, GIF, and WebP payloads that passed the former
     signature/structure checks but cannot be decoded are covered by regression
     tests.

3. **Secret-bearing nested URLs are decoded and traversed safely**
   - Percent-encoding is decoded iteratively until a fixed point, with a
     six-round bound.
   - Embedded HTTP(S) URLs, query strings, fragments, and nested parameter
     values are inspected recursively, with a 64-candidate bound.
   - Inputs that exceed either bound fail closed.
   - Double-encoded token URLs nested in both query and fragment redirect
     values are covered by regression tests.

## Red/green evidence

The new focused regressions produced eleven red cases: four corrupt image
formats were sent to the fake AI service, three invalid or missing per-image
statuses were accepted, and four double-encoded or recursively nested token
URLs were accepted. After the scoped fixes, those cases and the existing UNESS
coverage pass.

## Verification

### Relevant Python tests

```powershell
$unessTests = Get-ChildItem -LiteralPath 'tests' -Filter 'test_uness*.py' |
  ForEach-Object FullName
.\.venv\Scripts\python.exe -m pytest @unessTests -q
```

Result: `98 passed in 2.15s`.

### React tests

```powershell
cd qcm_app
npm test
```

Result: `1` test file passed; `4` tests passed.

### React production build

```powershell
cd qcm_app
npm run build
```

Result: success; `16` modules transformed.

### Ruff

```powershell
ruff check backend/core/uness/ai_verifier.py `
  backend/core/uness/import_service.py backend/core/uness/models.py `
  tests/test_uness_ai_verifier.py tests/test_uness_import.py `
  tests/test_uness_models.py
```

Result: `All checks passed!`

## Scope protection

The worktree already contained unrelated edits and deletions. They were left
untouched and are excluded from this scoped change.
