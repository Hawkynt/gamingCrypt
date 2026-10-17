"""Controller input for navigating the GamingCrypt UI.

Delivers standard (Xbox layout) events from a background thread: from the
virtual controller when the user's mapping is active, otherwise from the
physical controller translated with the user's profile.
"""

from __future__ import annotations

import threading
import time
from typing import Callable

from gamingcrypt.input import evdev as e
from gamingcrypt.input.profile import Translator
from gamingcrypt.input.remapper import read_absinfo

Emit = Callable[[int, int, int], None]


class NavSource:
    RECHECK_S = 2.0

    def __init__(self, input_service, emit: Emit,
                 devices: Callable[[], list[e.DeviceInfo]] = e.list_devices,
                 open_device: Callable[[str], e.InputDevice] = e.InputDevice):
        self.input = input_service
        self.emit = emit
        self.devices = devices
        self.open_device = open_device
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def choose(self) -> tuple[e.DeviceInfo, bool] | None:
        """(device, is_virtual)."""
        if self.input.running:
            virtual = next((d for d in self.devices() if d.name == e.VIRTUAL_NAME), None)
            if virtual is not None:
                return virtual, True
        physical = self.input.device()
        return (physical, False) if physical is not None else None

    def start(self) -> None:
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="gamingcrypt-nav", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(2)
        self._thread = None

    def _physical(self) -> list[e.DeviceInfo]:
        """Every controller connected (a Bluetooth one too), when the mapping is off."""
        devices = getattr(self.input, "devices", None)
        if callable(devices):
            return [d for d in devices() if d.name != e.VIRTUAL_NAME]
        one = self.input.device()
        return [one] if one is not None else []

    def _run(self) -> None:
        while not self._stop.is_set():
            choice = self.choose()
            if choice is None:
                self._stop.wait(self.RECHECK_S)
                continue
            info, virtual = choice
            opened = []
            for each in [info] if virtual else self._physical():
                try:
                    opened.append((each, self.open_device(each.path)))
                except OSError:
                    pass
            if not opened:
                self._stop.wait(self.RECHECK_S)
                continue
            try:
                self._read(opened, virtual)
            finally:
                for _each, device in opened:
                    device.close()

    def _read(self, opened: list, virtual: bool) -> None:
        """Every opened controller, until the choice changes (mapping on / off, a controller
        connected or gone)."""
        import select

        translators = {}
        if not virtual:
            for info, device in opened:
                translators[device.fd] = Translator(self.input.profile(info), read_absinfo(device, info.axes))
        devices = {device.fd: device for _info, device in opened}
        paths = sorted(info.path for info, _device in opened)
        checked = time.monotonic()
        while not self._stop.is_set():
            try:
                ready, _, _ = select.select(list(devices), [], [], 0.1)
            except (OSError, ValueError):
                return
            for fd in ready:
                try:
                    events = devices[fd].read(0)
                except OSError:
                    return  # unplugged -> choose again
                translator = translators.get(fd)
                for event in events:
                    if translator is None:
                        self.emit(*event)
                    else:
                        for out in translator.feed(*event):
                            self.emit(*out)
            if time.monotonic() - checked > self.RECHECK_S:
                checked = time.monotonic()
                choice = self.choose()
                if choice is None or choice[1] != virtual:
                    return  # mapping switched on / off
                now = [choice[0].path] if virtual else sorted(d.path for d in self._physical())
                if now != paths:
                    return  # a controller connected or gone
