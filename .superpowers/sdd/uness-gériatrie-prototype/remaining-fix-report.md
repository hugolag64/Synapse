# UNESS Gériatrie — remaining blocker fix report

Date: 2026-07-30  
Base revision: `e6c8ffd`

## Implemented

- Added a multimodal image-content contract to the configured AI route. The UNESS verifier resolves confined local media, sends image bytes as Gemini `inlineData`, and never puts image source URLs or local filesystem paths in the remote prompt.
- Images that cannot be safely loaded are marked with `verification_status: unsupported`. The prompt explicitly says that visual verification is unavailable and forbids claims that the image was seen.
- Added configured artifact-root support and a confined local media resolver. Workspace-relative normalized paths such as `data/uness/artifacts/...` now resolve through the QCM image endpoint without weakening path traversal protections.
- Expanded recursive secret rejection to dictionaries, lists, and tuples, covering password, session storage, client secret, ID token, generic/auth/access/refresh tokens, authorization, API keys, credentials, cookies, and local storage. HTTP(S) URLs carrying sensitive query, fragment, or user-info data are rejected anywhere in the canonical payload.
- Applied the same secret gate before AI prompt construction as well as at model, save, and import persistence boundaries.
- Added UNESS provenance disclosure to the React correction and NiceGUI replay: source URL, faculty, level, year, collection timestamp, and collection status are shown when available.
- Made the verifier require a boolean `verdict_ia`, matching the verified-import contract. A shared regression proves both boundaries reject `null`.
- Expanded AI transport, verifier, import/API, replay UI, React, and smoke coverage for these contracts.

## Verification

### Relevant Python UNESS/QCM/AI suites

```text
$testFiles = Get-ChildItem tests -File | Where-Object {
  $_.Name -like 'test_uness*.py' -or
  $_.Name -like 'test_qcm*.py' -or
  $_.Name -like 'test_ai*.py' -or
  $_.Name -eq 'test_gemini_client.py'
} | Select-Object -ExpandProperty FullName
pytest @testFiles -q
```

Result: `176 passed, 2 warnings in 6.20s`.

The warnings are existing dependency notices from `requests` and FastAPI/Starlette test tooling.

### React tests

```text
npm test -- --run
```

Result: `1` test file passed, `3` tests passed.

### React production build

```text
npm run build
```

Result: success; `16` modules transformed and production assets emitted.

### Ruff

```text
ruff check <all touched Python source and test files>
```

Result: `All checks passed!`

### TypeScript standalone typecheck

```text
npx tsc --noEmit
```

Result: not an available clean gate in the existing package. It fails because the project does not install declaration packages for React/ReactDOM and has no CSS module declaration (`@types/react`, `@types/react-dom`, and a `*.css` declaration). These baseline dependency/configuration gaps produce the cascading JSX errors. No dependency or typecheck setup expansion was made because it is outside the remaining UNESS blocker scope; the required Vite production build succeeds.

## Scope protection

The worktree already contained unrelated user edits and deletions. They were left untouched; only the UNESS/QCM/AI implementation, its tests, generated QCM production assets, and this report are included in the scoped commit.
