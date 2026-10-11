"""Which game is this file? - a list of the system's games to choose from, for a file the
automatic matching didn't recognise. Its cover, genre and year come by the chosen name then
(emulation/names)."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QLineEdit, QScrollArea, QVBoxLayout, QWidget

from gamingcrypt.emulation import names as names_mod
from gamingcrypt.ui.tasks import run_async
from gamingcrypt.ui.widgets import (KeyboardFocusFilter, OnScreenKeyboard, big_button, enable_touch_scroll,
                                    set_status)

SHOWN = 40  # typing narrows it down - a longer list is no help on a controller


class IdentifyPage(QWidget):
    chosen = Signal(object)  # the official name - or None: found automatically again

    def __init__(self, tab, game, parent: QWidget | None = None):
        super().__init__(parent)
        self.tab, self.game = tab, game
        self.names: list[str] | None = None  # every game of the system; None: not loaded (yet)
        self.buttons: list[QWidget] = []
        current = tab.rom_names.get(game) if tab.rom_names is not None else None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 16, 30, 10)
        top = QHBoxLayout()
        top.addWidget(tab.back_button())
        title = QLabel("Which game is this?")
        title.setObjectName("title")
        top.addWidget(title, 1)
        self.automatic_button = big_button("Find it automatically")
        self.automatic_button.setToolTip("Forget the choice: matched by the file's name again")
        self.automatic_button.clicked.connect(lambda: self.chosen.emit(None))
        self.automatic_button.setVisible(current is not None)
        top.addWidget(self.automatic_button)
        layout.addLayout(top)
        self.hint = QLabel(f"File: {game.path.name}  ·  {game.system.name}"
                           + (f"\nChosen: {current}" if current else ""))
        self.hint.setObjectName("cardMeta")
        self.hint.setWordWrap(True)
        layout.addWidget(self.hint)
        self.search = QLineEdit()
        self.search.setPlaceholderText("🔍  Type a part of the game's name")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(lambda _t: self.fill())
        layout.addWidget(self.search)
        self.status = QLabel("")
        self.status.setObjectName("status")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        enable_touch_scroll(scroll)
        inner = QWidget()
        self.list = QVBoxLayout(inner)
        self.list.setContentsMargins(0, 0, 0, 0)
        self.list.setSpacing(8)
        self.list.addStretch()
        scroll.setWidget(inner)
        layout.addWidget(scroll, 1)
        self.keyboard = OnScreenKeyboard(self.search)
        self.keyboard.submitted.connect(self.keyboard.hide)
        self.keyboard.dismissable = True
        self.keyboard.hide()
        self._focus_filter = KeyboardFocusFilter(self.keyboard, self)
        self._focus_filter.watch(self.search)
        layout.addWidget(self.keyboard)
        set_status(self.status, f"Loading the list of {game.system.name} games…")
        covers, facts = getattr(tab, "covers", None), getattr(tab, "rom_facts", None)
        run_async(lambda: names_mod.titles(game, covers, facts), self._loaded, lambda _e: self._loaded(None),
                  owner=self)

    def _loaded(self, names) -> None:
        self.names = names
        self.fill()

    def fill(self) -> None:
        for button in self.buttons:
            self.list.removeWidget(button)
            button.deleteLater()
        self.buttons = []
        if self.names is None:
            if not self.status.text().startswith("Loading"):
                return
            set_status(self.status, "Couldn't load the list of games - no network?", error=True)
            return
        text = self.search.text().strip()
        found = names_mod.suggest(self.game.path.name, self.names, text, limit=SHOWN + 1)
        for name in found[:SHOWN]:
            button = big_button(name)
            button.setStyleSheet("text-align: left;")
            button.clicked.connect(lambda _c=False, n=name: self.chosen.emit(n))
            self.list.insertWidget(self.list.count() - 1, button)
            self.buttons.append(button)
        if not found:
            set_status(self.status, "No game with that name - try another part of it" if text else
                       "Nothing looks like the file's name - type a part of the game's name")
        elif len(found) > SHOWN:
            set_status(self.status, f"The first {SHOWN} - type more of the name to narrow it down")
        else:
            set_status(self.status, f"{len(found)} game{'s' if len(found) != 1 else ''} - choose yours")
