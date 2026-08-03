# DP Coverage Panel Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make DP coverage follow real multi-college course links and keep every count visible without horizontal scrolling.

**Architecture:** Keep the static EDN mapping as fallback metadata, then merge it with college memberships derived from `data_store.cours`. The UI consumes a pure row-building helper and renders the rows with a CSS grid that does not require a fixed college column.

**Tech Stack:** Python 3.13, NiceGUI, pytest, CSS.

## Global Constraints

- Use `data_store.cours` for actual college memberships and deduplicate by EDN item number.
- Preserve `local_store.get_dp_count_by_item()` as the source of DP counts.
- Do not add horizontal scrolling; the DP count remains visible at all viewport widths.

---

### Task 1: Build rows from real college memberships

**Files:**
- Modify: `frontend/components/dp_coverage_panel.py`
- Create: `tests/test_dp_coverage_panel.py`

**Interfaces:**
- Consumes: `all_items() -> list[dict]`, `college_full(str) -> str`, and course objects exposing `item_number`, `college`, and `title`.
- Produces: `_coverage_rows(courses, counts) -> list[dict]`, with `item`, `title`, `colleges`, and `count` keys.

- [ ] **Step 1: Write the failing test**

```python
def test_coverage_rows_include_a_course_multi_college_membership():
    rows = _coverage_rows(
        [SimpleNamespace(item_number="269", college=["Dermatologie 🧴"], title="Douleur abdominale")],
        {"269": 2},
    )
    row = next(row for row in rows if row["item"] == 269)
    assert row["colleges"] == {"Dermatologie 🧴"}
    assert row["count"] == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.\\.venv\\Scripts\\python.exe -m pytest tests/test_dp_coverage_panel.py -q`

Expected: FAIL because `_coverage_rows` does not exist.

- [ ] **Step 3: Write minimal implementation**

```python
def _coverage_rows(courses, counts):
    by_item = {int(entry["item"]): {"title": entry.get("title", ""), "colleges": {college_full(entry.get("college", ""))} - {""}} for entry in all_items()}
    for course in courses:
        item = _item_number(getattr(course, "item_number", ""))
        if item is None:
            continue
        entry = by_item.setdefault(item, {"title": getattr(course, "title", ""), "colleges": set()})
        entry["colleges"].update(getattr(course, "college", None) or [])
    return [{"item": item, "title": entry["title"], "colleges": entry["colleges"], "count": counts.get(str(item), 0)} for item, entry in by_item.items()]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.\\.venv\\Scripts\\python.exe -m pytest tests/test_dp_coverage_panel.py -q`

Expected: PASS.

### Task 2: Render the merged rows without horizontal overflow

**Files:**
- Modify: `frontend/components/dp_coverage_panel.py`
- Modify: `tests/test_dp_coverage_panel.py`

**Interfaces:**
- Consumes: `_coverage_rows(courses, counts) -> list[dict]`.
- Produces: panel rows filtered by any membership in the selected college; `.dpc-row` CSS grid with the count column visible.

- [ ] **Step 1: Write the failing test**

```python
def test_dp_coverage_css_uses_a_non_scrolling_grid():
    assert "grid-template-columns:56px minmax(0,1fr) 64px" in panel._CSS
    assert "overflow-x:hidden" in panel._CSS
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.\\.venv\\Scripts\\python.exe -m pytest tests/test_dp_coverage_panel.py::test_dp_coverage_css_uses_a_non_scrolling_grid -q`

Expected: FAIL because the current rows are flex columns with nowrap titles.

- [ ] **Step 3: Write minimal implementation**

```python
.dpc-row { display:grid; grid-template-columns:56px minmax(0,1fr) 64px; }
.dpc-title { white-space:normal; overflow-wrap:anywhere; }
.dpc-scroll { overflow-x:hidden; }
```

Filter selected colleges with `state["college"] in row["colleges"]`; render the college list as subtext only in the global view.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.\\.venv\\Scripts\\python.exe -m pytest tests/test_dp_coverage_panel.py -q`

Expected: PASS.

### Task 3: Verify the panel change against relevant regression tests

**Files:**
- Verify: `tests/test_dp_coverage_panel.py`
- Verify: `tests/test_settings.py`

- [ ] **Step 1: Run focused Python tests**

Run: `.\\.venv\\Scripts\\python.exe -m pytest tests/test_dp_coverage_panel.py tests/test_settings.py -q`

Expected: PASS.

- [ ] **Step 2: Run static diff validation**

Run: `git diff --check`

Expected: exit code 0.
