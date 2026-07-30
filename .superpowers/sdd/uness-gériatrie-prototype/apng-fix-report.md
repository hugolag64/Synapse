# UNESS Gériatrie — APNG metadata fix report

Date: 2026-07-30
Base revision: `a6bd57d`

## Reviewer finding resolved

Pillow 10.4 emits `Invalid APNG, will use default PNG image if possible` when
an `acTL` chunk declares zero frames. It then exposes the valid default image
as a one-frame static PNG. The verifier previously treated the `EOFError`
raised while seeking frame 1 as normal end-of-animation and attached the
original malformed APNG bytes to the AI request.

PNG container validation now checks APNG control metadata before Pillow opens
the image:

- `acTL` must have its exact eight-byte payload, occur at most once, and
  declare a nonzero frame count;
- every `fcTL` must have its exact 26-byte payload;
- every `fdAT` must contain at least its four-byte sequence number;
- when `acTL` is present, its declared frame count must equal the number of
  `fcTL` chunks;
- `fcTL` or `fdAT` chunks without `acTL` are rejected.

Malformed animation metadata is therefore classified as `unsupported` before
Pillow can downgrade it or emit its fallback warning.

## Regression coverage

The regression builds a real two-frame APNG with Pillow, rewrites the `acTL`
frame count, and recalculates that chunk's CRC. It covers:

- the reported `num_frames=0` downgrade with the original `fcTL`/`fdAT`
  chunks still present;
- a positive declared frame count that does not match the frame controls.

Preservation coverage explicitly accepts complete animated APNG, GIF, and
WebP inputs. Existing coverage continues to accept complete static PNG, JPEG,
GIF, and WebP inputs.

## Red/green evidence

Before the production change, the reported zero-frame regression failed
because the fake AI service received the malformed bytes:

```text
FAILED test_verifier_rejects_apng_with_invalid_declared_frame_count[zero-frames]
1 failed, 1 passed, 1 warning in 0.42s
```

The warning was Pillow's static fallback:

```text
UserWarning: Invalid APNG, will use default PNG image if possible
```

After the scoped change:

```text
2 passed in 0.41s
```

The complete verifier test module then passed:

```text
42 passed in 0.53s
```

## Verification

### Relevant Python tests

```powershell
$unessTests = Get-ChildItem -LiteralPath 'tests' -Filter 'test_uness_*.py' |
  ForEach-Object { $_.FullName }
.\.venv\Scripts\python.exe -m pytest $unessTests -q
```

Result: `114 passed in 2.59s`.

### React tests

```powershell
cd qcm_app
npm test -- --run
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
ruff check backend/core/uness tests/test_uness_ai_verifier.py
```

Result: `All checks passed!`

## Scope protection

The worktree already contained unrelated edits, deletions, and an untracked
plan. They were left untouched and excluded from this scoped commit.
