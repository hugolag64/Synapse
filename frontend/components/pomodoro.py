"""
PomodoroController — composant extrait de dashboard.py (#18).
"""
from nicegui import ui


class PomodoroController:
    def __init__(self):
        self.active = False
        self.mode = 50
        self.time = 50 * 60
        self.total = 50 * 60
        self.timer: ui.timer | None = None
        self.lbl_time: ui.label | None = None
        self.btn_icon: ui.icon | None = None
        self.lbl_status: ui.label | None = None
        self.bar: ui.linear_progress | None = None

    def _fmt(self, s: int) -> str:
        m, sec = divmod(s, 60)
        return f"{m:02d}:{sec:02d}"

    def _refresh_ui(self):
        if self.lbl_time:
            self.lbl_time.set_text(self._fmt(self.time))
        if self.bar and self.total:
            self.bar.set_value(self.time / self.total)
        if self.btn_icon:
            self.btn_icon.props(f'name={"pause" if self.active else "play_arrow"}')
        if self.lbl_status:
            self.lbl_status.set_text("Focus en cours…" if self.active else "Prêt à démarrer ?")

    async def tick(self):
        if self.active and self.time > 0:
            self.time -= 1
            self._refresh_ui()
            if self.time == 0:
                self.active = False
                if self.timer:
                    self.timer.deactivate()
                ui.notify("Session terminée ! 🔔", type="positive")
                self._refresh_ui()

    def toggle(self):
        self.active = not self.active
        if self.active:
            if self.timer:
                self.timer.activate()
        else:
            if self.timer:
                self.timer.deactivate()
        self._refresh_ui()

    def reset(self):
        self.active = False
        if self.timer:
            self.timer.deactivate()
        self.time = self.mode * 60
        self.total = self.mode * 60
        self._refresh_ui()

    def set_mode(self, m: int):
        self.mode = m
        self.reset()
        ui.notify(f"Mode {m} min activé", type="info")
