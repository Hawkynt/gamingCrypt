"""Runtime controls of the running gamescope (X11 root window properties).

The refresh rate of the internal screen changes without restarting gamescope (so a
running game keeps running). Whether a rate is possible depends on the panel - hence
the keep/revert question in the UI. gamescope has one knob for the refresh rate and
the FPS limit together, see set_frame_target.

Which app gamescope shows is steered like Steam does it on the Steam Deck: every
window carries an app id (STEAM_GAME; games launched by Steam get theirs from
gamescope), and GAMESCOPECTRL_BASELAYER_APPID on the root lists the app ids in
the order they should be on screen. GamingCrypt gives itself its own id and puts
it first - so Steam's Big Picture never pops up in front of it by itself.
"""

from __future__ import annotations

import re
import subprocess
from typing import Callable

Runner = Callable[..., subprocess.CompletedProcess]
DYNAMIC_REFRESH = "GAMESCOPE_DYNAMIC_REFRESH"
FOCUS_ORDER = "GAMESCOPECTRL_BASELAYER_APPID"
FPS_LIMIT = "GAMESCOPE_FPS_LIMIT"
TOUCH_MODE = "STEAM_TOUCH_CLICK_MODE"  # how gamescope hands on touches (Steam sets it the same way)
TOUCH_PASSTHROUGH = 4  # real touches (Qt: GamingCrypt; the session's --default-touch-mode)
TOUCH_LEFT_CLICK = 1  # touches as left clicks at the finger (the movie player can't read touches)
SCREENSHOT = "GAMESCOPECTRL_REQUEST_SCREENSHOT"
SCREENSHOT_FILE = "/tmp/gamescope.png"  # where gamescope writes it
FULL_COMPOSITION = 2  # what's on screen, overlays included
WINDOW_APPID = "STEAM_GAME"
BIG_PICTURE_APPID = 769  # Steam's own UI windows
LAUNCHER_APPID = 4293000000  # GamingCrypt's window - no real Steam app has this id


def _xprop(args: list[str], runner: Runner) -> subprocess.CompletedProcess | None:
    try:
        return runner(["xprop", "-root", *args], capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return None


def _number(name: str, runner: Runner) -> int:
    result = _xprop([name], runner)
    if result is None or result.returncode != 0:
        return 0
    match = re.search(r"=\s*(\d+)", result.stdout)
    return int(match.group(1)) if match else 0


def _set_number(name: str, value: int, runner: Runner) -> bool:
    args = ["-f", name, "32c", "-set", name, str(int(value))] if value else ["-remove", name]
    result = _xprop(args, runner)
    return result is not None and result.returncode == 0


def set_frame_target(refresh: int, fps: int, runner: Runner = subprocess.run) -> bool:
    """The screen's refresh rate and the FPS limit - one number for gamescope, as Steam sets it
    on the Steam Deck: the screen goes to the highest rate of its panel the number divides (50:
    50 Hz; 30: 60 Hz with every second frame) and games are held at the number. 0: the panel's own.

    Through gamescope's control protocol: what the root window's properties say
    (GAMESCOPE_DYNAMIC_REFRESH, GAMESCOPE_FPS_LIMIT) gamescope (3.16) overwrites with this
    number on every frame - set by the properties alone, the refresh rate never changed and
    games ran on at 60 with a limit of 30. An FPS limit wins: it's the one that's about the game."""
    try:
        ctl = runner(["gamescopectl", "debug_set_fps_limit", str(int(fps or refresh))], capture_output=True,
                     text=True, timeout=5)
        return ctl.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def dynamic_refresh(runner: Runner = subprocess.run) -> int:
    """The refresh rate asked for last (0 = the panel's own) - kept in the root window's property."""
    return _number(DYNAMIC_REFRESH, runner)


def set_dynamic_refresh(hz: int, runner: Runner = subprocess.run) -> bool:
    ctl = set_frame_target(hz, _number(FPS_LIMIT, runner), runner)
    return _set_number(DYNAMIC_REFRESH, hz, runner) or ctl  # the property: older gamescopes, and to remember


def set_window_appid(window: int, appid: int = LAUNCHER_APPID, runner: Runner = subprocess.run) -> bool:
    try:
        result = runner(["xprop", "-id", str(int(window)), "-f", WINDOW_APPID, "32c",
                         "-set", WINDOW_APPID, str(int(appid))], capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return False
    return result.returncode == 0


def set_notification_overlay(window: int, runner: Runner = subprocess.run) -> bool:
    """Draw this window over everything as a notification (as Steam's toasts) - its own plane,
    next to the external overlay mangoapp (the performance overlay) uses: gamescope draws only
    one external overlay, so a second one pushed the performance overlay away.

    gamescope counts an overlay as a notification when it's narrower than the screen and takes
    no input (steamcompmgr: nWidth < root_width): give it the screen's size less one pixel."""
    try:
        result = runner(["xprop", "-id", str(int(window)), "-f", "STEAM_OVERLAY", "32c", "-set",
                         "STEAM_OVERLAY", "1"], capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return False
    return result.returncode == 0


def notification_geometry(screen) -> tuple[int, int, int, int]:
    """(x, y, w, h) of a notification window: the screen, one pixel narrower (see above)."""
    return screen.x(), screen.y(), max(1, screen.width() - 1), screen.height()


def set_focus_order(appids: list[int], runner: Runner = subprocess.run) -> bool:
    """App ids, most wanted on screen first. Empty = gamescope decides by itself."""
    appids = [int(a) for a in dict.fromkeys(appids) if a]
    if appids:
        value = ",".join(str(a) for a in appids)
        args = ["-f", FOCUS_ORDER, "32c", "-set", FOCUS_ORDER, value]
    else:
        args = ["-remove", FOCUS_ORDER]
    result = _xprop(args, runner)
    return result is not None and result.returncode == 0


def set_fps_limit(fps: int, runner: Runner = subprocess.run) -> bool:
    """Frame limit for the game on screen (0 = none; then the refresh rate that was asked for
    counts again). The property stays as the way for older gamescopes. On a fixed 60 Hz screen
    only rates that divide 60 limit anything (30, 20 …)."""
    ok = set_frame_target(_number(DYNAMIC_REFRESH, runner), fps, runner)
    return _set_number(FPS_LIMIT, fps, runner) or ok


# --- upscaling: a game on gamescope's second X server, at a lower resolution ------------------

XWAYLAND_MODE = "GAMESCOPE_XWAYLAND_MODE_CONTROL"  # server index, width, height, allow bigger than the screen
SCALING_FILTER = "GAMESCOPE_NEW_SCALING_FILTER"
FILTER_LINEAR, FILTER_FSR = 0, 2  # gamescope's GamescopeUpscaleFilter


def set_xwayland_mode(server: int, width: int, height: int, runner: Runner = subprocess.run) -> bool:
    """The size an X server of gamescope offers its windows (games render at it)."""
    value = f"{int(server)},{int(width)},{int(height)},0"
    result = _xprop(["-f", XWAYLAND_MODE, "32c", "-set", XWAYLAND_MODE, value], runner)
    return result is not None and result.returncode == 0


def set_scaling_filter(value: int, runner: Runner = subprocess.run) -> bool:
    """How gamescope scales a smaller game up to the screen (FILTER_FSR, FILTER_LINEAR)."""
    result = _xprop(["-f", SCALING_FILTER, "32c", "-set", SCALING_FILTER, str(int(value))], runner)
    return result is not None and result.returncode == 0


def set_touch_mode(mode: int, runner: Runner = subprocess.run) -> bool:
    result = _xprop(["-f", TOUCH_MODE, "32c", "-set", TOUCH_MODE, str(int(mode))], runner)
    return result is not None and result.returncode == 0


def request_screenshot(runner: Runner = subprocess.run) -> bool:
    """gamescope writes SCREENSHOT_FILE and removes the property when it's done."""
    args = ["-f", SCREENSHOT, "32c", "-set", SCREENSHOT, str(FULL_COMPOSITION)]
    result = _xprop(args, runner)
    return result is not None and result.returncode == 0


def screenshot_pending(runner: Runner = subprocess.run) -> bool:
    result = _xprop([SCREENSHOT], runner)
    return result is not None and result.returncode == 0 and "=" in result.stdout


# --- performance overlay (mangoapp, started by the gaming session with --mangoapp) ---------

OVERLAY_OFF = "no_display\n"


def overlay_on_text(env: dict | None = None) -> str:
    """What it shows when on: the bar as set in Settings (overlay_bar), else its defaults."""
    try:
        return _bar_file(env).read_text()
    except OSError:
        from gamingcrypt.system.overlay_bar import DEFAULT, mangohud_config

        return mangohud_config(DEFAULT)


def _bar_file(env: dict | None = None):
    return overlay_config(env).with_name("overlay-bar.conf")


def set_bar(text: str, env: dict | None = None) -> bool:
    """Settings → In-game bar changed: kept - and on screen at once if it's shown now."""
    try:
        path = _bar_file(env)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    except OSError:
        return False
    return set_overlay(True, env) if overlay_shown(env) else True


def overlay_config(env: dict | None = None):
    from gamingcrypt.session.mode import config_dir

    return config_dir(env) / "mangohud.conf"


def overlay_available(which=None) -> bool:
    import shutil

    return bool((which or shutil.which)("mangoapp"))


def overlay_shown(env: dict | None = None) -> bool:
    try:
        return "no_display" not in overlay_config(env).read_text()
    except OSError:
        return False


def set_overlay(shown: bool, env: dict | None = None) -> bool:
    """mangoapp watches its config file: the change shows at once."""
    path = overlay_config(env)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(overlay_on_text(env) if shown else OVERLAY_OFF)
    except OSError:
        return False
    return True


def _wanted_file(env: dict | None = None):
    return overlay_config(env).with_name("overlay-wanted")


def overlay_wanted(env: dict | None = None) -> bool:
    """The quick menu's switch - shown only while a game is in front (apply_overlay)."""
    try:
        return _wanted_file(env).read_text().strip() == "1"
    except OSError:
        return overlay_shown(env)  # from before there was a switch: what was on screen


def set_overlay_wanted(on: bool, env: dict | None = None) -> bool:
    try:
        path = _wanted_file(env)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("1\n" if on else "0\n")
    except OSError:
        return False
    return True


def apply_overlay(game_in_front: bool, env: dict | None = None) -> bool:
    """On screen only over a game - not over GamingCrypt's own pages."""
    shown = overlay_wanted(env) and game_in_front
    if shown == overlay_shown(env) and overlay_config(env).exists():
        return True
    return set_overlay(shown, env)
