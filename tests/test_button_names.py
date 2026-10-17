"""Hints name the buttons of this device: its quick menu and lock buttons (Settings ->
Controller -> Device buttons, different per handheld), what its power button does."""

from gamingcrypt.input import hotkeys
from gamingcrypt.input import evdev as e
from gamingcrypt.ui.tour import TOUR, tour

DECK = hotkeys.CONTROLLER  # a Steam Deck has no Windows key: Guide, and Guide + View
AYA = hotkeys.WINDOWS


def test_a_binding_in_words():
    assert AYA["lock"].how_to() == "hold Windows and press Volume Down"
    assert DECK["lock"].how_to() == "hold Guide and press View"
    assert DECK["quick_menu"].how_to() == "press Guide" and AYA["quick_menu"].parts() == ["Windows"]
    assert hotkeys.Binding(hotkeys.KEY, (e.KEY_VOLUMEUP, 999)).how_to() == "hold Volume Up and press Key 999"
    assert DECK["lock"].describe() == "Guide + View (controller)"  # (Settings shows it as ever)


def test_quick_menu_says_this_devices_lock_buttons(qtbot):
    from PySide6.QtWidgets import QWidget

    from gamingcrypt.system.controls import SystemControls
    from gamingcrypt.ui.quick_menu import QuickMenu

    host = QWidget()
    qtbot.addWidget(host)
    menu = QuickMenu(host, SystemControls(), refresh_get=lambda: 0, refresh_set=lambda hz: True)
    assert menu.lock_hint.text() == "Lock shortcut: hold Windows and press Volume Down"
    menu.set_lock_shortcut(DECK["lock"])
    assert menu.lock_hint.text() == "Lock shortcut: hold Guide and press View" and "Windows" not in menu.lock_hint.text()


def test_hint_bar_names_the_quick_menu_button(qtbot):
    from gamingcrypt.ui.shell import Shell

    shell = Shell(show_hints=True)
    qtbot.addWidget(shell)
    assert "⊞  Quick menu" in shell.hint_bar.text()
    shell.hint_bar.set_quick_menu(DECK["quick_menu"])
    assert "Guide  Quick menu" in shell.hint_bar.text() and "⊞" not in shell.hint_bar.text()
    shell.hint_bar._focus_changed(None, shell.tab_buttons["Games"])  # a new highlight keeps the name
    assert "Guide  Quick menu" in shell.hint_bar.text()


def test_tour_in_the_words_of_the_device():
    deck = tour(DECK["quick_menu"], "menu")
    assert "The Guide button opens the quick menu" in deck[1][2] and "Windows button" not in deck[1][2]
    assert deck[2][2].startswith("The power button opens the power menu")  # the default: no sleep
    assert "puts the device to sleep" not in deck[2][2]
    aya = tour(AYA["quick_menu"], "sleep")
    assert "The Windows button opens the quick menu" in aya[1][2]
    assert aya[2][2].startswith("The power button puts the device to sleep")
    combo = tour(hotkeys.Binding(hotkeys.PAD, (e.BTN_MODE, e.BTN_SOUTH)), "menu")
    assert "Hold Guide and press A to open the quick menu" in combo[1][2]
    assert len(deck) == len(TOUR)


def test_the_app_names_the_buttons_of_a_steam_deck(qtbot, monkeypatch):
    from tests.test_game_running import make_window

    monkeypatch.setattr(hotkeys, "dmi", lambda sys_root=None: ("Valve", "Jupiter"))
    window, service, calls = make_window(qtbot, monkeypatch)
    assert "Guide  Quick menu" in window.shell.hint_bar.text()
    window.toggle_quick_menu()
    assert window.quick_menu.lock_hint.text() == "Lock shortcut: hold Guide and press View"
    window.quick_menu.close_menu()
    hotkeys.save(window.config, "quick_menu", hotkeys.Binding(hotkeys.KEY, (e.KEY_VOLUMEUP,)))
    window.reload_hotkeys()  # changed in Settings -> Device buttons
    assert "Volume Up  Quick menu" in window.shell.hint_bar.text()


def test_overlay_setting_names_the_quick_menu_button(qtbot, monkeypatch):
    import copy

    from gamingcrypt.config import DEFAULTS
    from gamingcrypt.ui.system_settings import OverlayBarSection

    monkeypatch.setattr(hotkeys, "dmi", lambda sys_root=None: ("Valve", "Jupiter"))
    section = OverlayBarSection(copy.deepcopy(DEFAULTS), lambda c: None, write=lambda *a: True)
    qtbot.addWidget(section)
    from PySide6.QtWidgets import QLabel

    texts = " ".join(label.text() for label in section.findChildren(QLabel))
    assert "(Guide → Performance overlay)" in texts and "⊞" not in texts
