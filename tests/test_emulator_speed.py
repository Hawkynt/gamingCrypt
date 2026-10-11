"""Running speed of RetroArch games (0.1x - 10x): the quick menu's slider."""

import copy

import pytest

from gamingcrypt.config import DEFAULTS
from gamingcrypt.emulation import retroarch
from gamingcrypt.emulation.library import EmulationPaths, scan
from gamingcrypt.emulation.systems import BY_ID


def test_speed_settings():
    assert retroarch.SLOW_SPEEDS[0] == 0.1 and retroarch.FAST_SPEEDS[-1] == 10.0
    assert retroarch.speed_settings(3.0, 0.25) == {"fastforward_ratio": "3", "slowmotion_ratio": "4"}
    assert retroarch.speed_settings(10.0, 0.1) == {"fastforward_ratio": "10", "slowmotion_ratio": "10"}


def test_the_sliders_speeds():
    assert retroarch.SPEEDS[0] == 0.1 and retroarch.SPEEDS[-1] == 10.0 and 1.0 in retroarch.SPEEDS
    assert list(retroarch.SPEEDS) == sorted(retroarch.SPEEDS)
    assert retroarch.SLOW_SPEEDS + (1.0,) + retroarch.FAST_SPEEDS == retroarch.SPEEDS
    assert [retroarch.mode_of(s) for s in (0.25, 1.0, 3.0)] == ["slow", "normal", "fast"]


def test_mode_commands():
    assert retroarch.mode_commands("normal", "fast") == ["FAST_FORWARD"]
    assert retroarch.mode_commands("fast", "normal") == ["FAST_FORWARD"]
    assert retroarch.mode_commands("normal", "slow") == ["SLOWMOTION"]
    assert retroarch.mode_commands("slow", "fast") == ["SLOWMOTION", "FAST_FORWARD"]
    assert retroarch.mode_commands("fast", "fast") == []


def test_launch_writes_the_rates(tmp_path):
    paths = EmulationPaths(tmp_path / "Emulation")
    paths.ensure()
    (paths.cores / "snes9x_libretro.so").write_text("x")
    (paths.roms / "snes" / "Mario.sfc").write_text("x")
    game = scan(paths, BY_ID["snes"])[0]
    ok, _ = retroarch.launch(game, paths, tmp_path / "d", tmp_path / "l", popen=lambda cmd, **k: None,
                             which=lambda n: "/usr/bin/retroarch", fast=4.0, slow=0.25)
    config = (paths.config / "gamingcrypt.cfg").read_text()
    assert ok and 'fastforward_ratio = "4"' in config and 'slowmotion_ratio = "4"' in config


@pytest.fixture
def window(qtbot, tmp_path, monkeypatch):
    from gamingcrypt.app import MainWindow
    from gamingcrypt.ui.games_tab import GamesTab
    from tests.fakes import FakeService

    paths = EmulationPaths(tmp_path / "Emulation")
    paths.ensure()
    (paths.roms / "snes" / "Super Mario World.sfc").write_text("x")
    launches, sent = [], []
    monkeypatch.setattr(retroarch, "launch", lambda game, *a, **k: launches.append(
        (game.name, k.get("fast"), k.get("slow"))) or (True, "Starting"))
    monkeypatch.setattr(retroarch, "send", lambda text, port=None: sent.append(text) or True)
    pages = {}

    def factory(cfg):
        pages["Games"] = GamesTab(FakeService(), library_settings=cfg["libraries"], emulation_root=str(paths.root))
        return dict(pages)

    w = MainWindow(copy.deepcopy(DEFAULTS), lambda c: None, page_factory=factory)
    qtbot.addWidget(w)
    w.windowed = True
    w.show()
    w.show_shell()
    games = pages["Games"]
    qtbot.waitUntil(lambda: "snes" in games.home.system_cards)
    w._launches, w._sent, w._game, w._paths = launches, sent, scan(paths, BY_ID["snes"])[0], paths
    return w


def toasts(window):
    return window.toasts.shown + [x[1] for x in window.toasts.queue]


def playing(window):
    window.launch_rom(window._game)
    window.game_watcher.phase = "playing"
    window.toggle_quick_menu()
    return window.quick_menu


def test_normal_and_the_started_rates_are_instant(qtbot, window):
    menu = playing(window)
    assert window._launches == [("Super Mario World", 2.0, 0.5)]  # the defaults
    assert menu.speed_row.isVisibleTo(menu) and menu.speed_value.text() == "1x"
    window.set_speed(2.0)
    assert window._sent == ["FAST_FORWARD"] and window.speed == 2.0  # right away, no restart
    window.set_speed(0.5)
    assert window._sent == ["FAST_FORWARD", "FAST_FORWARD", "SLOWMOTION"]
    menu.close_menu()
    window.toggle_quick_menu()
    assert menu.speed_value.text() == "0.5x"  # still slow
    window.set_speed(1.0)
    assert window._sent[-1] == "SLOWMOTION" and window.speed == 1.0
    assert len(window._launches) == 1 and "fast_speed" not in window.game_profiles.get(window._game.appid)


def test_the_slider_sets_the_speed(qtbot, window, monkeypatch):
    from gamingcrypt.ui import quick_menu

    monkeypatch.setattr(quick_menu, "SPEED_SETTLE_MS", 10)
    menu = playing(window)
    menu.speed.setValue(retroarch.SPEEDS.index(2.0))
    qtbot.waitUntil(lambda: window._sent == ["FAST_FORWARD"])
    assert menu.isVisible()


def fake_retroarch(window, monkeypatch, saves=True, comes_back=True):
    """RetroArch for a change of speed: it saves into its slot 0, can be stopped and asked how it is."""
    from gamingcrypt.steam import running

    paths, stopped = window._paths, []

    def send(text, port=None):
        window._sent.append(text)
        if text == "SAVE_STATE" and saves:
            (paths.states / "Super Mario World.state").write_text("where I was")
        return True

    monkeypatch.setattr(retroarch, "send", send)
    monkeypatch.setattr(retroarch, "playing", lambda *a, **k: comes_back)
    monkeypatch.setattr(running, "force_quit", lambda appid, **k: stopped.append(appid) or 1)
    monkeypatch.setattr("time.sleep", lambda s: None)
    return stopped


def test_another_rate_starts_retroarch_again_where_the_game_was(qtbot, window, monkeypatch):
    """RetroArch reads its rates only at its start: save, start again with the rate, load, go on fast."""
    from gamingcrypt.emulation import savestates

    stopped = fake_retroarch(window, monkeypatch)
    game = window._game
    (window._paths.states / "Super Mario World.state").write_text("my own state")
    menu = playing(window)
    watched = []
    monkeypatch.setattr(window.game_watcher, "watch", lambda *a, **k: watched.append(a))
    window.set_speed(5.0)
    assert not menu.speed.isEnabled() and "5x" in menu.status.text() and menu.speed_value.text() == "5x"
    window.set_speed(8.0)  # one at a time
    qtbot.waitUntil(lambda: getattr(window, "speed", 1.0) == 5.0 and menu.speed.isEnabled(), timeout=8000)
    assert stopped == [game.appid] and window._launches == [("Super Mario World", 2.0, 0.5),
                                                            ("Super Mario World", 5.0, 0.5)]
    assert window._sent == ["SAVE_STATE", f"LOAD_STATE_SLOT {savestates.SPARE}", "FAST_FORWARD"]
    assert watched == [] and window.game_watcher.appid == game.appid  # the same game went on: no new loading screen
    assert menu.status.text() == "" and window.speed_mode == "fast"
    slots = savestates.slots(window._paths, game)
    assert slots[0].path.read_text() == "my own state" and sum(not s.empty for s in slots) == 1  # the slots untouched
    window.set_speed(1.0)
    window.set_speed(5.0)  # that's its rate now: instant
    assert window._sent[-2:] == ["FAST_FORWARD", "FAST_FORWARD"] and len(window._launches) == 2


def test_the_rate_is_remembered_for_the_next_start(qtbot, window, monkeypatch):
    fake_retroarch(window, monkeypatch)
    playing(window)
    window.set_speed(0.25)
    qtbot.waitUntil(lambda: getattr(window, "speed", 1.0) == 0.25, timeout=8000)
    assert window._sent[-1] == "SLOWMOTION" and window.speed_rates(window._game) == (2.0, 0.25)
    window.game_over(window._game.appid)
    window.game_watcher._stop()
    window.launch_rom(window._game)
    assert window._launches[-1] == ("Super Mario World", 2.0, 0.25) and window.speed == 1.0  # starts at normal speed


def test_a_game_without_save_states_keeps_running(qtbot, window, monkeypatch):
    stopped = fake_retroarch(window, monkeypatch, saves=False)
    monkeypatch.setattr("gamingcrypt.emulation.savestates.capture", lambda *a, **k: False)
    menu = playing(window)
    window.set_speed(4.0)
    qtbot.waitUntil(lambda: any("4x from the next start" in t for t in toasts(window)), timeout=8000)
    assert stopped == [] and len(window._launches) == 1 and window.speed == 1.0
    assert menu.speed.isEnabled() and menu.speed_value.text() == "1x"
    assert window.speed_rates(window._game) == (4.0, 0.5)


def test_a_game_that_does_not_come_back_keeps_its_state(qtbot, window, monkeypatch):
    from gamingcrypt.emulation import savestates

    fake_retroarch(window, monkeypatch, comes_back=False)
    clock = iter(range(0, 100000, 30))
    monkeypatch.setattr("time.monotonic", lambda: next(clock))
    playing(window)
    window.set_speed(4.0)
    qtbot.waitUntil(lambda: any("slot 1 of Load state" in t for t in toasts(window)), timeout=8000)
    assert savestates.slots(window._paths, window._game)[0].path.read_text() == "where I was"
    assert window.speed == 1.0 and window.quick_menu.speed.isEnabled()


def test_no_speeds_to_choose_on_the_game_page(qtbot, window):
    from gamingcrypt.ui.emulation_pages import RomGamePage

    page = RomGamePage(window.shell.pages["Games"], window._game)
    qtbot.addWidget(page)
    assert not hasattr(page, "speed_combos")  # the quick menu's slider is all there is
