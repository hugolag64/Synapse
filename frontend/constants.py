"""
Constantes de classes Tailwind réutilisables.
Évite de répéter des chaînes comme 'text-slate-800 dark:text-slate-100' partout.
"""

# ── Texte ──────────────────────────────────────────────────────────────────────
TEXT_PRIMARY   = "text-slate-900 dark:text-slate-100"
TEXT_SECONDARY = "text-slate-600 dark:text-slate-400"
TEXT_MUTED     = "text-slate-400 dark:text-slate-500"
TEXT_ACCENT    = "text-violet-600 dark:text-violet-400"
TEXT_DANGER    = "text-red-500 dark:text-red-400"
TEXT_SUCCESS   = "text-emerald-600 dark:text-emerald-400"

# ── Fonds & bordures ───────────────────────────────────────────────────────────
CARD_BG        = "bg-white dark:bg-slate-900"
CARD_BORDER    = "border border-slate-200 dark:border-slate-800"
SURFACE_BG     = "bg-slate-50 dark:bg-slate-950"
HOVER_BG       = "hover:bg-slate-50 dark:hover:bg-slate-800/50"

# ── Cartes standard ────────────────────────────────────────────────────────────
CARD_BASE      = f"w-full rounded-2xl shadow-sm {CARD_BG} {CARD_BORDER}"

# ── Titres de page ─────────────────────────────────────────────────────────────
PAGE_TITLE     = f"text-2xl font-bold {TEXT_PRIMARY}"
SECTION_TITLE  = f"font-bold text-[13px] {TEXT_SECONDARY} uppercase tracking-widest"

# ── Labels de badge ───────────────────────────────────────────────────────────
BADGE_SM       = "text-[12px] px-2 py-0.5"
BADGE_MD       = "text-[12px] px-2.5 py-1"

# ── Inputs ─────────────────────────────────────────────────────────────────────
INPUT_CLASSES  = "w-full bg-white dark:bg-slate-900"
