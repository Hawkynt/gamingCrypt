"""Pictures of the emulated systems' controllers, for the emulator controls page.

Each picture is a body shape plus the console's buttons at their place (in a
1000 x 560 drawing). The buttons are real, selectable buttons laid over the
drawing - see controls_page.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QTransform

from gamingcrypt.ui import theme

W, H = 1000, 560
# button kinds: size in the drawing
SIZES = {"dir": (50, 50), "face": (68, 68), "big": (84, 84), "c": (50, 50), "small": (96, 36), "shoulder": (160, 46)}


@dataclass(frozen=True)
class Picture:
    body: str  # pad, rect, trident, portrait, landscape, stick, panel
    buttons: dict[str, tuple[int, int, str]]  # console button -> (x, y, kind)
    dpad: tuple[int, int] | None = (250, 300)
    sticks: tuple[tuple[int, int], ...] = ()
    screen: tuple[int, int, int, int] | None = None  # x, y, w, h
    colors: dict[str, str] = field(default_factory=dict)  # console button -> its color
    # drawn only (not buttons): ("well", x, y, r) - a hollow the buttons sit in;
    # ("dot", x, y, r, color[, text]) - e.g. the C buttons that aren't their own; ("led", x, y, r, color)
    decor: tuple[tuple, ...] = ()
    split_dpad: bool = False  # PlayStation: four separate arrows, not one cross


def _face(top: str, left: str, right: str, bottom: str, x: int = 750, y: int = 300, d: int = 72) -> dict:
    return {top: (x, y - d, "face"), left: (x - d, y, "face"), right: (x + d, y, "face"),
            bottom: (x, y + d, "face")}


SNES_COLORS = {"X": "#3b4fb8", "Y": "#2e9b4f", "A": "#c8323c", "B": "#d6b52a"}
PS_COLORS = {"Triangle": "#3fae8e", "Circle": "#d2454f", "Cross": "#5a7fd6", "Square": "#c86fae"}
SELECT_START = {"Select": (440, 330, "small"), "Start": (560, 330, "small")}

PICTURES: dict[str, Picture] = {
    "nes": Picture("rect", {"B": (690, 330, "face"), "A": (800, 330, "face"),
                            "Turbo B": (690, 220, "small"), "Turbo A": (800, 220, "small"), **SELECT_START},
                   colors={"A": "#c8323c", "B": "#c8323c"}),
    "snes": Picture("pad", {**_face("X", "Y", "A", "B"), "L": (250, 105, "shoulder"),
                            "R": (750, 105, "shoulder"), **SELECT_START}, colors=SNES_COLORS),
    # three grips: the D-pad on the left one, the stick on the middle one (Z behind it), A, B
    # and the four yellow C buttons on the right
    "n64": Picture("n64", {"A": (675, 345, "big"), "B": (600, 285, "face"),
                           "C-Left": (750, 255, "c"), "C-Down": (805, 308, "c"),
                           "C-buttons (stick)": (835, 395, "small"), "Start": (500, 235, "face"),
                           "Z": (500, 510, "small"), "L": (215, 95, "shoulder"), "R": (785, 95, "shoulder")},
                   dpad=(215, 250), sticks=((500, 380),),
                   colors={"A": "#3b5fd0", "B": "#2e9b4f", "C-Left": "#d6b52a", "C-Down": "#d6b52a",
                           "Start": "#c8323c"},
                   decor=(("dot", 805, 202, 25, "#d6b52a", "C▲"), ("dot", 860, 255, 25, "#d6b52a", "C▶"))),
    "gb": Picture("portrait", {"B": (575, 400, "face"), "A": (655, 355, "face"),
                               "Select": (450, 480, "small"), "Start": (555, 480, "small")},
                  dpad=(410, 385), screen=(370, 60, 260, 230), colors={"A": "#a3245a", "B": "#a3245a"}),
    "gba": Picture("landscape", {"B": (745, 300, "face"), "A": (825, 250, "face"), "L": (190, 95, "shoulder"),
                                 "R": (810, 95, "shoulder"), "Select": (200, 440, "small"),
                                 "Start": (200, 390, "small")},
                   dpad=(200, 265), screen=(330, 150, 340, 240)),
    "nds": Picture("landscape", {**_face("X", "Y", "A", "B", 800, 270, 60), "L": (190, 95, "shoulder"),
                                 "R": (810, 95, "shoulder"), "Select": (760, 430, "small"),
                                 "Start": (860, 430, "small"), "Touch / Mic": (500, 450, "small")},
                   dpad=(200, 270), screen=(340, 140, 320, 250)),
    "gc": Picture("pad", {"A": (750, 300, "big"), "B": (665, 360, "face"), "X": (835, 255, "face"),
                          "Y": (730, 215, "face"), "Z": (780, 155, "small"), "L": (230, 100, "shoulder"),
                          "R": (770, 100, "shoulder"), "Start": (500, 290, "face")},
                  dpad=(360, 420), sticks=((250, 280), (640, 420)),
                  colors={"A": "#2fae8a", "B": "#c8323c", "Z": "#6a4fc8", "Start": "#555b6e"}),
    "mastersystem": Picture("rect", {"1": (700, 320, "face"), "2": (800, 320, "face"),
                                     "Pause": (500, 330, "small")}),
    "megadrive": Picture("pad", {"A": (650, 345, "face"), "B": (740, 315, "face"), "C": (830, 285, "face"),
                                 "X": (630, 250, "c"), "Y": (720, 220, "c"), "Z": (810, 190, "c"),
                                 "Mode": (780, 105, "small"), "Start": (500, 300, "small")}),
    "gamegear": Picture("landscape", {"1": (760, 310, "face"), "2": (845, 265, "face"),
                                      "Start": (830, 170, "small")},
                        dpad=(200, 290), screen=(330, 130, 340, 260)),
    "saturn": Picture("pad", {"A": (650, 345, "face"), "B": (740, 315, "face"), "C": (830, 285, "face"),
                              "X": (630, 250, "c"), "Y": (720, 220, "c"), "Z": (810, 190, "c"),
                              "L": (250, 105, "shoulder"), "R": (750, 105, "shoulder"),
                              "Start": (500, 330, "small")}),
    "dreamcast": Picture("pad", {**_face("Y", "X", "B", "A"), "L trigger": (250, 105, "shoulder"),
                                 "R trigger": (750, 105, "shoulder"), "Start": (500, 420, "small")},
                         dpad=(250, 380), sticks=((260, 230),),
                         colors={"A": "#c8323c", "B": "#3b5fd0", "X": "#d6b52a", "Y": "#2e9b4f"}),
    # the first PlayStation pad: no sticks - the DualShock 2 below has them (and L3 / R3)
    "psx": Picture("psx", {"Triangle": (760, 200, "face"), "Square": (690, 270, "face"),
                                 "Circle": (830, 270, "face"), "Cross": (760, 340, "face"),
                                 "L1": (230, 105, "shoulder"), "R1": (770, 105, "shoulder"),
                                 "L2": (230, 48, "shoulder"), "R2": (770, 48, "shoulder"),
                                 "Select": (440, 300, "small"), "Start": (560, 300, "small")},
                   dpad=(235, 270), colors=PS_COLORS, split_dpad=True,
                   decor=(("well", 235, 270, 105), ("well", 760, 270, 108))),
    "ps2": Picture("dualshock", {"Triangle": (760, 200, "face"), "Square": (690, 270, "face"),
                                 "Circle": (830, 270, "face"), "Cross": (760, 340, "face"),
                                 "L1": (230, 105, "shoulder"), "R1": (770, 105, "shoulder"),
                                 "L2": (230, 48, "shoulder"), "R2": (770, 48, "shoulder"),
                                 "L3": (370, 400, "face"), "R3": (630, 400, "face"),
                                 "Select": (440, 270, "small"), "Start": (560, 270, "small")},
                   dpad=(235, 270), sticks=((370, 400), (630, 400)), colors=PS_COLORS, split_dpad=True,
                   decor=(("well", 235, 270, 105), ("well", 760, 270, 108), ("led", 500, 330, 9, "#c8323c"))),
    "psp": Picture("landscape", {**_face("Triangle", "Square", "Circle", "Cross", 800, 270, 62),
                                 "L": (190, 95, "shoulder"), "R": (810, 95, "shoulder"),
                                 "Select": (560, 450, "small"), "Start": (680, 450, "small")},
                   dpad=(200, 260), sticks=((200, 410),), screen=(330, 140, 340, 260), colors=PS_COLORS),
    "pce": Picture("rect", {"II": (690, 330, "face"), "I": (800, 330, "face"), "Select": (440, 330, "small"),
                            "Run": (560, 330, "small")}),
    "atari2600": Picture("stick", {"Fire": (380, 170, "big"), "Select": (420, 480, "small"),
                                   "Reset": (580, 480, "small")}, dpad=None, sticks=((540, 300),),
                         colors={"Fire": "#c8323c"}),
    "arcade": Picture("panel", {"Button 1": (560, 280, "face"), "Button 2": (660, 255, "face"),
                                "Button 3": (760, 255, "face"), "Button 4": (560, 380, "face"),
                                "Button 5": (660, 355, "face"), "Button 6": (760, 355, "face"),
                                "Coin": (170, 200, "small"), "Start": (310, 200, "small")},
                      dpad=None, sticks=((240, 340),),
                      colors={f"Button {i}": c for i, c in enumerate(
                          ("#c8323c", "#d6b52a", "#2e9b4f", "#3b5fd0", "#c86fae", "#e08a2e"), 1)}),
}
PICTURES["3ds"] = Picture("landscape", {**_face("X", "Y", "A", "B", 800, 270, 60), "L": (190, 95, "shoulder"),
                                         "ZL": (310, 95, "small"), "R": (810, 95, "shoulder"),
                                         "ZR": (690, 95, "small"), "Select": (760, 430, "small"),
                                         "Start": (860, 430, "small")},
                          dpad=(200, 340), sticks=((200, 210),), screen=(340, 140, 320, 250))
# the Wii Remote, the Nunchuk's C and Z beside it
PICTURES["wii"] = Picture("rect", {"A": (690, 300, "big"), "B": (800, 230, "face"), "1": (690, 410, "face"),
                                   "2": (800, 410, "face"), "−": (430, 330, "small"), "Home": (500, 380, "small"),
                                   "+": (570, 330, "small"), "C": (620, 160, "small"), "Z": (730, 160, "small"),
                                   "Shake Wii Remote": (840, 130, "small"), "Shake Nunchuk": (160, 130, "small")},
                          dpad=(230, 300), sticks=((230, 450),),
                          colors={"A": "#8a93a8", "B": "#8a93a8"})
# the Wii U GamePad: a screen between the sticks
PICTURES["wiiu"] = Picture("landscape", {**_face("X", "Y", "A", "B", 820, 300, 55), "L": (190, 95, "shoulder"),
                                         "ZL": (310, 95, "small"), "R": (810, 95, "shoulder"),
                                         "ZR": (690, 95, "small"), "−": (700, 450, "small"),
                                         "+": (790, 450, "small"), "L3": (120, 450, "small"),
                                         "R3": (880, 450, "small")},
                           dpad=(180, 330), sticks=((180, 200), (820, 170)), screen=(330, 130, 340, 260))
PICTURES["gbc"] = PICTURES["gb"]
PICTURES["segacd"] = PICTURES["megadrive"]
GENERIC = Picture("pad", {**_face("X", "Y", "A", "B"), "L": (250, 115, "shoulder"), "R": (750, 115, "shoulder"),
                          "L2": (250, 55, "shoulder"), "R2": (750, 55, "shoulder"), "L3": (390, 440, "face"),
                          "R3": (610, 440, "face"), **SELECT_START})
SHORT_TEXT = {"C-Left": "C◀", "C-Down": "C▼", "Up": "▲", "Down": "▼", "Left": "◀", "Right": "▶", "Triangle": "△", "Circle": "○", "Square": "□", "Cross": "✕", "C-buttons (stick)": "C-stick",
              "Touch / Mic": "Touch", "Shake Wii Remote": "Shake", "Shake Nunchuk": "Shake N", "L trigger": "L", "R trigger": "R", "Turbo B": "Turbo B",
              **{f"Button {i}": str(i) for i in range(1, 7)}}


def dpad_buttons(pic: Picture) -> dict[str, tuple[int, int, str]]:
    """The four directions on the D-pad (or the stick, without one)."""
    x, y = pic.dpad or pic.sticks[0]
    return {"Up": (x, y - 50, "dir"), "Down": (x, y + 50, "dir"), "Left": (x - 50, y, "dir"),
            "Right": (x + 50, y, "dir")}


def picture(system_id: str) -> Picture:
    from dataclasses import replace

    pic = PICTURES.get(system_id, GENERIC)
    return replace(pic, buttons={**dpad_buttons(pic), **pic.buttons})


def button_text(name: str) -> str:
    return SHORT_TEXT.get(name, name)


def _body(shape: str) -> QPainterPath:
    """The outline: the parts united into one shape."""
    parts: list[QPainterPath] = []

    def rounded(x, y, w, h, r):
        part = QPainterPath()
        part.addRoundedRect(QRectF(x, y, w, h), r, r)
        parts.append(part)

    def rotated(cx, cy, w, h, r, degrees):
        """A rounded upright part around its centre, turned (the grips spread outwards)."""
        part = QPainterPath()
        part.addRoundedRect(QRectF(-w / 2, -h / 2, w, h), r, r)
        parts.append(QTransform().translate(cx, cy).rotate(degrees).map(part))

    def circle(x, y, r):
        part = QPainterPath()
        part.addEllipse(QPointF(x, y), r, r)
        parts.append(part)

    if shape == "pad":  # two grips joined in the middle
        rounded(170, 140, 660, 260, 120)
        circle(250, 320, 175)
        circle(750, 320, 175)
    elif shape == "rect":
        rounded(110, 160, 780, 300, 30)
    elif shape == "n64":
        top = QPainterPath()
        top.addEllipse(QPointF(500, 255), 435, 150)
        parts.append(top)
        rounded(110, 150, 780, 200, 90)
        rotated(205, 400, 175, 300, 85, 10)
        rotated(795, 400, 175, 300, 85, -10)
        rounded(410, 300, 180, 250, 90)
    elif shape in ("dualshock", "psx"):  # the front with the two long grips (DualShock: the sticks between)
        rounded(125, 140, 750, 240, 110)
        if shape == "dualshock":
            rounded(285, 290, 430, 200, 90)
        rotated(210, 375, 190, 345, 95, 17)
        rotated(790, 375, 190, 345, 95, -17)
    elif shape == "trident":
        rounded(90, 130, 820, 230, 110)
        for x in (220, 500, 780):
            rounded(x - 95, 200, 190, 330, 90)
    elif shape == "portrait":
        rounded(320, 20, 360, 530, 40)
    elif shape == "landscape":
        rounded(80, 110, 840, 400, 150)
    elif shape == "stick":
        rounded(300, 110, 400, 420, 40)
    elif shape == "panel":
        rounded(70, 140, 860, 330, 24)
    body = QPainterPath()
    for part in parts:
        body = body.united(part)
    return body


def paint(painter: QPainter, pic: Picture, body: str = theme.SURFACE_HI, outline: str = theme.TEXT_DIM) -> None:
    """The controller's body, D-pad, sticks and screen (the buttons are widgets)."""
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(QPen(QColor(outline), 3))
    painter.setBrush(QColor(body))
    painter.drawPath(_body(pic.body))
    painter.setPen(Qt.PenStyle.NoPen)
    for item in pic.decor:
        if item[0] == "well":
            _kind, x, y, r = item
            painter.setBrush(QColor(0, 0, 0, 55))
            painter.drawEllipse(QPointF(x, y), r, r)
    if pic.screen:
        x, y, w, h = pic.screen
        painter.setBrush(QColor("#0b0d12"))
        painter.drawRoundedRect(QRectF(x, y, w, h), 14, 14)
        painter.setBrush(QColor("#2b3a2e"))
        painter.drawRect(QRectF(x + 20, y + 20, w - 40, h - 40))
    painter.setBrush(QColor("#11141b"))
    if pic.dpad and pic.split_dpad:
        x, y = pic.dpad
        for ax, ay in ((0, -1), (0, 1), (-1, 0), (1, 0)):
            w, h = (50, 62) if ax == 0 else (62, 50)
            cx, cy = x + ax * 52, y + ay * 52
            painter.drawRoundedRect(QRectF(cx - w / 2, cy - h / 2, w, h), 10, 10)
    elif pic.dpad:
        x, y = pic.dpad
        painter.drawRoundedRect(QRectF(x - 75, y - 25, 150, 50), 8, 8)
        painter.drawRoundedRect(QRectF(x - 25, y - 75, 50, 150), 8, 8)
    for x, y in pic.sticks:
        painter.setBrush(QColor("#11141b"))
        painter.drawEllipse(QPointF(x, y), 58, 58)
        painter.setBrush(QColor(theme.SURFACE))
        painter.drawEllipse(QPointF(x, y), 38, 38)
    for item in pic.decor:
        if item[0] in ("dot", "led"):
            _kind, x, y, r, color, *text = item
            painter.setBrush(QColor(color))
            painter.drawEllipse(QPointF(x, y), r, r)
            if text:  # as the buttons write it (e.g. "C▲")
                font = painter.font()
                font.setPixelSize(int(r * 0.85))
                font.setBold(True)
                painter.setFont(font)
                painter.setPen(QColor(theme.TEXT))
                painter.drawText(QRectF(x - r, y - r, 2 * r, 2 * r), Qt.AlignmentFlag.AlignCenter, text[0])
                painter.setPen(Qt.PenStyle.NoPen)
