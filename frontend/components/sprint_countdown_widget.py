"""
sprint_countdown_widget.py — Synapse
------------------------------------
Widget UI Streamlit pour le Sprint Countdown EDN.
"""

from __future__ import annotations

import streamlit as st
from backend.core.planning.sprint_countdown import SprintCountdownService, SprintPhase


def render_sprint_countdown_widget(service: SprintCountdownService | None = None) -> None:
    """Rendu du widget Sprint Countdown EDN dans le Dashboard ou Header."""
    service = service or SprintCountdownService()
    status = service.get_sprint_status()

    col1, col2, col3 = st.columns([1, 2, 1])

    with col1:
        st.metric(
            label="📅 Compte à Rebours EDN",
            value=f"J-{status.days_remaining}",
            delta=f"Objectif {status.target_date.strftime('%d/%m/%Y')}",
        )

    with col2:
        st.markdown(f"**Focus Rythme ({status.phase.value.upper()})**")
        st.info(status.focus_message)

    with col3:
        st.caption("⚡ Ratios Préconisés :")
        st.write(f"• Nouveaux : **{int(status.recommended_new_ratio * 100)}%**")
        st.write(f"• Révisions : **{int(status.recommended_review_ratio * 100)}%**")
        st.write(f"• DP / QCM : **{int(status.recommended_qcm_dp_ratio * 100)}%**")
