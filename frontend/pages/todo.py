"""
todo.py — Redirection vers le Cockpit Suivi Quotidien.
"""
from frontend.theme import frame


async def todo_page():
    with frame("Suivi Quotidien"):
        from frontend.pages.todo_cockpit import render_revisions_cockpit
        await render_revisions_cockpit()
        return
