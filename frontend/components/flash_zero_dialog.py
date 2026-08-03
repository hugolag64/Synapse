"""
flash_zero_dialog.py — Synapse
------------------------------
Composant dialog / modale Streamlit pour le Morning Flash-Zero Quiz.
"""

from __future__ import annotations

import streamlit as st
from backend.core.practice.flash_zero_service import FlashZeroService


def render_flash_zero_dialog(service: FlashZeroService | None = None) -> None:
    """Affiche l'interface interactive du quiz matinal Flash-Zero."""
    service = service or FlashZeroService()

    st.markdown("### ⚡ Morning Flash-Zero Quiz (5 min)")
    st.caption("10 questions express ciblées sur les Zéros Éliminatoires, contre-indications et pièges EDN.")

    if "fz_quiz" not in st.session_state or st.button("🔄 Regénérer un quiz Flash-Zero"):
        st.session_state.fz_quiz = service.get_morning_quiz(count=10)
        st.session_state.fz_index = 0
        st.session_state.fz_score = 0
        st.session_state.fz_zero_errors = 0
        st.session_state.fz_answers = {}

    quiz = st.session_state.fz_quiz
    idx = st.session_state.get("fz_index", 0)

    if idx >= len(quiz):
        st.success(f"🎉 **Quiz Terminé !** Score : {st.session_state.fz_score} / {len(quiz)}")
        if st.session_state.fz_zero_errors > 0:
            st.error(f"⚠️ Attention : {st.session_state.fz_zero_errors} piège(s) Zéro Éliminatoire manqué(s) !")
        else:
            st.info("🛡️ Zéro Éliminatoire commis ! Excellente vigilance sur le Rang A.")
        return

    q = quiz[idx]
    st.progress((idx) / len(quiz), text=f"Question {idx + 1} / {len(quiz)} — {q.category}")
    st.markdown(f"**[{q.item_number}] {q.item_title}**")
    st.write(q.question_text)

    choice = st.radio("Sélectionnez votre réponse :", q.choices, key=f"fz_radio_{idx}")

    if st.button("Valider", key=f"fz_btn_{idx}"):
        selected_idx = q.choices.index(choice)
        if selected_idx == q.correct_idx:
            st.success("✅ Bonne réponse !")
            st.session_state.fz_score += 1
        else:
            st.error(f"❌ Mauvaise réponse. La réponse correcte était : **{q.choices[q.correct_idx]}**")
            if q.is_zero_eliminatoire:
                st.session_state.fz_zero_errors += 1
        
        st.info(f"💡 **Explication :** {q.explanation}")
        st.session_state.fz_index += 1
