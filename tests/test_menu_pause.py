"""The quick menu over an emulated game: the game stands still while it's open."""

import socket
import threading

import pytest

from gamingcrypt.emulation import retroarch
from tests.test_emulator_speed import playing, window  # noqa: F401 - the fixture


class FakeRetroArch:
    """Answers GET_STATUS and toggles its pause, over UDP like the real one."""

    def __init__(self, state="PLAYING"):
        self.state, self.got = state, []
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(("127.0.0.1", 0))
        self.port = self.sock.getsockname()[1]
        threading.Thread(target=self.serve, daemon=True).start()

    def serve(self):
        while True:
            try:
                data, peer = self.sock.recvfrom(4096)
            except OSError:
                return
            text = data.decode()
            self.got.append(text)
            if text == "GET_STATUS":
                self.sock.sendto(f"GET_STATUS {self.state} snes,Super Mario World,crc32=0".encode(), peer)
            elif text == "PAUSE_TOGGLE":
                self.state = "PAUSED" if self.state == "PLAYING" else "PLAYING"


@pytest.fixture
def fake():
    server = FakeRetroArch()
    yield server
    server.sock.close()


def wait_for(condition, timeout=2.0):
    import time

    end = time.monotonic() + timeout
    while not condition() and time.monotonic() < end:
        time.sleep(0.01)
    return condition()


def test_pause_and_resume_retroarch(fake):
    assert retroarch.status(fake.port) == "playing"
    assert retroarch.pause(fake.port) and wait_for(lambda: fake.state == "PAUSED")
    assert not retroarch.pause(fake.port)  # paused already: not toggled back on
    assert wait_for(lambda: fake.state == "PAUSED")
    assert retroarch.resume(fake.port) and wait_for(lambda: fake.state == "PLAYING")
    assert not retroarch.resume(fake.port) and fake.state == "PLAYING"


def test_no_retroarch_nothing_happens():
    free = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    free.bind(("127.0.0.1", 0))
    port = free.getsockname()[1]
    free.close()
    assert retroarch.status(port, timeout=0.1) == "" and not retroarch.pause(port)


def test_the_menu_pauses_the_game_and_closing_it_goes_on(qtbot, window, monkeypatch):  # noqa: F811
    calls = []
    monkeypatch.setattr(retroarch, "pause", lambda *a: calls.append("pause") or True)
    monkeypatch.setattr(retroarch, "resume", lambda *a: calls.append("resume") or True)
    menu = playing(window)
    qtbot.waitUntil(lambda: calls == ["pause"])
    menu.load_state_button.click()  # a page of the menu: still paused
    window.menu_page.gamepad_back()  # back in the menu
    qtbot.wait(50)
    assert calls == ["pause"]
    menu.close_menu()
    qtbot.waitUntil(lambda: calls == ["pause", "resume"])
    window.toggle_quick_menu()
    menu.load_state_button.click()
    window.state_chosen(window._game, window._paths, "load", 0)  # a state picked: on with the game
    qtbot.waitUntil(lambda: calls == ["pause", "resume", "pause", "resume"])


def test_a_game_paused_already_is_left_paused(qtbot, window, monkeypatch):  # noqa: F811
    calls = []
    monkeypatch.setattr(retroarch, "pause", lambda *a: calls.append("pause") or False)  # it was paused
    monkeypatch.setattr(retroarch, "resume", lambda *a: calls.append("resume") or True)
    menu = playing(window)
    qtbot.waitUntil(lambda: calls == ["pause"])
    menu.close_menu()
    qtbot.wait(100)
    assert calls == ["pause"]


def test_an_emulator_without_a_pause_command_is_stopped(qtbot, window, monkeypatch):  # noqa: F811
    from gamingcrypt.steam import running

    signals = []
    monkeypatch.setattr(running, "pause_game", lambda appid, stop: signals.append((appid, stop)) or 2)
    import dataclasses

    game = window._game
    eden = dataclasses.replace(game, system=dataclasses.replace(game.system, emulator="eden"))
    monkeypatch.setattr(window, "running_rom", lambda: eden)
    menu = playing(window)
    qtbot.waitUntil(lambda: signals == [(game.appid, True)])
    menu.close_menu()
    qtbot.waitUntil(lambda: signals == [(game.appid, True), (game.appid, False)])


def test_stopping_and_going_on_signals_the_game(tmp_path):
    import signal

    from gamingcrypt.steam import running

    sent = []
    pids = {11, 12}
    running_game = lambda appid, proc: pids  # noqa: E731
    import gamingcrypt.steam.running as module

    original = module.game_processes
    module.game_processes = running_game
    try:
        assert running.pause_game(5, True, kill=lambda pid, sig: sent.append((pid, sig))) == 2
        assert running.pause_game(5, False, kill=lambda pid, sig: sent.append((pid, sig))) == 2
    finally:
        module.game_processes = original
    assert sorted(sent) == sorted([(11, signal.SIGSTOP), (12, signal.SIGSTOP), (11, signal.SIGCONT),
                                   (12, signal.SIGCONT)])
