"""The screen follows a game's frame rate: 50 Hz PAL games on a 60 Hz screen stuttered
(every fifth frame twice - NFSU2 PAL on the AYANEO)."""

import copy
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from gamingcrypt.config import DEFAULTS
from gamingcrypt.emulation import retroarch
from gamingcrypt.emulation.library import EmulationPaths, scan
from gamingcrypt.emulation.systems import BY_ID

ROOT = Path(__file__).resolve().parent.parent

# as RetroArch writes it (NFSU2 PAL on the handheld)
PAL_LOG = """[INFO] [Core] Geometry: 640x448, Aspect: 1.333, FPS: 59.94, Sample rate: 48000.00 Hz.
[INFO] [Environ] SET_SYSTEM_AV_INFO: 640x448, Aspect: 1.333, FPS: 59.94, Sample rate: 48000.00 Hz.
[libretro INFO] [GameDB] No CRC-specific patch or default patch found
[INFO] [Environ] SET_SYSTEM_AV_INFO: 640x512, Aspect: 1.333, FPS: 50.00, Sample rate: 48000.00 Hz.
[INFO] [Video] Timings deviate too much. Will not adjust. (Target = 60.00 Hz, Game = 50.00 Hz)
"""


def test_content_fps_from_the_log(tmp_path):
    log = tmp_path / "retroarch.log"
    assert retroarch.content_fps(log) is None
    log.write_text("[INFO] [Core] Geometry: 256x224, Aspect: 1.143, FPS: 60.10, Sample rate: 32040.50 Hz.\n")
    assert retroarch.content_fps(log) == 60.10
    log.write_text(PAL_LOG)
    assert retroarch.content_fps(log) == 50.0  # the last one: the game switched to PAL
    assert retroarch.refresh_for(50.0) == 50 and retroarch.refresh_for(49.9) == 50
    assert retroarch.refresh_for(59.94) == 0 and retroarch.refresh_for(None) == 0


def test_launch_logs_verbosely_into_a_fresh_file(tmp_path):
    paths = EmulationPaths(tmp_path / "Emulation")
    paths.ensure()
    (paths.cores / "snes9x_libretro.so").write_text("x")
    (paths.roms / "snes" / "Mario.sfc").write_text("x")
    logs = tmp_path / "logs"
    logs.mkdir()
    (logs / retroarch.LOG_NAME).write_text(PAL_LOG)  # the last game's
    started = []
    retroarch.launch(scan(paths, BY_ID["snes"])[0], paths, tmp_path / "d", logs,
                     popen=lambda cmd, **k: started.append(cmd), which=lambda n: "/usr/bin/retroarch")
    assert "--verbose" in started[0] and (logs / retroarch.LOG_NAME).read_text() == ""


@pytest.fixture
def window(qtbot, tmp_path, monkeypatch):
    from gamingcrypt import config as config_mod
    from gamingcrypt.app import MainWindow
    from gamingcrypt.session import mode
    from gamingcrypt.system import gamescope_ctl
    from gamingcrypt.ui.games_tab import GamesTab
    from tests.fakes import FakeService

    paths = EmulationPaths(tmp_path / "Emulation")
    paths.ensure()
    (paths.roms / "ps2").mkdir(exist_ok=True)
    (paths.roms / "ps2" / "NFSU2.iso").write_text("x")
    monkeypatch.setattr(mode, "in_gaming_session", lambda env=None: True)
    monkeypatch.setattr(mode, "refresh_rates_available", lambda env=None: True)  # a screen with other rates
    monkeypatch.setattr(gamescope_ctl, "set_focus_order", lambda order, runner=None: True)
    monkeypatch.setattr(gamescope_ctl, "set_window_appid", lambda *a, **k: True)
    refresh = {"hz": 0, "sets": []}
    monkeypatch.setattr(gamescope_ctl, "dynamic_refresh", lambda runner=None: refresh["hz"])
    monkeypatch.setattr(gamescope_ctl, "set_dynamic_refresh",
                        lambda hz, runner=None: refresh["sets"].append(hz) or refresh.update(hz=hz) or True)
    monkeypatch.setattr(retroarch, "launch", lambda *a, **k: (True, "Starting"))
    pages = {}

    def factory(cfg):
        pages["Games"] = GamesTab(FakeService(), library_settings=cfg["libraries"], emulation_root=str(paths.root))
        return dict(pages)

    config = copy.deepcopy(DEFAULTS)
    config["system"]["follow_game_refresh"] = True  # Settings -> Display: 50 Hz games at 50 Hz
    w = MainWindow(config, lambda c: None, page_factory=factory)
    qtbot.addWidget(w)
    w.windowed = True
    w.show_shell()
    w._log = config_mod.cache_dir() / "logs" / retroarch.LOG_NAME
    w._log.parent.mkdir(parents=True, exist_ok=True)
    w._log.write_text("")
    w._refresh, w._game = refresh, scan(paths, BY_ID["ps2"])[0]
    return w


def test_screen_follows_a_pal_game_and_comes_back(qtbot, window):
    window.launch_rom(window._game)
    window._log.write_text(PAL_LOG)
    qtbot.waitUntil(lambda: window._refresh["sets"] == [50], timeout=5000)
    window.game_watcher._stop()
    window.game_watcher.finished.emit(window._game.appid)
    qtbot.waitUntil(lambda: window._refresh["sets"] == [50, 0], timeout=3000)


def test_the_screen_stays_as_it_is_unless_switched_on(qtbot, window):
    """Off by default: not every panel shows 50 Hz right."""
    assert DEFAULTS["system"]["follow_game_refresh"] is False
    window.config["system"]["follow_game_refresh"] = False
    window.launch_rom(window._game)
    window._log.write_text(PAL_LOG)
    qtbot.wait(1500)
    assert window._refresh["sets"] == [] and getattr(window, "_refresh_timer", None) is None


def test_a_screen_without_other_rates_is_left_alone(qtbot, window, monkeypatch):
    from gamingcrypt.session import mode

    monkeypatch.setattr(mode, "refresh_rates_available", lambda env=None: False)
    window.launch_rom(window._game)
    window._log.write_text(PAL_LOG)
    qtbot.wait(1500)
    assert window._refresh["sets"] == [] and getattr(window, "_refresh_timer", None) is None
    assert window.default_refresh() == 0 and not window.refresh_rates()


def test_a_60_hz_game_leaves_the_screen_alone(qtbot, window):
    window.launch_rom(window._game)
    window._log.write_text("[INFO] [Core] Geometry: 640x448, Aspect: 1.333, FPS: 59.94, Sample rate: 48000.00 Hz.\n")
    qtbot.wait(2500)
    window.game_watcher._stop()
    window.game_watcher.finished.emit(window._game.appid)
    qtbot.wait(300)
    assert window._refresh["sets"] == []


def test_the_quick_menus_choice_wins(qtbot, window):
    window.launch_rom(window._game)
    window._log.write_text(PAL_LOG)
    qtbot.waitUntil(lambda: window._refresh["sets"] == [50], timeout=5000)
    window._refresh["hz"] = 40  # chosen in the quick menu
    qtbot.waitUntil(lambda: not window._refresh_timer.isActive(), timeout=3000)
    assert window._refresh["sets"] == [50]


def test_install_script_takes_the_display_profile_away(tmp_path):
    """GamingCrypt's own profile for the AYANEO 2021 panel (40-60 Hz): the panel shows only its own
    60 Hz right, so the profile is removed - from both places it was ever copied to."""
    assert not (ROOT / "gamingcrypt" / "session" / "gamescope").exists()
    function = subprocess.run(["sed", "-n", "/^remove_gamescope_displays()/,/^}/p", str(ROOT / "install.sh")],
                              capture_output=True, text=True).stdout
    old = [tmp_path / "gamescope" / "gamingcrypt-displays.lua",
           tmp_path / "gamescope" / "scripts" / "gamingcrypt-displays.lua"]
    other = tmp_path / "gamescope" / "scripts" / "my-own.lua"
    for f in (*old, other):
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text("-- a profile")
    subprocess.run(["bash", "-c", f'set -euo pipefail\n{function}\nXDG_CONFIG_HOME="{tmp_path}" '
                    "remove_gamescope_displays"], check=True)
    assert not any(f.exists() for f in old) and other.exists()
    subprocess.run(["bash", "-c", f'set -euo pipefail\n{function}\nXDG_CONFIG_HOME="{tmp_path / "none"}" '
                    "remove_gamescope_displays"], check=True)  # nothing there: fine
