"""
qcm/service.py — Synapse Phase C
----------------------------------
Logique métier QCM :
  - parse du score (14/20 ou 70%)
  - couleurs / labels selon score
  - helpers de présentation pour les cartes
"""

from __future__ import annotations

import re


# ── Seuils ────────────────────────────────────────────────────────────────────

PASS_THRESHOLD = 70.0     # % : en dessous = raté
WARN_THRESHOLD = 60.0     # % : zone limite
QCM_PASS_THRESHOLD = PASS_THRESHOLD


# ── Parsing du score ──────────────────────────────────────────────────────────

def parse_score(raw: str) -> tuple[float | None, str | None]:
    """
    Convertit une saisie libre en (pourcentage float, affichage str).

    Formats acceptés :
      "14/20"  → (70.0, "14/20")
      "70%"    → (70.0, "70%")
      "70"     → (70.0, "70%")
      "0.7"    → (70.0, "70%")   (fraction 0-1)
      ""       → (None, None)
    """
    raw = raw.strip()
    if not raw:
        return None, None

    # Format fraction X/Y
    if "/" in raw:
        m = re.match(r"^\s*([\d.,]+)\s*/\s*([\d.,]+)\s*$", raw)
        if m:
            try:
                num = float(m.group(1).replace(",", "."))
                den = float(m.group(2).replace(",", "."))
                if den > 0 and 0 <= num <= den:
                    pct = round(num / den * 100, 1)
                    return pct, raw
            except ValueError:
                pass
        return None, None

    # Format pourcentage X%
    if "%" in raw:
        try:
            pct = round(float(raw.replace("%", "").replace(",", ".").strip()), 1)
            if 0 <= pct <= 100:
                return pct, f"{pct}%"
        except ValueError:
            pass
        return None, None

    # Format numérique brut
    try:
        val = float(raw.replace(",", "."))
        if 0 <= val <= 1:          # fraction implicite (ex : 0.7)
            pct = round(val * 100, 1)
            return pct, f"{pct}%"
        if 0 <= val <= 100:
            return round(val, 1), f"{round(val, 1)}%"
    except ValueError:
        pass

    return None, None


# ── Couleur selon score ───────────────────────────────────────────────────────

def score_color(percent: float | None) -> str:
    """
    Retourne une couleur Tailwind/Quasar en fonction du score.
      ≥ 70%  → "green"
      60-70% → "amber"
      < 60%  → "red"
      None   → "slate"
    """
    if percent is None:
        return "slate"
    if percent >= PASS_THRESHOLD:
        return "green"
    if percent >= WARN_THRESHOLD:
        return "amber"
    return "red"


def score_bg_classes(percent: float | None) -> str:
    """Classes Tailwind de fond coloré selon score."""
    if percent is None:
        return "bg-slate-50 text-slate-600 dark:bg-slate-800 dark:text-slate-300"
    if percent >= PASS_THRESHOLD:
        return "bg-green-50 text-green-700 dark:bg-green-900/20 dark:text-green-300"
    if percent >= WARN_THRESHOLD:
        return "bg-amber-50 text-amber-700 dark:bg-amber-900/20 dark:text-amber-300"
    return "bg-red-50 text-red-700 dark:bg-red-900/20 dark:text-red-300"


def score_label(percent: float | None) -> str:
    """Label court : PASSÉ / LIMITE / RATÉ."""
    if percent is None:
        return "—"
    if percent >= PASS_THRESHOLD:
        return "PASSÉ"
    if percent >= WARN_THRESHOLD:
        return "LIMITE"
    return "RATÉ"


def score_display(percent: float | None, raw: str | None) -> str:
    """Affichage principal du score : raw si disponible, sinon N%."""
    if raw:
        return raw
    if percent is not None:
        return f"{percent}%"
    return "—"


def is_failed(percent: float | None) -> bool:
    return percent is not None and percent < PASS_THRESHOLD


# ── Sévérité de lacune suggérée ───────────────────────────────────────────────

def suggested_severity(percent: float | None) -> int:
    """Sévérité de lacune automatique selon score."""
    if percent is None:
        return 2
    if percent < 50:
        return 4
    if percent < 60:
        return 3
    return 2


# ── Platform colors ───────────────────────────────────────────────────────────

PLATFORM_COLORS = {
    "EDNpro":     "purple",
    "Hypocampus": "blue",
    "ChatGPT":    "emerald",
    "Gemini":     "cyan",
}

PLATFORM_BG = {
    "EDNpro":     "bg-purple-50 text-purple-700 dark:bg-purple-900/20 dark:text-purple-300",
    "Hypocampus": "bg-blue-50 text-blue-700 dark:bg-blue-900/20 dark:text-blue-300",
    "ChatGPT":    "bg-emerald-50 text-emerald-700 dark:bg-emerald-900/20 dark:text-emerald-300",
    "Gemini":     "bg-cyan-50 text-cyan-700 dark:bg-cyan-900/20 dark:text-cyan-300",
}

SESSION_TYPE_COLORS = {
    "QCM":     "indigo",
    "DP":      "teal",
    "KFP":     "cyan",
    "Annales": "orange",
}
