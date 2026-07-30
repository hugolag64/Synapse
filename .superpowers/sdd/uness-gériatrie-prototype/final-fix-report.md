# UNESS Gériatrie — final fix report

Date: 2026-07-30

## Implemented findings

- Verified import is now server-enforced. Every proposition must contain a boolean IA verdict, a non-empty explanation, a confidence in `0..1`, a coherent status, and a disagreement comment when applicable before the session can use the `uness-verified-local` marker.
- Canonical exams now require faculty, level, year, title, and complete provenance (`source`, `source_url`, collection date/status). Source URLs are validated and token-bearing URLs are rejected. Normalization rejects a mismatch between the captured URL and human-confirmed metadata.
- Recursive sensitive-key filtering now blocks normalized password, session storage, access/refresh token, authorization, and API-key variants in addition to the existing credential/cookie keys.
- The verifier prompt receives the official answers as non-authoritative comparison input, general DP context, question context, image metadata, and visual-only state. Local filesystem paths are deliberately excluded from the remote prompt.
- Import answer precedence is now manually validated final answer, then IA verdict, then official UNESS answer. The stored correction payload identifies `validated` as the primary source when applicable and carries explicit disagreement metadata.
- React and NiceGUI replay now expose a collapsed-state divergence warning, disagreement comments, the secondary official UNESS correction, DP context, images, and the visual-only warning. A local, path-confined image endpoint makes imported media browser-readable.
- The smoke test now round-trips the verified canonical JSON before importing it. API tests cover verified rejection, manual-final scoring, disagreement/context/image metadata, and local image delivery.
- All six pre-existing Ruff diagnostics in the touched UNESS files/tests were resolved.

## Verification evidence

### Required Python suites

Command:

```text
$testFiles = Get-ChildItem tests -File | Where-Object { $_.Name -like 'test_uness*.py' -or $_.Name -like 'test_qcm*.py' } | Select-Object -ExpandProperty FullName
pytest @testFiles tests/test_ai_practice.py -q
```

Output:

```text
131 passed, 2 warnings in 4.22s
```

The two warnings are existing dependency deprecations/version notices from `requests` and FastAPI/Starlette test tooling; there were no test failures.

### React tests

Command:

```text
npm test
```

Output:

```text
Test Files  1 passed (1)
Tests       3 passed (3)
```

### React production build

Command:

```text
npm run build
```

Output:

```text
16 modules transformed
dist/index.html                   0.41 kB
dist/assets/index-jqv8jicS.css    7.08 kB
dist/assets/index-Cdzgxpna.js   200.78 kB
build completed successfully
```

### Ruff

Command:

```text
ruff check backend/core/uness/__init__.py backend/core/uness/models.py backend/core/uness/artifacts.py backend/core/uness/normalizer.py backend/core/uness/ai_verifier.py backend/core/uness/import_service.py backend/api/qcm.py frontend/components/qcm_replay.py tests/test_uness_models.py tests/test_uness_normalizer.py tests/test_uness_ai_verifier.py tests/test_uness_import.py tests/test_uness_smoke_fixture.py tests/test_qcm_replay.py
```

Output:

```text
All checks passed!
```
