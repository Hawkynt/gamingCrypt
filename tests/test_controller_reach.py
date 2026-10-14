"""Controller only: every control on every Settings page can be reached with the D-pad."""

import copy

import pytest
from PySide6.QtWidgets import QMainWindow

from gamingcrypt.ui.navigator import GamepadNavigator


def reachable(nav, start):
    seen, todo = {start}, [start]
    while todo:
        w = todo.pop()
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nav.focus(w)
            nav.move(dx, dy)
            target = nav.focused()
            if target is not None and target not in seen:
                seen.add(target)
                todo.append(target)
    return seen


def describe(w):
    text = w.text() if hasattr(w, "text") and callable(w.text) else ""
    return f"{type(w).__name__}({text!r}, {w.objectName()!r}) in {type(w.parentWidget()).__name__}"


@pytest.fixture
def settings(qtbot, monkeypatch):
    from gamingcrypt.config import DEFAULTS
    from gamingcrypt.session import mode
    from gamingcrypt.system.controls import SystemControls
    from gamingcrypt.ui import theme
    from gamingcrypt.ui.settings_tab import SettingsTab
    from tests.test_navigation import LongNamesAudio
    from tests.test_system_settings import FakeBrightness
    from tests.test_updater import FakeUpdater

    class Health:
        def run(self):
            return []

    class Info:
        ok, available, message, changes = True, False, "Up to date", []

    monkeypatch.setenv("GAMINGCRYPT_SESSION", "1")
    monkeypatch.setattr(mode, "panel_size", lambda *a: (1280, 800))
    window = QMainWindow()
    window.setStyleSheet(theme.STYLESHEET)
    qtbot.addWidget(window)
    window.resize(1280, 800)
    tab = SettingsTab(copy.deepcopy(DEFAULTS), lambda c: None, health=Health(), updater=FakeUpdater(Info()),
                      system=SystemControls(audio=LongNamesAudio(), brightness=FakeBrightness()),
                      restart_gaming=lambda: None)
    window.setCentralWidget(tab)
    window.show()
    qtbot.waitExposed(window)
    return window, tab


@pytest.mark.parametrize("name", ["Device", "Network", "Controller", "Storage", "Games", "Security", "System"])
def test_every_control_of_a_settings_page_can_be_reached(settings, qtbot, name):
    window, tab = settings
    if name not in tab.sub_buttons:
        pytest.skip("no such page")
    tab.show_sub_tab(name)
    qtbot.wait(100)
    nav = GamepadNavigator(window)
    start = tab.sub_buttons[name]
    seen = reachable(nav, start)
    missing = [w for w in nav.candidates() if w not in seen]
    assert not missing, "\n".join(describe(w) for w in missing)


def test_every_settings_control_a_user_sees_can_be_reached(qtbot, monkeypatch):
    from gamingcrypt import users
    from gamingcrypt.ui import theme
    from gamingcrypt.ui.settings_tab import SettingsTab
    from tests.test_users_page import config as admin_config

    cfg = admin_config()
    kim = users.add(cfg, "Kim", "pin", "1111", users.admin_master(cfg, "0000", lambda s: True))
    users.enter(cfg, kim.id)
    window = QMainWindow()
    window.setStyleSheet(theme.STYLESHEET)
    qtbot.addWidget(window)
    window.resize(1280, 800)
    tab = SettingsTab(cfg, lambda c: None)
    window.setCentralWidget(tab)
    window.show()
    qtbot.waitExposed(window)
    for name, button in tab.sub_buttons.items():
        if button.isHidden():
            continue
        tab.show_sub_tab(name)
        qtbot.wait(50)
        nav = GamepadNavigator(window)
        seen = reachable(nav, button)
        missing = [w for w in nav.candidates() if w not in seen]
        assert not missing, name + ":\n" + "\n".join(describe(w) for w in missing)


@pytest.mark.parametrize("emulated", [False, True])
def test_every_control_of_the_quick_menu_can_be_reached(qtbot, emulated):
    from gamingcrypt.system.battery import BatteryState
    from gamingcrypt.system.controls import SystemControls
    from gamingcrypt.system.power import PowerLimit
    from gamingcrypt.ui import theme
    from gamingcrypt.ui.quick_menu import QuickMenu
    from tests.test_navigation import LongNamesAudio
    from tests.test_quick_menu import Brightness

    window = QMainWindow()
    window.setStyleSheet(theme.STYLESHEET)
    qtbot.addWidget(window)
    window.resize(1280, 800)
    window.show()
    menu = QuickMenu(window, SystemControls(audio=LongNamesAudio(), brightness=Brightness()),
                     refresh_get=lambda: 0, refresh_set=lambda hz: True,
                     battery_reader=lambda: BatteryState(64, False, False))
    window.nav_root = lambda: menu
    menu.set_performance(limit=PowerLimit(15, 5, 28, "test"), fps=0, overlay=False, in_game=True)
    if emulated:
        menu.set_emulated(True, speed=1.0)
        menu.set_in_step(True)
    menu.open_menu(620, "Portal 2")
    qtbot.waitExposed(window)
    qtbot.wait(50)
    nav = GamepadNavigator(window)
    seen = reachable(nav, menu.back_button)
    missing = [w for w in nav.candidates() if w not in seen]
    assert not missing, "\n".join(describe(w) for w in missing)


def test_every_control_of_the_games_list_and_a_game_page_can_be_reached(qtbot):
    from gamingcrypt.ui import theme
    from gamingcrypt.ui.games_tab import GamesTab
    from tests.fakes import FakeService

    window = QMainWindow()
    window.setStyleSheet(theme.STYLESHEET)
    qtbot.addWidget(window)
    window.resize(1280, 800)
    service = FakeService()
    tab = GamesTab(service)
    window.setCentralWidget(tab)
    window.show()
    qtbot.waitExposed(window)
    tab.games.update({g.appid: g for g in service.games})
    tab.home.set_installed(service.installed_games())
    qtbot.wait(100)
    nav = GamepadNavigator(window)
    start = nav.nearest(None, 0, 1)
    seen = reachable(nav, start)
    missing = [w for w in nav.candidates() if w not in seen]
    assert not missing, "list:\n" + "\n".join(describe(w) for w in missing)
    for appid in (620, 292030):  # installed / not
        tab.open_game(appid)
        qtbot.wait(100)
        page = tab.currentWidget()
        seen = reachable(nav, page.main_button)
        missing = [w for w in nav.candidates() if w not in seen]
        assert not missing, f"game {appid}:\n" + "\n".join(describe(w) for w in missing)
        tab.gamepad_back()
        qtbot.wait(50)
