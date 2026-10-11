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
LUA = ROOT / "gamingcrypt" / "session" / "gamescope" / "gamingcrypt-displays.lua"

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


@pytest.mark.skipif(shutil.which("lua") is None, reason="needs lua")
def test_display_profile_for_the_ayaneo_panel(tmp_path):
    """gamescope's Lua profile: matches the AYANEO 2021 panel (EDID UGD 0x1003), 40-60 Hz. A lower
    rate is the panel's own mode with more blank lines - the pixel clock isn't touched (a slower
    clock gave wrong, shifting colours on the panel)."""
    script = tmp_path / "check.lua"
    script.write_text(f"""
gamescope = {{ config = {{ known_displays = {{}} }}, modegen = {{}} }}
-- as in gamescope's scripts/00-gamescope/common/modegen.lua
gamescope.modegen.adjust_front_porch = function(mode, vfp)
    local vsync = mode.vsync_end - mode.vsync_start
    local vbp = mode.vtotal - mode.vsync_end
    mode.vsync_start = mode.vdisplay + vfp
    mode.vsync_end = mode.vsync_start + vsync
    mode.vtotal = mode.vsync_end + vbp
end
gamescope.modegen.calc_vrefresh = function(mode, refresh)
    return math.floor((1000 * mode.clock) / (mode.htotal * mode.vtotal))
end
gamescope.modegen.calc_max_clock = function(mode, refresh)
    return math.floor(((mode.htotal * mode.vtotal * refresh) + 999) / 1000)
end
function debug(text) end
dofile("{LUA}")
local panel = gamescope.config.known_displays.gamingcrypt_ayaneo_2021_lcd
print(panel.matches({{ vendor = "UGD", product = 0x1003, model = "" }}))
print(panel.matches({{ vendor = "VLV", product = 0x3003, model = "" }}))
print(panel.dynamic_refresh_rates[1], panel.dynamic_refresh_rates[#panel.dynamic_refresh_rates])
local function own()  -- 800 x 1280 at 60 Hz
    return {{ hdisplay = 800, hsync_start = 810, hsync_end = 820, htotal = 880,
             vdisplay = 1280, vsync_start = 1290, vsync_end = 1294, vtotal = 1310, clock = 69168, vrefresh = 60 }}
end
local m = panel.dynamic_modegen(own(), 50)
print(m.vrefresh, m.clock, m.htotal, m.hsync_start, m.vtotal, m.vsync_start, m.vsync_end - m.vsync_start,
      m.vtotal - m.vsync_end)
m = panel.dynamic_modegen(own(), 40)
print(m.vrefresh, m.clock, m.vtotal)
m = panel.dynamic_modegen(own(), 60)
print(m.vrefresh, m.clock, m.vtotal)
""")

    def run(timing=None):
        """The profile as gamescope loads it, with Settings' choice of how a lower rate is made."""
        config = tmp_path / "config" / "gamingcrypt"
        config.mkdir(parents=True, exist_ok=True)
        if timing is None:
            (config / "panel-timing").unlink(missing_ok=True)
        else:
            (config / "panel-timing").write_text(timing + "\n")
        env = {**os.environ, "XDG_CONFIG_HOME": str(tmp_path / "config")}
        out = subprocess.run(["lua", str(script)], capture_output=True, text=True, check=True, env=env).stdout
        return [line.split() for line in out.splitlines()]

    out = run()
    assert out[:3] == [["4000"], ["-1"], ["40", "60"]]
    # rate, clock, pixels a line, sync at, lines, sync at, sync lines, lines after it
    # 50 Hz, the default: 262 more blank lines before the sync pulse - the clock and the rest as they are
    assert out[3] == ["50", "69168", "880", "810", "1572", "1552", "4", "16"]
    assert out[4] == ["40", "69168", "1965"] and out[5] == ["60", "69168", "1310"]  # 60 Hz: the panel's own
    assert run("front") == out and run("nonsense") == out
    assert run("back")[3] == ["50", "69168", "880", "810", "1572", "1290", "4", "278"]  # after the pulse
    assert run("sync")[3] == ["50", "69168", "880", "810", "1572", "1290", "266", "16"]  # the pulse itself
    assert run("line")[3] == ["50", "69168", "1056", "986", "1310", "1290", "4", "16"]  # 176 more pixels a line
    assert run("clock")[3] == ["50", "57640", "880", "810", "1310", "1290", "4", "16"]  # only the clock
    assert all(run(t)[5] == ["60", "69168", "1310"] for t in ("back", "sync", "line", "clock"))


def test_install_script_copies_the_profile(tmp_path):
    """Into ~/.config/gamescope/scripts: right in ~/.config/gamescope gamescope never read it - the
    panel had no other refresh rates, so the screen never followed a 50 Hz game."""
    (tmp_path / "gamescope").mkdir()
    (tmp_path / "gamescope" / "gamingcrypt-displays.lua").write_text("-- where it was before")
    function = subprocess.run(["sed", "-n", "/^install_gamescope_displays()/,/^}/p", str(ROOT / "install.sh")],
                              capture_output=True, text=True).stdout
    subprocess.run(["bash", "-c", f'set -euo pipefail\n{function}\nSRC_DIR="{ROOT}" XDG_CONFIG_HOME="{tmp_path}" '
                    "install_gamescope_displays"], check=True)
    assert (tmp_path / "gamescope" / "scripts" / "gamingcrypt-displays.lua").read_text() == LUA.read_text()
    assert not (tmp_path / "gamescope" / "gamingcrypt-displays.lua").exists()
