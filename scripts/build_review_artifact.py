"""
scripts/build_review_artifact.py
-----------------------------------
Genere la page HTML statique de revue du mapping 59 colleges UNESS -> 36
categories Notion, a partir de data/consolidation_review.json.

Sortie : scratchpad/college_mapping_review.html (a publier via l'outil Artifact)
"""
from __future__ import annotations

import html
import json
import os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_PATH = os.path.join(BASE, "data", "consolidation_review.json")
OUT_PATH = r"C:\Users\hugol\AppData\Local\Temp\claude\C--Users-hugol-Desktop-Projet-Python-Synapse\7ed13ee2-f937-4f0c-8f91-69556ac146ea\scratchpad\college_mapping_review.html"


def fmt_items(items: list[int], limit: int = 10) -> tuple[str, str]:
    full = ", ".join(str(i) for i in items)
    if len(items) <= limit:
        return full, full
    shown = ", ".join(str(i) for i in items[:limit])
    return f"{shown}…", full


def row_html(r: dict) -> str:
    name = html.escape(r["name"])
    acro = html.escape(r["acronym"])
    notion = r["notion"]
    unmapped = notion is None
    notion_html = html.escape(notion) if notion else "— aucune catégorie —"
    e_shown, e_full = fmt_items(r["ecriture_items"])
    r_shown, r_full = fmt_items(r["relecture_items"])
    row_class = "unmapped" if unmapped else ""
    return f"""
    <tr class="{row_class}">
      <td class="col-acro"><code>{acro}</code></td>
      <td class="col-name">{name}</td>
      <td class="col-notion">{notion_html}</td>
      <td class="col-count" title="{html.escape(e_full)}">{r['ecriture_count']}<span class="items">{html.escape(e_shown)}</span></td>
      <td class="col-count" title="{html.escape(r_full)}">{r['relecture_count']}<span class="items">{html.escape(r_shown)}</span></td>
    </tr>"""


def main() -> None:
    data = json.load(open(DATA_PATH, encoding="utf-8"))
    rows = data["rows"]
    unmapped_rows = [r for r in rows if r["notion"] is None]
    mapped_rows = [r for r in rows if r["notion"] is not None]

    total_items_unmapped = len({i for r in unmapped_rows for i in r["ecriture_items"] + r["relecture_items"]})

    rows_html = "\n".join(row_html(r) for r in sorted(rows, key=lambda r: r["name"]))

    unmapped_cards = "\n".join(f"""
      <div class="uc">
        <div class="uc-head">
          <code>{html.escape(r['acronym'])}</code>
          <span class="uc-name">{html.escape(r['name'])}</span>
        </div>
        <div class="uc-body">
          <span class="uc-stat">écriture&nbsp;{r['ecriture_count']}</span>
          <span class="uc-stat">relecture&nbsp;{r['relecture_count']}</span>
          <span class="uc-items">items&nbsp;{html.escape(', '.join(str(i) for i in sorted(set(r['ecriture_items'] + r['relecture_items']))))}</span>
        </div>
      </div>""" for r in sorted(unmapped_rows, key=lambda r: -( r['ecriture_count'] + r['relecture_count'])))

    html_out = f"""<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8" />
<title>Mapping collèges UNESS → Notion</title>
<style>
:root {{
  --bg: #f1f4f3;
  --panel: #ffffff;
  --ink: #16211d;
  --ink-soft: #4b5c56;
  --line: #d7ded9;
  --accent: #2a6f77;
  --accent-soft: #e4eeed;
  --warn: #b8792a;
  --warn-soft: #f8ecd9;
  --mono: ui-monospace, "SFMono-Regular", Consolas, "Liberation Mono", monospace;
}}
@media (prefers-color-scheme: dark) {{
  :root {{
    --bg: #10171a;
    --panel: #17211f;
    --ink: #e7efe9;
    --ink-soft: #a6b8b0;
    --line: #2a3936;
    --accent: #5fb3ae;
    --accent-soft: #1c2f2d;
    --warn: #e0a556;
    --warn-soft: #2c2416;
  }}
}}
:root[data-theme="dark"] {{
  --bg: #10171a; --panel: #17211f; --ink: #e7efe9; --ink-soft: #a6b8b0;
  --line: #2a3936; --accent: #5fb3ae; --accent-soft: #1c2f2d; --warn: #e0a556; --warn-soft: #2c2416;
}}
:root[data-theme="light"] {{
  --bg: #f1f4f3; --panel: #ffffff; --ink: #16211d; --ink-soft: #4b5c56;
  --line: #d7ded9; --accent: #2a6f77; --accent-soft: #e4eeed; --warn: #b8792a; --warn-soft: #f8ecd9;
}}
* {{ box-sizing: border-box; }}
body {{
  margin: 0;
  background: var(--bg);
  color: var(--ink);
  font-family: Georgia, "Iowan Old Style", "Palatino Linotype", serif;
  line-height: 1.5;
}}
.wrap {{ max-width: 1080px; margin: 0 auto; padding: 3rem 1.5rem 5rem; }}
header {{ margin-bottom: 2.5rem; }}
.eyebrow {{
  font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
  font-size: 0.72rem;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: var(--accent);
  font-weight: 600;
  margin-bottom: 0.6rem;
}}
h1 {{
  font-size: 2rem;
  margin: 0 0 0.5rem;
  text-wrap: balance;
  font-weight: 600;
}}
.sub {{
  font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
  color: var(--ink-soft);
  font-size: 0.98rem;
  max-width: 60ch;
}}
.stats {{
  display: flex;
  gap: 0.75rem;
  margin-top: 1.75rem;
  flex-wrap: wrap;
}}
.stat {{
  font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 8px;
  padding: 0.7rem 1rem;
  min-width: 9rem;
}}
.stat .n {{
  font-size: 1.4rem;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
  display: block;
}}
.stat .l {{ font-size: 0.75rem; color: var(--ink-soft); }}
.stat.warn {{ border-color: var(--warn); background: var(--warn-soft); }}
.stat.warn .n {{ color: var(--warn); }}

section {{ margin-top: 3rem; }}
h2 {{
  font-size: 1.15rem;
  font-weight: 600;
  border-bottom: 1px solid var(--line);
  padding-bottom: 0.6rem;
  margin-bottom: 1.2rem;
}}
p.lead {{
  font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
  color: var(--ink-soft);
  font-size: 0.92rem;
  max-width: 68ch;
  margin-top: -0.4rem;
}}

.uc-grid {{
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
  gap: 0.75rem;
  font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
}}
.uc {{
  background: var(--panel);
  border: 1px solid var(--warn);
  border-left: 4px solid var(--warn);
  border-radius: 6px;
  padding: 0.85rem 1rem;
}}
.uc-head {{ display: flex; align-items: baseline; gap: 0.5rem; margin-bottom: 0.4rem; }}
.uc-head code {{
  font-family: var(--mono);
  font-size: 0.75rem;
  background: var(--warn-soft);
  color: var(--warn);
  padding: 0.1rem 0.4rem;
  border-radius: 4px;
}}
.uc-name {{ font-weight: 600; font-size: 0.95rem; }}
.uc-body {{ font-size: 0.82rem; color: var(--ink-soft); }}
.uc-stat {{ margin-right: 0.8rem; font-variant-numeric: tabular-nums; }}
.uc-items {{ display: block; margin-top: 0.35rem; font-family: var(--mono); font-size: 0.76rem; line-height: 1.4; }}

.table-scroll {{ overflow-x: auto; border: 1px solid var(--line); border-radius: 8px; }}
table {{
  border-collapse: collapse;
  width: 100%;
  min-width: 760px;
  font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
  font-size: 0.86rem;
  background: var(--panel);
}}
thead th {{
  text-align: left;
  font-size: 0.7rem;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--ink-soft);
  font-weight: 600;
  padding: 0.65rem 0.85rem;
  border-bottom: 1px solid var(--line);
  position: sticky;
  top: 0;
  background: var(--panel);
}}
tbody td {{
  padding: 0.6rem 0.85rem;
  border-bottom: 1px solid var(--line);
  vertical-align: top;
}}
tbody tr:last-child td {{ border-bottom: none; }}
tbody tr.unmapped {{ background: var(--warn-soft); }}
.col-acro code {{
  font-family: var(--mono);
  font-size: 0.78rem;
  color: var(--accent);
}}
.col-notion {{ color: var(--ink-soft); }}
tr.unmapped .col-notion {{ color: var(--warn); font-weight: 600; }}
.col-count {{ font-variant-numeric: tabular-nums; white-space: nowrap; cursor: default; }}
.col-count .items {{
  display: block;
  font-family: var(--mono);
  font-size: 0.72rem;
  color: var(--ink-soft);
  white-space: normal;
  margin-top: 0.15rem;
}}

footer {{
  margin-top: 3rem;
  font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
  font-size: 0.8rem;
  color: var(--ink-soft);
}}
</style>
</head>
<body>
<div class="wrap">
  <header>
    <div class="eyebrow">Synapse · réconciliation référentiel EDN</div>
    <h1>367 items, 59 collèges UNESS, 36 catégories Notion</h1>
    <p class="sub">Proposition de consolidation des collèges officiels du référentiel nexternat.fr / UNESS vers les catégories Collège existantes dans la base Notion Synapse. À valider avant tout écriture dans Notion.</p>
    <div class="stats">
      <div class="stat"><span class="n">367</span><span class="l">items EDN référencés</span></div>
      <div class="stat"><span class="n">59</span><span class="l">collèges officiels (UNESS)</span></div>
      <div class="stat"><span class="n">36</span><span class="l">catégories Collège (Notion)</span></div>
      <div class="stat warn"><span class="n">9</span><span class="l">collèges sans catégorie Notion</span></div>
      <div class="stat warn"><span class="n">{total_items_unmapped}</span><span class="l">items concernés par ces 9</span></div>
    </div>
  </header>

  <section>
    <h2>À trancher — collèges sans catégorie Notion</h2>
    <p class="lead">Ces collèges officiels n'ont aucune catégorie Collège correspondante dans Notion aujourd'hui. Pour chacun : créer une nouvelle catégorie, ou le rattacher à une catégorie existante ?</p>
    <div class="uc-grid">
      {unmapped_cards}
    </div>
  </section>

  <section>
    <h2>Mapping complet proposé (59 → 36)</h2>
    <p class="lead">Comptage écriture/relecture = nombre d'items EDN distincts où ce collège apparaît dans ce rôle. Survoler un nombre affiche la liste complète des items.</p>
    <div class="table-scroll">
      <table>
        <thead>
          <tr>
            <th>Acronyme</th>
            <th>Collège officiel (UNESS)</th>
            <th>→ Catégorie Notion proposée</th>
            <th>Items écriture</th>
            <th>Items relecture</th>
          </tr>
        </thead>
        <tbody>
          {rows_html}
        </tbody>
      </table>
    </div>
  </section>

  <footer>Source : liste des référentiels — nexternat.fr/externat/items-et-referentiels/liste-des-referentiels · généré le 16 juillet 2026.</footer>
</div>
</body>
</html>
"""
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        f.write(html_out)
    print(f"Écrit : {OUT_PATH}")


if __name__ == "__main__":
    main()
