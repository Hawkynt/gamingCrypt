"""Settings -> Network -> Bluetooth (bluetoothctl)."""

import copy
import subprocess

import pytest

from gamingcrypt.system.bluetooth import Bluetooth, parse_info

PAD = "AA:BB:CC:DD:EE:01"
BUDS = "AA:BB:CC:DD:EE:02"
INFO = {
    PAD: """Device AA:BB:CC:DD:EE:01 (public)
\tName: Xbox Wireless Controller
\tAlias: Xbox Wireless Controller
\tIcon: input-gaming
\tPaired: yes
\tTrusted: yes
\tConnected: yes
\tBattery Percentage: 0x55 (85)
""",
    BUDS: """Device AA:BB:CC:DD:EE:02 (public)
\tName: Buds
\tAlias: Buds
\tIcon: audio-headset
\tPaired: no
\tConnected: no
""",
}


class Ctl:
    def __init__(self, powered=True, fail=()):
        self.calls, self.powered, self.fail = [], powered, fail

    def __call__(self, cmd, **kw):
        self.calls.append(cmd)
        args = cmd[1:]
        if any(f in args for f in self.fail):
            return subprocess.CompletedProcess(cmd, 1, "Failed to pair: org.bluez.Error.AuthenticationFailed\n", "")
        if args == ["show"]:
            return subprocess.CompletedProcess(cmd, 0, f"Controller X\n\tPowered: {'yes' if self.powered else 'no'}\n", "")
        if args == ["devices"]:
            return subprocess.CompletedProcess(cmd, 0, f"Device {PAD} Xbox Wireless Controller\nDevice {BUDS} Buds\n", "")
        if args[0] == "info":
            return subprocess.CompletedProcess(cmd, 0, INFO[args[1]], "")
        if "pair" in args:
            return subprocess.CompletedProcess(cmd, 0, "Attempting to pair\nPairing successful\n", "")
        if args[0] == "connect":
            return subprocess.CompletedProcess(cmd, 0, "Attempting to connect\nConnection successful\n", "")
        return subprocess.CompletedProcess(cmd, 0, "", "")


def bt(**kw):
    return Bluetooth(Ctl(**kw), which=lambda tool: "/usr/bin/bluetoothctl")


def test_devices_with_battery_and_icons():
    devices = bt().devices()
    assert [d.name for d in devices] == ["Xbox Wireless Controller", "Buds"]  # connected first
    pad, buds = devices
    assert pad.connected and pad.paired and pad.battery == 85 and pad.symbol == "🎮"
    assert not buds.paired and buds.battery is None and buds.symbol == "🎧"
    assert parse_info("X", "").name == "X"


def test_pair_trusts_and_connects():
    b = bt()
    assert b.pair(BUDS.lower()) == (True, "Connected")
    args = [c[1:] for c in b.runner.calls]
    assert args == [["info", BUDS], ["pairable", "on"],  # pairable: or BlueZ keeps no key (see below)
                    ["--agent", "NoInputNoOutput", "pair", BUDS], ["trust", BUDS], ["connect", BUDS]]


def test_failures_and_bad_addresses():
    failing = bt(fail=("pair",))
    ok, message = failing.pair(BUDS)
    assert not ok and "pairing mode" in message
    assert not any(c[1] in ("trust", "connect") for c in failing.runner.calls)  # no trust/connect
    with pytest.raises(ValueError):
        bt().connect("AA:BB; rm -rf /")
    assert bt().disconnect(PAD) == (True, "Disconnected") and bt().remove(PAD) == (True, "Removed")
    assert bt().set_powered(False)[0]


DUALSENSE = "58:10:31:C1:82:42"
HALF_PAIRED = """Device 58:10:31:C1:82:42 (public)
\tName: DualSense Wireless Controller
\tAlias: DualSense Wireless Controller
\tIcon: input-gaming
\tPaired: yes
\tBonded: no
\tTrusted: yes
\tConnected: yes
"""


def test_a_controller_paired_without_its_key_is_paired_anew():
    """Seen on the handheld: paired while the adapter wasn't pairable - "Paired: yes, Bonded: no".
    BlueZ refused its input ("Rejected connection from !bonded device"): connected, and neither
    the UI nor games got a single button. It's removed and paired again, the adapter pairable."""
    INFO[DUALSENSE] = HALF_PAIRED
    try:
        device = parse_info(DUALSENSE, HALF_PAIRED)
        assert device.paired and device.connected and device.bonded is False and device.half_paired
        assert not parse_info(PAD, INFO[PAD]).half_paired  # (no "Bonded" line: an older BlueZ - fine)
        b = bt()
        assert b.pair(DUALSENSE) == (True, "Connected")
        args = [c[1:] for c in b.runner.calls]
        assert args[:4] == [["info", DUALSENSE], ["remove", DUALSENSE], ["pairable", "on"],
                            ["--agent", "NoInputNoOutput", "pair", DUALSENSE]]
    finally:
        INFO.pop(DUALSENSE)


def test_search_scans_first():
    b = bt()
    b.scan(3)
    assert b.runner.calls[-1] == ["bluetoothctl", "--timeout", "3", "scan", "on"]


def test_not_installed():
    assert not Bluetooth(Ctl(), which=lambda tool: None).available


@pytest.fixture
def section(qtbot):
    from gamingcrypt.config import DEFAULTS
    from gamingcrypt.ui.settings_tab import SettingsTab
    from tests.test_wifi import wifi

    tab = SettingsTab(copy.deepcopy(DEFAULTS), lambda c: None, wifi=wifi(), bluetooth=bt())
    qtbot.addWidget(tab)
    tab.show()
    tab.sub_buttons["Network"].click()
    qtbot.waitUntil(lambda: len(tab.bluetooth_section.rows) == 2)
    return tab.bluetooth_section


def test_bluetooth_section(qtbot, section):
    pad_buttons = section.rows[PAD].findChildren(type(section.toggle))
    assert "Connected" in pad_buttons[0].text() and "🔋 85%" in pad_buttons[0].text()
    assert pad_buttons[1].text() == "Remove"
    buds_buttons = section.rows[BUDS].findChildren(type(section.toggle))
    assert "Tap to pair" in buds_buttons[0].text() and len(buds_buttons) == 1  # nothing to remove yet
    buds_buttons[0].click()
    qtbot.waitUntil(lambda: ["bluetoothctl", "connect", BUDS] in section.bt.runner.calls)
    qtbot.waitUntil(lambda: section.status.text() == "Connected" and not section.busy)
    section.rows[PAD].findChildren(type(section.toggle))[0].click()  # connected: tap disconnects
    qtbot.waitUntil(lambda: ["bluetoothctl", "disconnect", PAD] in section.bt.runner.calls)


def test_search_button(qtbot, section):
    section.search_button.click()
    assert "pairing mode" in section.status.text()
    qtbot.waitUntil(lambda: any("scan" in c for c in section.bt.runner.calls) and not section.busy)


def test_bluetooth_off(qtbot):
    from gamingcrypt.config import DEFAULTS
    from gamingcrypt.ui.settings_tab import SettingsTab
    from tests.test_wifi import wifi

    tab = SettingsTab(copy.deepcopy(DEFAULTS), lambda c: None, wifi=wifi(), bluetooth=bt(powered=False))
    qtbot.addWidget(tab)
    tab.sub_buttons["Network"].click()
    qtbot.waitUntil(lambda: tab.bluetooth_section.status.text() == "Bluetooth is off")
    assert not tab.bluetooth_section.search_button.isEnabled()


def test_bluetooth_page_over_a_game(qtbot):
    """From the quick menu: the same list as in Settings, with Done to go back."""
    from gamingcrypt.ui.network_page import BluetoothPage

    page = BluetoothPage(bt())
    qtbot.addWidget(page)
    page.show()
    qtbot.waitUntil(lambda: len(page.section.rows) == 2)
    assert page.section.toggle.isChecked()
    closed = []
    page.closed.connect(lambda: closed.append(True))
    page.done_button.click()
    assert page.gamepad_back() and closed == [True, True]


def test_quick_menu_opens_bluetooth_while_the_game_runs(qtbot, monkeypatch):
    from gamingcrypt.app import MainWindow
    from gamingcrypt.config import DEFAULTS
    from gamingcrypt.ui.network_page import BluetoothPage
    from gamingcrypt.ui.settings_tab import SettingsTab

    ctl = Ctl()
    bluetooth = Bluetooth(ctl, which=lambda tool: "/usr/bin/bluetoothctl")
    cfg = copy.deepcopy(DEFAULTS)
    window = MainWindow(cfg, lambda c: None, page_factory=lambda c: {
        "Settings": SettingsTab(c, lambda _c: None, bluetooth=bluetooth)})
    qtbot.addWidget(window)
    window.windowed = True
    window.show()
    window.show_shell()
    asides = []
    monkeypatch.setattr(window, "step_aside", lambda front="steam": asides.append(front))
    window.game_watcher.appid, window.game_watcher.phase = 620, "playing"  # any game: a Steam one here
    window.toggle_quick_menu()
    menu = window.quick_menu
    assert menu.bluetooth_button.isVisibleTo(menu)
    menu.bluetooth_button.click()
    page = window.menu_page
    assert isinstance(page, BluetoothPage) and page.isVisible() and not menu.isVisible()
    assert page.section.bt is bluetooth and window.nav_root() is page and asides == []  # the game keeps running behind
    qtbot.waitUntil(lambda: BUDS in page.section.rows)
    page.section.choose(next(d for d in bluetooth.devices() if d.mac == BUDS))
    qtbot.waitUntil(lambda: ["bluetoothctl", "connect", BUDS] in ctl.calls)  # paired, trusted, connected
    page.done_button.click()
    assert window.menu_page is None and menu.isVisible() and asides == []  # back in the quick menu, not out of the game
    menu.close_menu()
    assert asides == ["game"]
    window.game_watcher._stop()


def test_the_list_says_a_half_paired_controller_needs_pairing_again(qtbot, section, monkeypatch):
    from gamingcrypt.system.bluetooth import Device

    pairs = []
    monkeypatch.setattr(section.bt, "pair", lambda mac: pairs.append(mac) or (True, "Connected"))
    half = Device(DUALSENSE, "DualSense Wireless Controller", paired=True, connected=True, icon="input-gaming",
                  bonded=False)
    section.show_devices([half])
    button = section.rows[DUALSENSE].findChildren(type(section.toggle))[0]
    assert "Not paired properly · tap to pair again" in button.text() and "Connected" not in button.text()
    button.click()  # not "disconnect": paired anew
    assert "pairing mode" in section.status.text()
    qtbot.waitUntil(lambda: pairs == [DUALSENSE])
