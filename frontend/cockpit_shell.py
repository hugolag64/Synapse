"""App shell « cockpit » — sidebar groupée réductible (refonte, session 2).

Rendu uniquement quand preferences['ui_mode'] == 'cockpit'. Le chemin classic
(theme.frame) reste strictement inchangé. Backend intact.

Écart NiceGUI/Quasar (Journal) : le shell N'utilise PAS q-drawer. Un q-drawer
« standard » calcule sa hauteur depuis le q-layout et s'effondre à 0px sans
q-header/q-footer — or le cockpit n'a pas de barre supérieure pleine largeur.
On construit donc la sidebar en CSS (aside position:fixed + contenu margin-left),
ce qui donne un contrôle pixel exact et le collapse 200↔56px (transition width
160ms) sans dépendre du header. L'overlay mobile <768px sera traité en session 17.
"""
from contextlib import contextmanager
from nicegui import ui
from backend.state.store import data_store
from frontend.components.command_palette import open_command_palette

# (glyphe, label, route|None, badge)  badge: None | ('count', '2') | ('dot', 'warning')
_NAV_GROUPS = [
    ("Pilotage", [
        ("◉", "Aujourd'hui", "/",         None),
        ("▦", "Planning",    "/planning", None),
        ("↻", "Révisions",   "/todo",     ("count", "2")),
    ]),
    ("Connaissance", [
        ("▤", "Collèges",  "/colleges",  None),
        ("◫", "Semestres", "/semestres", None),
        ("≡", "Items",     "/items",     None),
        ("✓", "QCM",       "/qcm",       None),
        ("⚑", "Points faibles", "/lacunes", ("dot", "warning")),
    ]),
    ("Analyse", [
        ("◈", "Revue hebdo",   "/revue",    None),
        ("◍", "Statistiques",  "/stats",    None),
        ("◇", "Externat",      "/externat", None),
    ]),
    ("Système", [
        ("⚙", "Paramètres", "/settings", None),
    ]),
]

# Titre de page (passé à frame) → label nav actif
_TITLE_TO_NAV = {
    "Dashboard": "Aujourd'hui", "Tableau de Bord": "Aujourd'hui",
    "Planning": "Planning",
    "Suivi Quotidien": "Révisions",
    "Collèges": "Collèges", "Semestres": "Semestres", "QCM": "QCM",
    "Lacunes": "Points faibles", "Points faibles": "Points faibles", "Fiche cours": "Aujourd'hui",
    "Ma Progression": "Statistiques", "Stats": "Statistiques",
    "Statistiques": "Statistiques", "Externat": "Externat",
    "Paramètres": "Paramètres", "Settings": "Paramètres",
    "Bilan semaine": "Revue hebdo",
}

_SIDEBAR_CSS = """
.cockpit-sidebar { position:fixed; top:0; left:0; bottom:0; width:200px; z-index:1000;
  display:flex; flex-direction:column; background:var(--bg-alt); border-right:1px solid var(--border);
  padding:14px 10px; overflow-y:auto; overflow-x:hidden;
  transition: width 160ms var(--ease-standard); }
.cockpit-sidebar.mini { width:56px; }
.cockpit-sidebar::-webkit-scrollbar { width:0; }

.cockpit-main { margin-left:200px; min-height:100vh; padding:16px 24px 40px; color:var(--text);
  background:var(--bg); transition: margin-left 160ms var(--ease-standard); }
.cockpit-main.mini { margin-left:56px; }

.cockpit-logo { width:24px; height:24px; border-radius:6px; background:var(--accent); color:var(--accent-text);
  font-weight:600; font-size:13px; display:flex; align-items:center; justify-content:center; flex:0 0 24px; }
.cockpit-wordmark { font-family:var(--font-sans); font-weight:600; font-size:13.5px; color:var(--text); }
.cockpit-chevron { color:var(--text-dim); cursor:pointer; font-size:15px; line-height:1; user-select:none; flex:0 0 auto; }
.cockpit-search { display:flex; align-items:center; gap:8px; height:30px; padding:0 8px; margin-top:12px;
  border:1px solid var(--border); border-radius:6px; color:var(--text-dim); font-size:12px; cursor:pointer; background:var(--bg); }
.cockpit-search:hover { border-color:var(--border-strong); }
.cockpit-search kbd { font-family:var(--font-mono); font-size:10.5px; border:1px solid var(--border); border-radius:4px; padding:0 4px; color:var(--text-dim); background:transparent; }
.cockpit-group-label { font-size:10px; text-transform:uppercase; letter-spacing:0.04em; color:var(--text-dim);
  padding:0 8px; margin:14px 0 4px; font-weight:600; }
.cockpit-nav-item { display:flex; align-items:center; gap:10px; height:32px; padding:0 8px; border-radius:6px;
  color:var(--text-muted) !important; font-size:12.5px; text-decoration:none !important; cursor:pointer;
  transition: background var(--duration-fast) var(--ease-standard), color var(--duration-fast) var(--ease-standard); }
.cockpit-nav-item:hover { background:var(--surface); color:var(--text) !important; }
.cockpit-nav-item.active { background:var(--surface); color:var(--text) !important; font-weight:500; }
.cockpit-nav-item.soon { opacity:.55; cursor:default; }
.cockpit-nav-item.soon:hover { background:transparent; color:var(--text-muted) !important; }
.cockpit-nav-item .glyph { font-size:14px; width:16px; text-align:center; flex:0 0 16px; }
.cockpit-nav-item .lbl { flex:1; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.cockpit-badge-count { font-family:var(--font-mono); font-size:10.5px; min-width:16px; height:16px; padding:0 4px;
  border-radius:8px; background:var(--surface-hover); color:var(--text-muted); display:flex; align-items:center; justify-content:center; }
.cockpit-badge-dot { width:6px; height:6px; border-radius:50%; background:var(--warning); flex:0 0 6px; }

/* Mode réduit (56px) : masquer labels / groupes / texte recherche / wordmark / badges */
.cockpit-sidebar.mini .cockpit-group-label,
.cockpit-sidebar.mini .cockpit-nav-item .lbl,
.cockpit-sidebar.mini .cockpit-badge-count,
.cockpit-sidebar.mini .cockpit-search .lbl,
.cockpit-sidebar.mini .cockpit-search kbd,
.cockpit-sidebar.mini .cockpit-wordmark { display:none !important; }
.cockpit-sidebar.mini .cockpit-search { justify-content:center; }
.cockpit-sidebar.mini .cockpit-chevron { transform:rotate(180deg); }
"""


def _nav_item(glyph: str, label: str, route, badge, active: str) -> None:
    soon = route is None
    cls = "cockpit-nav-item"
    if soon:
        cls += " soon"
    elif label == active:
        cls += " active"

    container = ui.element("div") if soon else ui.link(target=route)
    container.classes(cls)
    with container:
        ui.label(glyph).classes("glyph")
        ui.label(label).classes("lbl")
        if soon:
            ui.label("bientôt").classes("lbl").style(
                "flex:0 0 auto;font-size:10px;color:var(--text-dim)"
            )
        elif badge and badge[0] == "count":
            ui.label(badge[1]).classes("cockpit-badge-count")
        elif badge and badge[0] == "dot":
            ui.element("span").classes("cockpit-badge-dot")


@contextmanager
def cockpit_frame(page_title: str):
    ui.add_head_html(f"<style>{_SIDEBAR_CSS}</style>", shared=True)

    dark = ui.dark_mode()
    dark.value = data_store.preferences.get("dark_mode", False)
    ui.colors(primary="#5e6ad2", accent="#5e6ad2", dark="#0f0f14",
              positive="#3fb271", negative="#e5484d", warning="#e5a23f")

    active = _TITLE_TO_NAV.get(page_title, page_title)

    side = ui.element("aside").classes("cockpit-sidebar")
    main = ui.element("div").classes("cockpit-main")
    state = {"mini": False}

    def _toggle():
        state["mini"] = not state["mini"]
        if state["mini"]:
            side.classes(add="mini")
            main.classes(add="mini")
        else:
            side.classes(remove="mini")
            main.classes(remove="mini")

    with side:
        # En-tête : logo + wordmark + chevron
        with ui.row().classes("items-center gap-2 w-full").style("flex-wrap:nowrap"):
            ui.label("S").classes("cockpit-logo")
            ui.label("Synapse").classes("cockpit-wordmark").style("flex:1")
            ui.label("‹").classes("cockpit-chevron").on("click", _toggle)

        # Recherche → command palette
        with ui.element("div").classes("cockpit-search").on("click", open_command_palette):
            ui.label("⌕").style("font-size:14px;flex:0 0 auto")
            ui.label("Rechercher").classes("lbl").style("flex:1")
            ui.html("<kbd>⌘K</kbd>")

        # Nav groupée
        for group_label, items in _NAV_GROUPS:
            ui.label(group_label).classes("cockpit-group-label")
            for glyph, label, route, badge in items:
                _nav_item(glyph, label, route, badge, active)

        # Récents (placeholder — câblage réel session ultérieure)
        ui.label("Récents").classes("cockpit-group-label")
        _nav_item("○", "Item 221 · Athérome", "/", None, active="")
        _nav_item("○", "Item 330 · Prescription", "/", None, active="")

        # Pied : bascule vers l'UI classic
        ui.element("div").style("flex:1 1 auto;min-height:12px")

        def _back_classic():
            data_store.set_preference("ui_mode", "classic")
            ui.navigate.reload()

        with ui.element("div").classes("cockpit-nav-item").on("click", _back_classic):
            ui.label("◐").classes("glyph")
            ui.label("Vue classic").classes("lbl")

    with main:
        yield
