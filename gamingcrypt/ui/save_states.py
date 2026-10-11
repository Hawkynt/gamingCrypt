"""Save / load state of a running emulated game: nine slots in a 3 by 3 grid, each with the
picture of the moment it was saved (opened from the quick menu, over the game)."""

from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPixmap
from PySide6.QtWidgets import QGridLayout, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from gamingcrypt.emulation.savestates import State
from gamingcrypt.ui import theme
from gamingcrypt.ui.game_widgets import Cover, Tappable, card_margins
from gamingcrypt.ui.widgets import big_button

COLUMNS = 3
CAPTION_H = 30


def saved_text(saved_at: float) -> str:
    """Date and time it was saved: "12 Oct 2026 · 18:45"."""
    return f"{datetime.fromtimestamp(saved_at):%d %b %Y · %H:%M}"


def placeholder(w: int, h: int, text: str, symbol: str = "") -> QPixmap:
    """No picture: an empty slot, or a state saved before there were pictures."""
    pix = QPixmap(w, h)
    pix.fill(QColor(theme.SURFACE_HI or "#232733"))
    painter = QPainter(pix)
    color = QColor(theme.TEXT_DIM or "#9aa3b5")
    painter.setPen(color)
    font = QFont()
    if symbol:
        font.setPixelSize(max(12, int(h * 0.34)))
        painter.setFont(font)
        painter.drawText(QRectF(0, 0, w, h * 0.72), Qt.AlignmentFlag.AlignCenter, symbol)
    font.setPixelSize(max(10, int(h * 0.11)))
    painter.setFont(font)
    area = QRectF(0, h * 0.62, w, h * 0.3) if symbol else QRectF(0, 0, w, h)
    painter.drawText(area, Qt.AlignmentFlag.AlignCenter, text)
    painter.end()
    return pix


class StateTile(Tappable):
    def __init__(self, state: State, w: int, h: int, parent: QWidget | None = None):
        super().__init__(parent)
        self.state = state
        self.has_picture = False
        self.setObjectName("card")
        self.setFixedSize(w, h)
        layout = QVBoxLayout(self)
        card_margins(layout)
        layout.setSpacing(4)
        inner_w, inner_h = w - 20, h - 26 - CAPTION_H  # the card's edge and padding, the gap to the caption
        self.picture = Cover()
        self.picture.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.picture.setFixedSize(inner_w, inner_h)
        pixmap = QPixmap(str(state.picture)) if state.picture is not None else QPixmap()
        if not pixmap.isNull():
            self.has_picture = True
            pixmap = pixmap.scaled(inner_w, inner_h, Qt.AspectRatioMode.KeepAspectRatio,
                                   Qt.TransformationMode.SmoothTransformation)
        elif state.empty:
            pixmap = placeholder(inner_w, inner_h, "Empty")
        else:
            pixmap = placeholder(inner_w, inner_h, "No picture", "💾")
        self.picture.setPixmap(pixmap)
        layout.addWidget(self.picture)
        below = QHBoxLayout()  # under the picture: when it was saved, and which slot it is
        below.setContentsMargins(0, 0, 0, 0)
        self.when = QLabel("" if state.empty else saved_text(state.saved_at))
        self.caption = QLabel(f"Slot {state.slot + 1}")
        for label in (self.when, self.caption):
            label.setObjectName("cardMeta")
            label.setFixedHeight(CAPTION_H)
        below.addWidget(self.when, 1)
        below.addWidget(self.caption)
        layout.addLayout(below)


class SaveStatesPage(QWidget):
    chosen = Signal(int)  # the slot to save into / to load
    closed = Signal()  # left without choosing

    def __init__(self, states: list[State], mode: str, game_name: str = "", parent: QWidget | None = None):
        super().__init__(parent)
        self.mode = mode
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        if parent is not None:
            self.setGeometry(parent.rect())
        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 16, 30, 16)
        layout.setSpacing(12)
        top = QHBoxLayout()
        self.title = QLabel("Save state" if mode == "save" else "Load state")
        self.title.setObjectName("title")
        top.addWidget(self.title)
        hint = "Pick the slot to save into" if mode == "save" else "Pick the state to go back to"
        self.hint = QLabel(f"{game_name}  ·  {hint}" if game_name else hint)
        self.hint.setObjectName("cardMeta")
        top.addWidget(self.hint, 1)
        self.back_button = big_button("Back")
        self.back_button.clicked.connect(self.closed.emit)
        top.addWidget(self.back_button)
        layout.addLayout(top)

        grid = QGridLayout()
        grid.setSpacing(14)
        rows = -(-len(states) // COLUMNS)
        w = (self.width() - 60 - grid.spacing() * (COLUMNS - 1)) // COLUMNS
        h = (self.height() - 32 - 80 - 12 - grid.spacing() * (rows - 1)) // rows
        w, h = max(180, min(w, 520)), max(120, h)
        self.tiles: list[StateTile] = []
        for index, state in enumerate(states):
            tile = StateTile(state, w, h)
            tile.setEnabled(mode == "save" or not state.empty)  # nothing to load from an empty slot
            tile.tapped.connect(lambda s=state: self._tapped(s))
            grid.addWidget(tile, index // COLUMNS, index % COLUMNS, Qt.AlignmentFlag.AlignCenter)
            self.tiles.append(tile)
        layout.addLayout(grid, 1)
        self.first = self._first(states)

    def _first(self, states: list[State]) -> QWidget:
        """Where the controller starts: saving on the first empty slot (else the oldest state),
        loading on the newest state."""
        filled = [s for s in states if not s.empty]
        if self.mode == "save":
            empty = [s for s in states if s.empty]
            start = empty[0] if empty else min(filled, key=lambda s: s.saved_at, default=None)
        else:
            start = max(filled, key=lambda s: s.saved_at, default=None)
        return self.tiles[states.index(start)] if start is not None else self.back_button

    def showEvent(self, event) -> None:  # noqa: N802 - Qt API
        super().showEvent(event)
        self.first.setFocus(Qt.FocusReason.TabFocusReason)

    def _tapped(self, state: State) -> None:
        if self.mode == "save" and not state.empty:
            from gamingcrypt.ui.modal import ask

            ask(self, f"Save over slot {state.slot + 1}?\nThe state from {saved_text(state.saved_at)} is replaced.",
                "💾  Save over it", lambda: self.chosen.emit(state.slot))
            return
        self.chosen.emit(state.slot)

    def gamepad_back(self) -> bool:
        self.closed.emit()
        return True
