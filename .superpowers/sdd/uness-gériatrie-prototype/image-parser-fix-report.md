# UNESS Gériatrie — image parser hardening report

Date: 2026-07-30
Base revision: `efe8bb0`

## Reviewer findings resolved

1. **Exact container endings are required**
   - PNG chunks must end exactly at the zero-length `IEND` chunk.
   - JPEG marker and scan parsing must reach the first `EOI` marker at EOF.
   - GIF blocks and sub-blocks must reach the first trailer at EOF.
   - WebP RIFF length, chunk boundaries, and padding must consume the complete
     file.
   - A valid PNG, JPEG, GIF, or WebP followed by token-bearing bytes is now
     classified as `unsupported` and never attached to the AI request.

2. **Every frame is decoded behind a safe failure boundary**
   - Pillow verifies the container, then a fresh decoder loads every frame
     until a normal `EOFError` from seeking the next frame.
   - Decode and parser failures including `IndexError`, `struct.error`,
     `ValueError`, `EOFError`, syntax errors, and I/O errors are classified as
     `unsupported`.
   - Regressions exercise two real truncation points in a two-frame GIF that
     previously escaped as `IndexError` and `struct.error`.

3. **Decompression warnings fail closed before pixel loading**
   - `PIL.Image.DecompressionBombWarning` is promoted to an exception while
     opening, verifying, and decoding an image.
   - Both Pillow decompression-bomb warnings and errors result in
     `unsupported`.
   - The existing maximum image count, per-image byte limit, and aggregate
     byte limit remain unchanged and continue to run before decoding.

4. **Valid supported images remain accepted**
   - Regression coverage admits complete PNG, JPEG, GIF, and WebP fixtures
     with the detected MIME type and `provided_to_ai` status.

## Red/green evidence

Before the production change, the focused regression command produced seven
failures while all four valid-container cases passed:

- four supported formats accepted token-bearing trailing bytes;
- two truncated multi-frame GIFs escaped as `IndexError` and `struct.error`;
- an image that emitted `DecompressionBombWarning` was still attached to the
  AI request.

After the scoped change, the same focused selection passed:

```text
11 passed, 26 deselected in 0.39s
```

## Verification

### Relevant Python tests

```powershell
$unessTestFiles = Get-ChildItem -LiteralPath 'tests' -Filter 'test_uness*.py' |
  ForEach-Object FullName
.\.venv\Scripts\python.exe -m pytest @unessTestFiles -q
```

Result: `109 passed in 2.75s`.

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
ruff check backend/core/uness/ai_verifier.py tests/test_uness_ai_verifier.py
```

Result: `All checks passed!`

## Scope protection

The worktree already contained unrelated edits, deletions, and an untracked
plan. They were left untouched and excluded from this scoped commit.
