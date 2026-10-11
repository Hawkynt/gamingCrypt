"""Asking before an emulated game is removed - and whether its saves go too.

Used on the game's page (Options) and in Settings -> Storage.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout

from gamingcrypt.emulation import removal
from gamingcrypt.ui.game_widgets import format_size
from gamingcrypt.ui.tasks import run_async
from gamingcrypt.ui.widgets import big_button


def saves_text(paths, saves) -> str:
    """"3 save states and its memory card" - what a game has besides its files."""
    states = [f for f in saves if paths.states in f.parents]
    count = sum(1 for f in states if not f.name.endswith((".png", ".time")))
    parts = []
    if count:
        parts.append(f"{count} save state{'s' if count != 1 else ''}")
    if len(states) < len(saves):
        parts.append("its memory card")
    return " and ".join(parts)


class RemoveConfirm(QFrame):
    """Two questions: really remove it? - and, when it has any, whether its save states and
    memory card are deleted too (asked on its own: a tick box next to Remove was easy to miss)."""

    removed = Signal(str)  # what happened
    cancelled = Signal()

    def __init__(self, paths, game, parent=None):
        super().__init__(parent)
        self.paths, self.game = paths, game
        self.setObjectName("card")
        self.plan = removal.plan(paths, game)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        self.question = QLabel(f"Really remove {game.name}?\nIts game files ({format_size(self.plan.files_size)}) "
                               "are deleted from the drive.")
        self.question.setWordWrap(True)
        layout.addWidget(self.question)
        self.none = QLabel("It has no save states or memory card.")
        self.none.setObjectName("cardMeta")
        self.none.setVisible(not self.plan.saves)
        layout.addWidget(self.none)
        row = QHBoxLayout()
        self.remove_button = big_button("🗑 Remove", "danger")
        self.remove_button.clicked.connect(self.ask_saves if self.plan.saves else lambda: self.confirm(False))
        # the second question's answers
        self.keep_button = big_button("Keep them")
        self.keep_button.clicked.connect(lambda: self.confirm(False))
        self.delete_saves_button = big_button("🗑 Delete them too", "danger")
        self.delete_saves_button.clicked.connect(lambda: self.confirm(True))
        self.cancel_button = big_button("Cancel")
        self.cancel_button.clicked.connect(self.cancelled.emit)
        for button in (self.remove_button, self.keep_button, self.delete_saves_button, self.cancel_button):
            row.addWidget(button)
        self.keep_button.hide()
        self.delete_saves_button.hide()
        row.addStretch()
        layout.addLayout(row)

    def ask_saves(self) -> None:
        """The game goes - and what was saved in it?"""
        what = saves_text(self.paths, self.plan.saves)
        self.question.setText(f"{self.game.name} has {what} ({format_size(self.plan.saves_size)}).\n"
                              "Delete them too? Kept, they are there again when you add the game again.")
        self.remove_button.hide()
        self.keep_button.show()
        self.delete_saves_button.show()
        self.keep_button.setFocus(Qt.FocusReason.TabFocusReason)  # the safe answer first

    def gamepad_back(self) -> bool:
        self.cancelled.emit()
        return True

    def confirm(self, with_saves: bool) -> None:
        for button in (self.remove_button, self.keep_button, self.delete_saves_button, self.cancel_button):
            button.setEnabled(False)
        paths, game = self.paths, self.game

        def done(freed: int) -> None:
            kept = "" if with_saves or not self.plan.saves else " - its saves are kept"
            self.removed.emit(f"{game.name} removed, {format_size(freed)} freed{kept}")

        run_async(lambda: removal.remove(paths, game, with_saves), done,
                  lambda exc: self.removed.emit(f"Could not remove it: {exc}"), owner=self)
