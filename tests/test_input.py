import os
import time

import pytest

from gamingcrypt.input import evdev as e
from gamingcrypt.input.profile import (
    AxisCal, CalibrationSession, Capture, Profile, Source, Translator, apply_deadzone, default_profile,
)
from gamingcrypt.input.remapper import Remapper
from gamingcrypt.input.service import InputService

STICK = e.AbsInfo(0, -32768, 32767)
TRIG = e.AbsInfo(0, 0, 255)
HAT = e.AbsInfo(0, -1, 1)
KEYS = {e.BTN_SOUTH, e.BTN_EAST, e.BTN_NORTH, e.BTN_WEST, e.BTN_TL, e.BTN_TR, e.BTN_SELECT, e.BTN_START,
        e.BTN_MODE, e.BTN_THUMBL, e.BTN_THUMBR}
AXES = {e.ABS_X, e.ABS_Y, e.ABS_RX, e.ABS_RY, e.ABS_Z, e.ABS_RZ, e.ABS_HAT0X, e.ABS_HAT0Y}
ABSINFO = {e.ABS_X: STICK, e.ABS_Y: STICK, e.ABS_RX: STICK, e.ABS_RY: STICK, e.ABS_Z: TRIG, e.ABS_RZ: TRIG,
           e.ABS_HAT0X: HAT, e.ABS_HAT0Y: HAT}


# --- low level -------------------------------------------------------------------

def test_parse_bitmap():
    # 64-bit words, most significant first, no padding (as sysfs prints them)
    bits = e.parse_bitmap("7fff000000000000 0 0 0 0")
    assert e.BTN_SOUTH in bits and e.BTN_THUMBR in bits and 0x12f not in bits
    assert e.parse_bitmap("30027") == {0, 1, 2, 5, 16, 17}
    assert e.parse_bitmap("0") == set()


def test_list_devices_from_sysfs(tmp_path):
    def device(n, name, key, abs_, vendor="28de", product="1205"):
        d = tmp_path / f"sys/class/input/event{n}/device"
        (d / "capabilities").mkdir(parents=True)
        (d / "id").mkdir()
        (d / "name").write_text(name + "\n")
        (d / "capabilities/key").write_text(key + "\n")
        (d / "capabilities/abs").write_text(abs_ + "\n")
        (d / "id/vendor").write_text(vendor)
        (d / "id/product").write_text(product)

    device(3, "AT keyboard", "1 0", "0")
    device(12, "Steam Deck", "7fff000000000000 0 0 0 0", "30027")
    device(20, e.VIRTUAL_NAME, "7fff000000000000 0 0 0 0", "30027")
    pads = [d for d in e.list_devices(tmp_path / "sys", tmp_path / "dev") if d.is_gamepad]
    assert [p.name for p in pads] == ["Steam Deck"]  # keyboard and our own virtual pad excluded
    assert pads[0].path == str(tmp_path / "dev/event12") and pads[0].key == "28de:1205:Steam Deck"


def test_event_packing():
    data = e.pack_event(e.EV_KEY, e.BTN_SOUTH, 1) + e.pack_event(e.EV_SYN, 0, 0)
    assert e.unpack_events(data) == [(e.EV_KEY, e.BTN_SOUTH, 1), (e.EV_SYN, 0, 0)]


# --- profile -----------------------------------------------------------------------

def test_default_profile_xbox_like():
    p = default_profile(KEYS, AXES)
    assert p.buttons["a"] == Source("key", e.BTN_SOUTH)
    assert p.buttons["dpad_left"] == Source("abs", e.ABS_HAT0X, -1)
    assert p.buttons["lt"] == Source("abs", e.ABS_Z, 1)
    assert p.axes == {"lx": 0, "ly": 1, "rx": 3, "ry": 4, "lt": 2, "rt": 5}


def test_default_profile_digital_dpad_and_triggers():
    keys = {e.BTN_SOUTH, e.BTN_DPAD_UP, e.BTN_DPAD_DOWN, e.BTN_DPAD_LEFT, e.BTN_DPAD_RIGHT, e.BTN_TL2, e.BTN_TR2}
    p = default_profile(keys, {e.ABS_X, e.ABS_Y})
    assert p.buttons["dpad_up"] == Source("key", e.BTN_DPAD_UP)
    assert p.buttons["lt"] == Source("key", e.BTN_TL2) and p.axes["lt"] is None


def test_profile_roundtrip():
    p = default_profile(KEYS, AXES)
    p.calibration[e.ABS_X] = AxisCal(120, 10, 250)
    p.deadzone = 0.12
    assert Profile.from_dict(p.to_dict()) == p


def test_axis_cal_normalize():
    cal = AxisCal(120, 20, 220)  # off-centre stick
    assert cal.normalize(120) == 0 and cal.normalize(220) == 1 and cal.normalize(20) == -1
    assert cal.normalize(170) == 0.5 and cal.normalize(500) == 1
    assert AxisCal(0, 0, 255).normalize(51) == pytest.approx(0.2)


def test_deadzone():
    assert apply_deadzone(0.05, 0.05, 0.1) == (0, 0)
    x, y = apply_deadzone(1.0, 0.0, 0.1)
    assert x == pytest.approx(1.0) and y == 0
    x, _ = apply_deadzone(0.55, 0.0, 0.1)
    assert x == pytest.approx(0.5)


def test_translator_mapping_and_calibration():
    p = default_profile(KEYS, AXES)
    p.buttons["a"], p.buttons["b"] = p.buttons["b"], p.buttons["a"]  # swap A/B
    p.buttons["guide"] = Source("abs", e.ABS_HAT0Y, -1)  # D-pad up also = Guide
    p.calibration[e.ABS_X] = AxisCal(1000, -31000, 33000)
    t = Translator(p, ABSINFO)
    first = t.feed(e.EV_SYN, 0, 0)
    assert (e.EV_ABS, e.ABS_X, 0) in first  # neutral state is sent once
    t.feed(e.EV_KEY, e.BTN_EAST, 1)  # physical B -> virtual A
    t.feed(e.EV_ABS, e.ABS_X, 33000)  # calibrated full right
    t.feed(e.EV_ABS, e.ABS_HAT0Y, -1)
    t.feed(e.EV_ABS, e.ABS_Z, 255)
    out = {(ty, c): v for ty, c, v in t.feed(e.EV_SYN, 0, 0)}
    assert out[(e.EV_KEY, e.BTN_SOUTH)] == 1 and (e.EV_KEY, e.BTN_EAST) not in out
    assert out[(e.EV_ABS, e.ABS_X)] == 32767
    assert out[(e.EV_ABS, e.ABS_HAT0Y)] == -1 and out[(e.EV_KEY, e.BTN_MODE)] == 1
    assert out[(e.EV_ABS, e.ABS_Z)] == 255
    assert t.feed(e.EV_SYN, 0, 0) == []  # nothing changed -> nothing sent


def test_translator_trigger_as_button_and_deadzone():
    p = default_profile(KEYS, AXES)
    p.buttons["rt"] = Source("key", e.BTN_TR)  # RT on the right bumper
    t = Translator(p, ABSINFO)
    t.feed(e.EV_SYN, 0, 0)
    t.feed(e.EV_ABS, e.ABS_Z, 5)  # inside the trigger deadzone
    t.feed(e.EV_ABS, e.ABS_X, 1500)  # inside the stick deadzone
    t.feed(e.EV_KEY, e.BTN_TR, 1)
    out = {(ty, c): v for ty, c, v in t.feed(e.EV_SYN, 0, 0)}
    assert out[(e.EV_ABS, e.ABS_RZ)] == 255
    assert (e.EV_ABS, e.ABS_Z) not in out and (e.EV_ABS, e.ABS_X) not in out


def test_calibration_session():
    p = default_profile(KEYS, AXES)
    s = CalibrationSession(p, {**ABSINFO, e.ABS_X: e.AbsInfo(800, -32768, 32767)})
    for v in (700, 900, 800, 850):
        s.feed(e.EV_ABS, e.ABS_X, v)
    s.next_step()
    profile, message = s.finish()
    assert profile is None and "LX" in message
    for code in (e.ABS_X, e.ABS_Y, e.ABS_RX, e.ABS_RY):
        s.feed(e.EV_ABS, code, -30000)
        s.feed(e.EV_ABS, code, 31000)
    for code in (e.ABS_Z, e.ABS_RZ):
        s.feed(e.EV_ABS, code, 3)
        s.feed(e.EV_ABS, code, 250)
    profile, message = s.finish()
    assert message == "Calibration done"
    assert profile.calibration[e.ABS_X] == AxisCal(800, -30000, 31000)
    assert profile.calibration[e.ABS_Z] == AxisCal(3, 3, 250)
    assert 0.03 <= profile.deadzone <= 0.3


def test_capture():
    c = Capture(ABSINFO)
    assert c.feed(e.EV_KEY, e.BTN_WEST, 0) is None
    assert c.feed(e.EV_ABS, e.ABS_X, 5000) is None  # small wobble
    assert c.feed(e.EV_ABS, e.ABS_RY, -30000) == Source("abs", e.ABS_RY, -1)
    assert c.feed(e.EV_ABS, e.ABS_HAT0X, 1) == Source("abs", e.ABS_HAT0X, 1)
    assert c.feed(e.EV_KEY, e.BTN_WEST, 1) == Source("key", e.BTN_WEST)
    assert Source("abs", e.ABS_RZ, 1).describe() == "Axis RZ +"


# --- service --------------------------------------------------------------------------

class FakeRemapper:
    def __init__(self, info, profile, ok=True):
        self.info, self.profile, self.ok = info, profile, ok
        self.running = False
        self.error = "" if ok else "Permission denied (/dev/uinput)"

    def start(self):
        self.running = self.ok
        return self.ok

    def stop(self):
        self.running = False


def service(pads, ok=True):
    import copy
    from gamingcrypt.config import DEFAULTS

    cfg = copy.deepcopy(DEFAULTS)
    saved = []
    made = []

    def factory(info, profile):
        made.append(FakeRemapper(info, profile, ok))
        return made[-1]

    return InputService(cfg, saved.append, finder=lambda: pads, remapper_factory=factory), cfg, saved, made


PAD = e.DeviceInfo("/dev/input/event9", "Handheld", "1234", "5678", KEYS, AXES)


def test_service_enable_profile_pause_resume():
    svc, cfg, saved, made = service([PAD])
    assert not svc.start()  # disabled by default
    assert svc.set_enabled(True) and svc.running and saved[-1]["input"]["enabled"]
    profile = svc.profile(PAD)
    profile.deadzone = 0.2
    svc.save_profile(PAD, profile)
    assert made[-1].profile.deadzone == 0.2  # restarted with the new profile
    assert cfg["input"]["profiles"]["1234:5678:Handheld"]["deadzone"] == 0.2
    was = svc.pause()
    assert was and not svc.running
    svc.resume(was)
    assert svc.running
    assert svc.reset_profile(PAD).deadzone == 0.08
    svc.set_enabled(False)
    assert not svc.running


def test_service_errors():
    svc, *_ = service([])
    svc.cfg["enabled"] = True
    assert not svc.start() and svc.error == "No controller found"
    svc, *_ = service([PAD], ok=False)
    assert not svc.set_enabled(True) and "uinput" in svc.error


def test_service_game_env_hides_the_grabbed_pad():
    svc, *_ = service([PAD])
    assert svc.game_env() == {}  # not grabbed: nothing to hide
    svc.set_enabled(True)
    assert svc.game_env() == {"SDL_GAMECONTROLLER_IGNORE_DEVICES": "0x1234/0x5678"}
    same = e.DeviceInfo("/dev/input/event9", "Pad", f"{e.VIRTUAL_VENDOR:04x}", f"{e.VIRTUAL_PRODUCT:04x}", KEYS, AXES)
    svc, *_ = service([same])
    svc.set_enabled(True)
    assert svc.game_env() == {}  # its id is the virtual one's: hiding it would hide both


# --- real kernel round trip --------------------------------------------------------------

uinput_ok = pytest.mark.skipif(not os.access("/dev/uinput", os.W_OK), reason="/dev/uinput not writable")


def wait_for_device(name, timeout=3.0):
    end = time.time() + timeout
    while time.time() < end:
        for d in e.list_devices():
            if d.name == name and os.access(d.path, os.R_OK):
                return d
        time.sleep(0.05)
    raise AssertionError(f"{name} did not appear")


@uinput_ok
def test_real_remapper_end_to_end():
    """A fake handheld (off-centre 0..255 stick, A/B swapped by the user) -> virtual Xbox pad."""
    name = f"GC Test Handheld {os.getpid()}"
    physical = e.UInput(name=name, keys=[e.BTN_SOUTH, e.BTN_EAST, e.BTN_NORTH, e.BTN_WEST],
                        axes=[e.AxisSpec(e.ABS_X, 0, 255), e.AxisSpec(e.ABS_Y, 0, 255),
                              e.AxisSpec(e.ABS_HAT0X, -1, 1), e.AxisSpec(e.ABS_HAT0Y, -1, 1)])
    remapper = None
    out = None
    try:
        info = wait_for_device(name)
        profile = default_profile(info.keys, info.axes)
        profile.buttons["a"], profile.buttons["b"] = profile.buttons["b"], profile.buttons["a"]
        profile.calibration[e.ABS_X] = AxisCal(140, 10, 250)
        profile.calibration[e.ABS_Y] = AxisCal(128, 0, 255)
        remapper = Remapper(info, profile)
        assert remapper.start(), remapper.error
        virtual = wait_for_device(e.VIRTUAL_NAME)
        assert (virtual.vendor, virtual.product) == ("045e", "028f")  # not the built-in pads' id
        out = e.InputDevice(virtual.path)
        assert out.absinfo(e.ABS_X).maximum == 32767
        out.read(0.2)  # drop the initial neutral state
        physical.emit([(e.EV_KEY, e.BTN_EAST, 1), (e.EV_ABS, e.ABS_X, 250), (e.EV_ABS, e.ABS_Y, 128),
                       (e.EV_ABS, e.ABS_HAT0X, -1),
                       (e.EV_SYN, 0, 0)])
        got = {}
        end = time.time() + 2
        while time.time() < end and (e.EV_KEY, e.BTN_SOUTH) not in got:
            for t, c, v in out.read(0.2):
                got[(t, c)] = v
        assert got[(e.EV_KEY, e.BTN_SOUTH)] == 1  # physical B became A
        assert got[(e.EV_ABS, e.ABS_X)] == 32767  # calibrated full deflection
        assert got[(e.EV_ABS, e.ABS_HAT0X)] == -1
        # the physical pad is grabbed: nobody else reads it while remapping
        other = e.InputDevice(info.path)
        physical.emit([(e.EV_KEY, e.BTN_NORTH, 1), (e.EV_SYN, 0, 0)])
        assert other.read(0.2) == []
        other.close()
    finally:
        if out is not None:
            out.close()
        if remapper is not None:
            remapper.stop()
        physical.close()
    assert not remapper.running


def test_remapper_reports_open_errors():
    def fail(path):
        raise PermissionError(13, "Permission denied", path)

    r = Remapper(PAD, default_profile(KEYS, AXES), open_device=fail)
    assert not r.start() and "Permission denied" in r.error


def test_playstation_and_nintendo_pads_get_the_xbox_layout():
    """Their left button (Square / Y) is BTN_WEST - passed on as X (BTN_NORTH, xpad), like an Xbox pad's."""
    from gamingcrypt.input.profile import Translator

    for vendor in ("054c", "057E"):
        p = default_profile(KEYS, AXES, vendor)
        assert p.buttons["x"] == Source("key", e.BTN_WEST) and p.buttons["y"] == Source("key", e.BTN_NORTH)
    xbox = default_profile(KEYS, AXES, "045e")
    assert xbox.buttons["x"] == Source("key", e.BTN_NORTH) and xbox.buttons["y"] == Source("key", e.BTN_WEST)
    t = Translator(default_profile(KEYS, AXES, "054c"), {})
    t.feed(e.EV_KEY, e.BTN_WEST, 1)
    assert (e.EV_KEY, e.BTN_NORTH, 1) in t.feed(e.EV_SYN, e.SYN_REPORT, 0)  # Square -> X


def test_x_and_y_reach_their_hooks():
    """xpad: X (the left button) is BTN_NORTH, Y (the top one) BTN_WEST."""
    from PySide6.QtWidgets import QApplication, QPushButton

    from gamingcrypt.ui.navigator import GamepadNavigator

    QApplication.instance() or QApplication([])
    calls = []
    window = QPushButton()
    window.gamepad_west = lambda: calls.append("west (X)") or True
    window.gamepad_north = lambda: calls.append("north (Y)") or True
    window.show()
    nav = GamepadNavigator(window)
    window.setFocus()
    for code in (e.BTN_NORTH, e.BTN_WEST):
        nav.on_event(e.EV_KEY, code, 1)
        nav.on_event(e.EV_KEY, code, 0)
    assert calls == ["west (X)", "north (Y)"]
    window.close()


# --- more than one controller (the built-in one and a Bluetooth one) ------------------------

class PipePad:
    """A controller whose events are handed in by the test - select() sees them (a pipe)."""

    def __init__(self):
        self.fd, self._wake = os.pipe()
        self.events, self.grabbed, self.closed, self.gone = [], False, False, False

    def press(self, *events):
        self.events.extend(events)
        os.write(self._wake, b"x")

    def unplug(self):
        self.gone = True
        os.write(self._wake, b"x")

    def absinfo(self, axis):
        return ABSINFO.get(axis)

    def grab(self):
        self.grabbed = True

    def read(self, timeout=0.1):
        try:
            os.read(self.fd, 64)
        except BlockingIOError:
            pass
        if self.gone:
            raise OSError(19, "No such device")
        events, self.events = self.events, []
        return events

    def close(self):
        self.closed = True


class FakeVirtual:
    def __init__(self):
        self.got, self.closed = [], False

    def emit(self, events):
        self.got.extend(events)

    def close(self):
        self.closed = True


BUILT_IN = e.DeviceInfo("/dev/input/event7", "Microsoft X-Box 360 pad", "045e", "028e", KEYS, AXES)
DUALSENSE = e.DeviceInfo("/dev/input/event13", "DualSense Wireless Controller", "054c", "0ce6", KEYS, AXES)


def wait_until(condition, timeout=3.0):
    end = time.time() + timeout
    while not condition() and time.time() < end:
        time.sleep(0.02)
    return condition()


def test_every_controller_feeds_the_virtual_one(monkeypatch):
    """Seen on the handheld: a DualSense over Bluetooth was a working input device - but only the
    built-in pad was read, so it did nothing in the UI and wasn't player 1 in games. Now each
    connected controller feeds the virtual pad (with its own profile); one connected later is
    found, one that goes away is let go - and the virtual pad stays."""
    from gamingcrypt.input import remapper as remapper_mod

    monkeypatch.setattr(remapper_mod, "RESCAN_S", 0.05)
    pads = {BUILT_IN.path: PipePad(), DUALSENSE.path: PipePad()}
    connected = [BUILT_IN]
    virtual = FakeVirtual()
    profiles = []

    def profile_for(info):
        profiles.append(info.name)
        return default_profile(info.keys, info.axes)

    r = Remapper(BUILT_IN, default_profile(KEYS, AXES), open_device=lambda path: pads[path],
                 make_uinput=lambda: virtual, find=lambda: list(connected), profile_for=profile_for)
    assert r.start(), r.error
    try:
        pads[BUILT_IN.path].press((e.EV_KEY, e.BTN_SOUTH, 1), (e.EV_SYN, 0, 0))
        assert wait_until(lambda: (e.EV_KEY, e.BTN_SOUTH, 1) in virtual.got)
        connected.append(DUALSENSE)  # paired over Bluetooth meanwhile
        assert wait_until(lambda: DUALSENSE in r.infos)
        assert pads[DUALSENSE.path].grabbed and "DualSense Wireless Controller" in profiles  # its own profile
        pads[DUALSENSE.path].press((e.EV_KEY, e.BTN_EAST, 1), (e.EV_SYN, 0, 0))
        assert wait_until(lambda: (e.EV_KEY, e.BTN_EAST, 1) in virtual.got)
        connected.remove(DUALSENSE)
        pads[DUALSENSE.path].unplug()  # switched off
        assert wait_until(lambda: DUALSENSE not in r.infos) and pads[DUALSENSE.path].closed
        assert r.running and not virtual.closed and not r.error  # the built-in one goes on
        pads[BUILT_IN.path].press((e.EV_KEY, e.BTN_NORTH, 1), (e.EV_SYN, 0, 0))
        assert wait_until(lambda: (e.EV_KEY, e.BTN_NORTH, 1) in virtual.got)
    finally:
        r.stop()
    assert virtual.closed and all(p.closed for p in pads.values())


def test_wine_games_skip_every_grabbed_controller():
    svc, *_ = service([BUILT_IN, DUALSENSE])
    svc.set_enabled(True)
    svc.remapper.infos = [BUILT_IN, DUALSENSE]
    assert svc.game_env() == {"SDL_GAMECONTROLLER_IGNORE_DEVICES": "0x045e/0x028e,0x054c/0x0ce6"}


def test_the_ui_reads_every_controller_without_the_mapping(monkeypatch):
    """Mapping off: the UI reads the controllers themselves - all of them, not only the first."""
    from gamingcrypt.input.nav_source import NavSource

    pads = {BUILT_IN.path: PipePad(), DUALSENSE.path: PipePad()}

    class Svc:
        running = False

        def devices(self):
            return [BUILT_IN, DUALSENSE]

        def device(self):
            return BUILT_IN

        def profile(self, info):
            return default_profile(info.keys, info.axes)

    got = []
    src = NavSource(Svc(), lambda *ev: got.append(ev), devices=lambda: [BUILT_IN, DUALSENSE],
                    open_device=lambda path: pads[path])
    src.start()
    try:
        time.sleep(0.2)
        pads[DUALSENSE.path].press((e.EV_KEY, e.BTN_SOUTH, 1), (e.EV_SYN, 0, 0))
        pads[BUILT_IN.path].press((e.EV_KEY, e.BTN_EAST, 1), (e.EV_SYN, 0, 0))
        assert wait_until(lambda: (e.EV_KEY, e.BTN_SOUTH, 1) in got and (e.EV_KEY, e.BTN_EAST, 1) in got)
    finally:
        src.stop()
