"""Feuille de surcharge de tokens — Refonte UI « cockpit » (Linear Editorial).

Chargée globalement via ui.add_head_html (shared). NE définit QUE des variables
CSS + la police mono : aucune règle appliquée directement aux composants.
Le shell cockpit consomme ces variables.

Valeurs = section « Design Tokens » du handoff. Les 4 tokens marqués « cf. DS »
dans le README (_ds/ non livré) sont DÉRIVÉS et notés dans le Journal du CLAUDE.md
de handoff :
  --accent-hover  : accent assombri ~9% (clair) / éclairci (sombre)
  --accent-text   : #ffffff / #0f0f14  (donné ~ dans le README)
  --accent-wash   : accent très pâle — solide en clair, translucide en sombre
  --border-strong : une marche plus soutenue que --border
"""
from nicegui import ui

_TOKENS_CSS = """
/* ── Police mono du cockpit (additif, n'affecte pas IBM Plex Mono existant) ── */
@import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;600&display=swap');

:root {
  /* Couleurs — clair */
  --bg: #ffffff;
  --bg-alt: #fafafa;
  --surface: #f4f4f5;
  --surface-hover: #ececee;
  --text: #0f0f14;
  --text-muted: #6b6b76;
  --text-dim: #a0a0ab;
  --border: #e4e4e7;
  --border-strong: #d4d4d8;        /* dérivé */
  --accent: #5e6ad2;
  --accent-hover: #4f5ac0;         /* dérivé : accent assombri */
  --accent-text: #ffffff;          /* dérivé */
  --accent-wash: #eef0fb;          /* dérivé : accent très pâle (solide) */

  /* Sémantiques — stables clair & sombre */
  --success: #3fb271;
  --warning: #e5a23f;
  --danger: #e5484d;
  --college-late-bg: rgba(229, 72, 77, 0.08);
  --scrim: rgba(15, 15, 20, 0.32);

  /* Variantes lisibles en texte sur fond clair */
  --success-text: #15803d;
  --danger-text: #b4232a;
  --warning-text: #96591a;

  /* Typographie */
  --font-sans: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
  --font-mono: 'JetBrains Mono', 'IBM Plex Mono', ui-monospace, monospace;

  /* Rayons (plafond 8px, pas de pills) */
  --radius-sm: 4px;
  --radius-md: 6px;
  --radius-lg: 8px;

  /* Mise en page partagée */
  --content-readable: 1100px;
  --content-full: 100%;
  --panel-padding: 20px;
  --grid-gap: 12px;

  /* Profondeur — une seule ombre (popover) */
  --shadow-popover: 0 2px 8px rgba(0, 0, 0, 0.04);

  /* Motion */
  --duration-fast: 120ms;
  --duration-base: 180ms;
  --ease-standard: ease-out;

  /* Espacement (base 4px) */
  --space-1: 4px;  --space-2: 8px;  --space-3: 12px; --space-4: 16px;
  --space-6: 24px; --space-8: 32px; --space-12: 48px; --space-16: 64px;
}

/* ── Sombre : Quasar pose body.body--dark ; on couvre aussi [data-theme] ── */
.body--dark,
[data-theme="dark"] {
  --bg: #0f0f14;
  --bg-alt: #15151b;
  --surface: #1a1a20;
  --surface-hover: #232329;
  --text: #f4f4f6;
  --text-muted: #8b8b96;
  --text-dim: #5c5c68;
  --border: #26262f;
  --border-strong: #33333d;        /* dérivé */
  --accent: #7b85e8;
  --accent-hover: #8f98ec;         /* dérivé : accent éclairci */
  --accent-text: #0f0f14;          /* dérivé */
  --accent-wash: rgba(123, 133, 232, 0.14);  /* dérivé : translucide sur fond sombre */
  --shadow-popover: 0 2px 8px rgba(0, 0, 0, 0.40);  /* dérivé : visible sur sombre */
  --success-text: var(--success);
  --danger-text: var(--danger);
  --warning-text: var(--warning);
}
"""


def apply_design_tokens() -> None:
    """Injecte la feuille de tokens une seule fois, globalement."""
    ui.add_head_html(f"<style>{_TOKENS_CSS}</style>", shared=True)
