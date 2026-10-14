import pytest
from PySide6.QtCore import QPointF, Qt

from gamingcrypt.ui.lock_screen import LockScreen
from gamingcrypt.ui.secret_input import PatternWidget, PinPad, between_node
from gamingcrypt.ui.widgets import OnScreenKeyboard
from gamingcrypt.unlock.veracrypt import UnlockResult


class FakeUnlocker:
    def __init__(self, correct="1234", configured=True):
        self.correct = correct
        self.configured = configured
        self.attempts = []

    def unlock(self, secret):
        self.attempts.append(secret)
        if secret == self.correct:
            return UnlockResult(True, "Unlocked")
        return UnlockResult(False, "Wrong code - please try again")


def test_pinpad_typing_and_submit(qtbot):
    pad = PinPad()
    qtbot.addWidget(pad)
    for key in "12⌫34":
        pad.press(key)
    with qtbot.waitSignal(pad.submitted) as blocker:
        pad.press("✓")
    assert blocker.args == ["134"]


@pytest.mark.parametrize("a,b,mid", [(0, 2, 1), (0, 8, 4), (2, 6, 4), (0, 6, 3), (0, 1, None), (0, 5, None)])
def test_between_node(a, b, mid):
    assert between_node(a, b) == mid


def test_pattern_add_node_fills_skipped_dots():
    w = PatternWidget()
    w.add_node(0)
    w.add_node(2)
    w.add_node(2)
    assert w.nodes == [0, 1, 2]


def test_pattern_drag_emits_nodes(qtbot):
    w = PatternWidget()
    qtbot.addWidget(w)
    w.resize(300, 300)
    w.show()
    points = [w.node_center(i).toPoint() for i in (0, 3, 6, 7)]
    with qtbot.waitSignal(w.pattern_entered) as blocker:
        qtbot.mousePress(w, Qt.MouseButton.LeftButton, pos=points[0])
        for p in points[1:]:
            qtbot.mouseMove(w, p)
            # offscreen mouseMove doesn't carry button state; feed the widget directly
            w._track(QPointF(p))
        qtbot.mouseRelease(w, Qt.MouseButton.LeftButton, pos=points[-1])
    assert blocker.args == [[0, 3, 6, 7]]


def test_keyboard_types_into_target(qtbot):
    from PySide6.QtWidgets import QLineEdit

    edit = QLineEdit()
    kb = OnScreenKeyboard(edit)
    qtbot.addWidget(kb)
    kb.toggle_shift()
    assert "Q" in kb.key_labels()
    kb.type_text("Q")  # shift resets after one letter
    assert "q" in kb.key_labels()
    kb.type_text("w")
    kb.toggle_symbols()
    kb.type_text("!")
    kb.backspace()
    kb.type_text("?")
    assert edit.text() == "Qw?"
    with qtbot.waitSignal(kb.submitted):
        kb.submitted.emit()


def test_lock_screen_correct_pin_unlocks(qtbot):
    unlocker = FakeUnlocker("4711")
    screen = LockScreen(unlocker, "pin")
    qtbot.addWidget(screen)
    with qtbot.waitSignal(screen.unlocked, timeout=3000):
        for key in "4711✓":
            screen.input.widget.press(key)
    assert unlocker.attempts == ["4711"]


def test_lock_screen_wrong_pin_shows_error(qtbot):
    unlocker = FakeUnlocker("4711")
    screen = LockScreen(unlocker, "pin")
    qtbot.addWidget(screen)
    for key in "0000✓":
        screen.input.widget.press(key)
    qtbot.waitUntil(lambda: not screen.busy)
    assert "Wrong code" in screen.status.text()
    assert screen.input.widget.display.text() == ""


def test_lock_screen_short_pin_is_rejected_without_calling_veracrypt(qtbot):
    unlocker = FakeUnlocker()
    screen = LockScreen(unlocker, "pin")
    qtbot.addWidget(screen)
    for key in "12✓":
        screen.input.widget.press(key)
    assert unlocker.attempts == []
    assert "at least" in screen.status.text()


def test_lock_screen_password(qtbot):
    unlocker = FakeUnlocker("secret")
    screen = LockScreen(unlocker, "password")
    qtbot.addWidget(screen)
    screen.input.widget.edit.setText("nope")
    screen.input.widget.keyboard.submitted.emit()
    qtbot.waitUntil(lambda: not screen.busy)
    assert unlocker.attempts == ["nope"]
    screen.input.widget.edit.setText("secret")
    with qtbot.waitSignal(screen.unlocked, timeout=3000):
        screen.input.widget.keyboard.submitted.emit()


def test_lock_screen_pattern(qtbot):
    unlocker = FakeUnlocker("14789")
    screen = LockScreen(unlocker, "pattern")
    qtbot.addWidget(screen)
    with qtbot.waitSignal(screen.unlocked, timeout=3000):
        screen.input.widget.pattern_entered.emit([0, 3, 6, 7, 8])


def test_lock_screen_unknown_method_falls_back_to_password(qtbot):
    screen = LockScreen(FakeUnlocker(), "bogus")
    qtbot.addWidget(screen)
    assert screen.method == "password"


def test_lock_screen_unconfigured_allows_skip(qtbot):
    screen = LockScreen(FakeUnlocker(configured=False), "pin")
    qtbot.addWidget(screen)
    assert not screen.skip_button.isHidden()
    with qtbot.waitSignal(screen.unlocked):
        screen.skip_button.click()


def test_dot_grid_taps_in_order(qtbot):
    from gamingcrypt.ui.secret_input import DotGridPad

    pad = DotGridPad()
    qtbot.addWidget(pad)
    pad.resize(500, 600)
    pad.show()
    for index in (0, 24, 24, 12):
        qtbot.mouseClick(pad.canvas, Qt.MouseButton.LeftButton, pos=pad.canvas.node_center(index).toPoint())
    assert pad.nodes == [0, 24, 24, 12]
    assert pad.display.text() == "●●●●"  # order is not revealed
    pad.backspace()
    pad.press(6)
    with qtbot.waitSignal(pad.submitted) as blocker:
        pad.ok_button.click()
    assert blocker.args == [[0, 24, 24, 6]]


def test_dot_grid_tap_between_dots_is_ignored(qtbot):
    from gamingcrypt.ui.secret_input import DotGridPad

    pad = DotGridPad()
    qtbot.addWidget(pad)
    pad.resize(500, 600)
    pad.show()
    a, b = pad.canvas.node_center(0), pad.canvas.node_center(6)
    assert pad.canvas.node_at(QPointF((a.x() + b.x()) / 2, (a.y() + b.y()) / 2)) is None


def test_lock_screen_dot_grid_unlocks(qtbot):
    unlocker = FakeUnlocker("1-7-13-25")
    screen = LockScreen(unlocker, "grid5")
    qtbot.addWidget(screen)
    assert "5×5" in screen.subtitle.text()
    pad = screen.input.widget
    for index in (0, 6, 12, 24):
        pad.press(index)
    with qtbot.waitSignal(screen.unlocked, timeout=3000):
        pad.ok_button.click()


def test_lock_screen_dot_grid_too_short(qtbot):
    unlocker = FakeUnlocker()
    screen = LockScreen(unlocker, "grid5")
    qtbot.addWidget(screen)
    screen.input.widget.press(3)
    screen.input.widget.ok_button.click()
    assert unlocker.attempts == [] and "at least" in screen.status.text()
    assert screen.input.widget.nodes == []


def test_dot_grid_buttons_keep_away_from_the_dots(qtbot):
    """⌫ / ✓ used to sit right under the last row and caught taps meant for those dots."""
    from gamingcrypt.ui import theme
    from gamingcrypt.ui.secret_input import DotGridPad

    pad = DotGridPad()
    pad.setStyleSheet(theme.STYLESHEET)
    qtbot.addWidget(pad)
    pad.resize(1280, 480)  # what's left on an 800 px high screen
    pad.show()
    qtbot.waitExposed(pad)
    canvas = pad.canvas
    dots = [canvas.mapTo(pad, canvas.node_center(i).toPoint()) for i in range(25)]
    radius = canvas._cell() * 0.3
    for button in (pad.back_button, pad.ok_button):
        rect = button.geometry()
        for dot in dots:
            dx = max(rect.left() - dot.x(), 0, dot.x() - rect.right())
            dy = max(rect.top() - dot.y(), 0, dot.y() - rect.bottom())
            assert (dx * dx + dy * dy) ** 0.5 - radius >= 40, (button.text(), dot)
    assert pad.back_button.x() < dots[0].x() < dots[4].x() < pad.ok_button.x()  # left / right of the grid


def test_dot_grid_with_the_controller_buttons(qtbot):
    """X takes the last dot back, B enters - with nothing entered B is back."""
    from gamingcrypt.input import evdev as e
    from gamingcrypt.ui.navigator import GamepadNavigator
    from gamingcrypt.ui.secret_input import DotGridPad

    from PySide6.QtWidgets import QVBoxLayout, QWidget

    backs = []
    window = QWidget()
    host = DotGridPad()
    QVBoxLayout(window).addWidget(host)
    window.resize(700, 600)
    qtbot.addWidget(window)
    window.show()
    window.gamepad_back = lambda: backs.append(True) or True  # what B does elsewhere
    nav = GamepadNavigator(window)
    nav.focus(host.canvas)
    press = lambda code: (nav.on_event(e.EV_KEY, code, 1), nav.on_event(e.EV_KEY, code, 0))  # noqa: E731
    press(e.BTN_EAST)
    assert backs == [True]  # nothing entered: back as everywhere
    for _ in range(3):
        press(e.BTN_SOUTH)
    assert len(host.nodes) == 3
    press(e.BTN_NORTH)  # X (xpad layout: the left button)
    assert len(host.nodes) == 2 and host.display.text() == "●●"
    with qtbot.waitSignal(host.submitted) as blocker:
        press(e.BTN_EAST)
    assert len(blocker.args[0]) == 2 and backs == [True]


def test_the_lock_screen_shows_the_controller_buttons_of_the_dots(qtbot):
    from PySide6.QtWidgets import QMainWindow

    from gamingcrypt.ui import theme
    from gamingcrypt.users import User

    window = QMainWindow()
    window.setStyleSheet(theme.STYLESHEET)
    qtbot.addWidget(window)
    window.resize(1280, 800)
    people = [User("admin", "admin", "grid5", admin=True), User("u1", "Mia", "grid5")]
    screen = LockScreen(FakeUnlocker(), "grid5", users=people, unlocker_for=lambda u: FakeUnlocker())
    window.setCentralWidget(screen)
    window.show()
    qtbot.waitExposed(window)
    qtbot.wait(50)
    pad = screen.input.widget
    assert pad.hint.isVisible() and "Ⓧ  Take the last one back" in pad.hint.text() and "Ⓑ  Enter" in pad.hint.text()
    bottom = lambda w: w.mapTo(window, w.rect().bottomLeft()).y()  # noqa: E731
    assert bottom(pad.hint) < bottom(screen.shutdown_button) <= 800  # all on the screen
    assert bottom(pad.canvas) < pad.hint.mapTo(window, pad.hint.rect().topLeft()).y()  # below the dots
    pin = LockScreen(FakeUnlocker(), "pin")
    qtbot.addWidget(pin)
    from gamingcrypt.ui.secret_input import DotGridPad

    elsewhere = DotGridPad()  # e.g. setting a code
    qtbot.addWidget(elsewhere)
    assert elsewhere.hint.isHidden()
