"""Save states of emulated games: nine slots with pictures (emulation/savestates, ui/save_states)."""

import copy
import os
import time

import pytest

from gamingcrypt.config import DEFAULTS
from gamingcrypt.emulation import retroarch, savestates
from gamingcrypt.emulation.library import EmulationPaths, scan
from gamingcrypt.emulation.systems import BY_ID


@pytest.fixture
def emu(tmp_path):
    paths = EmulationPaths(tmp_path / "Emulation")
    paths.ensure()
    (paths.roms / "snes" / "Super Mario World.sfc").write_text("x")
    (paths.roms / "snes" / "Super Mario World 2.sfc").write_text("x")
    return paths


@pytest.fixture
def game(emu):
    return next(g for g in scan(emu, BY_ID["snes"]) if g.path.stem == "Super Mario World")


def write(paths, name, text="state", age=0, picture=True, folder=""):
    """A state as RetroArch writes it, `age` seconds old."""
    target = paths.states / folder / name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text)
    when = time.time() - age
    os.utime(target, (when, when))
    if picture:
        target.with_name(name + ".png").write_text("picture of " + text)
    return target


class FakeRetroArch:
    """Saves into "its current slot", as the real one does."""

    def __init__(self, paths, stem="Super Mario World", slot=0, picture=True, saves=True):
        self.paths, self.stem, self.slot, self.picture, self.saves = paths, stem, slot, picture, saves
        self.sent, self.count = [], 0

    def __call__(self, text, port=None):
        self.sent.append(text)
        if text == "SAVE_STATE" and self.saves:
            self.count += 1
            write(self.paths, f"{self.stem}.state{self.slot or ''}", f"save {self.count}", picture=self.picture)
        return True


def test_names_as_retroarch_uses_them(emu, game):
    assert savestates.state_file(emu, game, 0).name == "Super Mario World.state"
    assert savestates.state_file(emu, game, 4).name == "Super Mario World.state4"
    assert savestates.picture_of(savestates.state_file(emu, game, 4)).name == "Super Mario World.state4.png"
    assert savestates.load_command(4) == "LOAD_STATE_SLOT 4"


def test_config_asks_for_pictures_right_in_the_states_folder(emu):
    text = retroarch.write_config(emu).read_text()
    assert 'savestate_thumbnail_enable = "true"' in text and 'sort_savestates_enable = "false"' in text
    assert 'sort_savestates_by_content_enable = "false"' in text and 'savestates_in_content_dir = "false"' in text


def test_nine_slots_with_and_without_pictures(emu, game):
    write(emu, "Super Mario World.state", age=50)
    write(emu, "Super Mario World.state3", age=10, picture=False)  # saved before there were pictures
    write(emu, "Super Mario World 2.state1")  # another game
    write(emu, "Super Mario World.state.auto")  # RetroArch's own, not a slot
    slots = savestates.slots(emu, game)
    assert [s.slot for s in slots] == list(range(9)) and [s.slot for s in slots if not s.empty] == [0, 3]
    assert slots[0].picture.name == "Super Mario World.state.png" and slots[3].picture is None
    assert slots[3].saved_at > slots[0].saved_at
    assert (emu.states / "Super Mario World 2.state1").exists() and (emu.states / "Super Mario World.state.auto").exists()


def test_more_than_nine_keeps_the_newest_nine(emu, game):
    """After the update: states in any slot, also in RetroArch's folder per core."""
    for slot in range(12):
        write(emu, f"Super Mario World.state{slot or ''}", f"s{slot}", age=1000 - slot * 10)  # 11 is the newest
    write(emu, "Super Mario World.state40", "s40", age=5, folder="Snes9x")
    slots = savestates.slots(emu, game)
    assert all(not s.empty for s in slots)
    kept = sorted(s.path.read_text() for s in slots)
    assert kept == sorted(["s4", "s5", "s6", "s7", "s8", "s9", "s10", "s11", "s40"])
    assert {s.path.read_text() for s in slots if s.slot >= 4} >= {"s4", "s5", "s6", "s7", "s8"}  # stayed where they were
    assert all(s.picture.read_text() == "picture of " + s.path.read_text() for s in slots)  # each its own picture
    left = sorted(f.name for f in emu.states.rglob("*") if f.is_file())
    assert len(left) == 18 and not (emu.states / "Snes9x" / "Super Mario World.state40").exists()
    assert savestates.slots(emu, game)[5].path.read_text() == slots[5].path.read_text()  # and it stays that way


def test_saving_into_a_slot_keeps_the_others(emu, game):
    """RetroArch saves into its own current slot (here 0, which is taken) - the state ends up in
    the slot that was picked, and what was in slot 0 is still there."""
    write(emu, "Super Mario World.state", "old 0", age=100)
    write(emu, "Super Mario World.state2", "old 2", age=90)
    fake = FakeRetroArch(emu)
    assert savestates.capture(emu, game, 5, fake, sleep=lambda s: None)
    assert fake.sent == ["SAVE_STATE"]
    slots = savestates.slots(emu, game)
    assert {s.slot: s.path.read_text() for s in slots if not s.empty} == {0: "old 0", 2: "old 2", 5: "save 1"}
    assert slots[5].picture.read_text() == "picture of save 1" and slots[0].picture.read_text() == "picture of old 0"
    assert not list(emu.states.glob("*.keep"))


def test_saving_over_a_slot(emu, game):
    write(emu, "Super Mario World.state", "old 0", age=100)
    write(emu, "Super Mario World.state2", "old 2", age=90)
    fake = FakeRetroArch(emu, slot=7, picture=False)  # RetroArch on another slot, and no picture this time
    assert savestates.capture(emu, game, 2, fake, sleep=lambda s: None, clock=iter(range(0, 9999)).__next__)
    slots = savestates.slots(emu, game)
    assert {s.slot: s.path.read_text() for s in slots if not s.empty} == {0: "old 0", 2: "save 1"}
    assert slots[2].picture is None  # not the picture of what was there before
    assert sorted(f.name for f in emu.states.iterdir()) == [
        "Super Mario World.state", "Super Mario World.state.png", "Super Mario World.state2"]


def test_a_core_that_cannot_save_loses_nothing(emu, game):
    write(emu, "Super Mario World.state", "old 0")
    fake = FakeRetroArch(emu, saves=False)
    assert not savestates.capture(emu, game, 0, fake, timeout=3, sleep=lambda s: None,
                                  clock=iter(range(0, 9999)).__next__)
    slots = savestates.slots(emu, game)
    assert slots[0].path.read_text() == "old 0" and slots[0].picture is not None
    assert not savestates.capture(emu, game, 0, lambda text: False)  # RetroArch not reachable
    assert savestates.slots(emu, game)[0].path.read_text() == "old 0"


def test_a_save_that_was_interrupted_is_put_back(emu, game):
    write(emu, "Super Mario World.state1.keep", "old 1", picture=False)
    (emu.states / "Super Mario World.state1.png.keep").write_text("picture of old 1")
    slots = savestates.slots(emu, game)
    assert slots[1].path.read_text() == "old 1" and slots[1].picture.read_text() == "picture of old 1"


def test_the_spare_state_is_not_a_slot(emu, game):
    """Slot 99: what a game comes back with after its speed was changed."""
    fake = FakeRetroArch(emu)
    assert savestates.capture(emu, game, savestates.SPARE, fake, sleep=lambda s: None)
    spare = savestates.state_file(emu, game, savestates.SPARE)
    assert spare.read_text() == "save 1" and all(s.empty for s in savestates.slots(emu, game))
    assert savestates.rescue(emu, game) == 0  # it didn't come back: kept where Load state shows it
    assert savestates.slots(emu, game)[0].path.read_text() == "save 1" and not spare.exists()
    write(emu, "Super Mario World.state99", age=savestates.SPARE_KEPT_S + 60)
    savestates.tidy(emu, game)
    assert not spare.exists() and savestates.rescue(emu, game) is None  # an old one is cleared away


def test_removing_a_game_takes_its_states_along(emu, game):
    from gamingcrypt.emulation import removal

    write(emu, "Super Mario World.state3")
    names = {f.name for f in removal.save_files(emu, game)}
    assert names == {"Super Mario World.state3", "Super Mario World.state3.png"}


# --- the page ---------------------------------------------------------------------------------

def picture(path):
    from PySide6.QtGui import QColor, QImage

    image = QImage(320, 224, QImage.Format.Format_RGB32)
    image.fill(QColor("#2060c0"))
    image.save(str(path), "PNG")


@pytest.fixture
def host(qtbot):
    from PySide6.QtWidgets import QMainWindow

    from gamingcrypt.ui import theme

    window = QMainWindow()
    window.setStyleSheet(theme.STYLESHEET)
    qtbot.addWidget(window)
    window.resize(1280, 800)
    window.show()
    return window


def test_saved_text():
    from datetime import datetime

    from gamingcrypt.ui.save_states import saved_text

    assert saved_text(datetime(2026, 10, 12, 14, 2).timestamp()) == "12 Oct 2026 · 14:02"
    assert saved_text(datetime(2026, 9, 1, 9, 5).timestamp()) == "01 Sep 2026 · 09:05"


def test_three_by_three_with_pictures_and_placeholders(qtbot, host, emu, game):
    from gamingcrypt.ui.save_states import SaveStatesPage

    write(emu, "Super Mario World.state", age=500)
    picture(emu.states / "Super Mario World.state.png")
    write(emu, "Super Mario World.state4", age=20, picture=False)  # from before the update
    page = SaveStatesPage(savestates.slots(emu, game), "load", "Super Mario World", parent=host)
    page.show()
    host.grab()
    assert len(page.tiles) == 9 and "Super Mario World" in page.hint.text()
    xs = sorted({t.mapTo(page, t.rect().topLeft()).x() for t in page.tiles})
    ys = sorted({t.mapTo(page, t.rect().topLeft()).y() for t in page.tiles})
    assert len(xs) == 3 and len(ys) == 3  # a 3 by 3 grid
    assert all(page.rect().contains(t.geometry()) for t in page.tiles)  # all on the screen, no scrolling
    with_picture, no_picture, empty = page.tiles[0], page.tiles[4], page.tiles[1]
    assert with_picture.has_picture and not no_picture.has_picture and not empty.has_picture
    assert not no_picture.picture.pixmap().isNull() and not empty.picture.pixmap().isNull()  # a placeholder each
    assert no_picture.picture.pixmap().toImage() != empty.picture.pixmap().toImage()
    from datetime import datetime

    from gamingcrypt.ui.save_states import saved_text

    assert with_picture.caption.text() == "Slot 1" and empty.caption.text() == "Slot 2"
    # date and time of the save, below the picture
    assert no_picture.when.text() == saved_text(no_picture.state.saved_at) and empty.when.text() == ""
    assert f"{datetime.now():%Y}" in no_picture.when.text() and ":" in no_picture.when.text()
    assert with_picture.when.geometry().top() >= with_picture.picture.geometry().bottom()
    assert [t.isEnabled() for t in page.tiles] == [True, False, False, False, True, False, False, False, False]
    assert page.first is no_picture  # the newest
    chosen, closed = [], []
    page.chosen.connect(chosen.append)
    page.closed.connect(lambda: closed.append(True))
    no_picture.tapped.emit()
    assert chosen == [4]
    assert page.gamepad_back() and closed == [True]


def test_saving_asks_before_replacing(qtbot, host, emu, game):
    from gamingcrypt.ui.modal import open_modal
    from gamingcrypt.ui.save_states import SaveStatesPage

    write(emu, "Super Mario World.state", age=500)
    page = SaveStatesPage(savestates.slots(emu, game), "save", parent=host)
    page.show()
    assert all(t.isEnabled() for t in page.tiles) and page.first is page.tiles[1]  # the first empty one
    chosen = []
    page.chosen.connect(chosen.append)
    page.tiles[3].tapped.emit()
    assert chosen == [3] and open_modal(host) is None  # an empty slot: right away
    page.tiles[0].tapped.emit()
    modal = open_modal(host)
    assert chosen == [3] and "slot 1" in modal.content.question.text()
    modal.content.cancel_button.click()
    assert chosen == [3]
    page.tiles[0].tapped.emit()
    open_modal(host).content.action_button.click()
    assert chosen == [3, 0]


def test_all_slots_taken_starts_on_the_oldest(qtbot, host, emu, game):
    from gamingcrypt.ui.save_states import SaveStatesPage

    for slot in range(9):
        write(emu, f"Super Mario World.state{slot or ''}", age=100 + (500 if slot == 6 else slot))
    page = SaveStatesPage(savestates.slots(emu, game), "save", parent=host)
    assert page.first is page.tiles[6]


# --- from the quick menu ----------------------------------------------------------------------

@pytest.fixture
def window(qtbot, emu, monkeypatch):
    from gamingcrypt.app import MainWindow
    from gamingcrypt.ui.games_tab import GamesTab
    from tests.fakes import FakeService

    monkeypatch.setattr(retroarch, "launch", lambda game, *a, **k: (True, "Starting"))
    pages = {}

    def factory(cfg):
        pages["Games"] = GamesTab(FakeService(), library_settings=cfg["libraries"], emulation_root=str(emu.root))
        return dict(pages)

    w = MainWindow(copy.deepcopy(DEFAULTS), lambda c: None, page_factory=factory)
    qtbot.addWidget(w)
    w.windowed = True
    w.resize(1280, 800)
    w.show()
    w.show_shell()
    qtbot.waitUntil(lambda: "snes" in pages["Games"].home.system_cards)
    w._asides = []
    monkeypatch.setattr(w, "step_aside", lambda front="steam": w._asides.append(front))
    return w


def toasts(window):
    return window.toasts.shown + [x[1] for x in window.toasts.queue]


def playing(window, game):
    window.launch_rom(game)
    window.game_watcher.phase = "playing"
    window.toggle_quick_menu()
    return window.quick_menu


def test_save_from_the_quick_menu(qtbot, window, emu, game, monkeypatch):
    from gamingcrypt.ui.save_states import SaveStatesPage

    write(emu, "Super Mario World.state", "old 0", age=100)
    fake = FakeRetroArch(emu)
    monkeypatch.setattr(retroarch, "send", fake)
    menu = playing(window, game)
    menu.save_state_button.click()
    page = window.menu_page
    assert isinstance(page, SaveStatesPage) and page.mode == "save" and page.isVisible() and not menu.isVisible()
    assert window.nav_root() is page and window._asides == []  # GamingCrypt stays in front, the controller on the page
    assert page.geometry() == window.rect() and not page.tiles[0].state.empty
    page.tiles[2].tapped.emit()
    assert window.menu_page is None and window._asides == ["game"]  # back in the game
    qtbot.waitUntil(lambda: any("State saved" in t for t in toasts(window)), timeout=8000)
    slots = savestates.slots(emu, game)
    assert slots[2].path.read_text() == "save 1" and slots[0].path.read_text() == "old 0"


def test_load_from_the_quick_menu(qtbot, window, emu, game, monkeypatch):
    write(emu, "Super Mario World.state6", age=100)
    fake = FakeRetroArch(emu)
    monkeypatch.setattr(retroarch, "send", fake)
    menu = playing(window, game)
    menu.load_state_button.click()
    page = window.menu_page
    assert page.mode == "load" and page.first is page.tiles[6]
    page.tiles[6].tapped.emit()
    assert fake.sent == ["LOAD_STATE_SLOT 6"] and window._asides == ["game"]
    assert any("State loaded" in t for t in toasts(window))


def test_back_from_the_slots_is_the_quick_menu_again(qtbot, window, emu, game, monkeypatch):
    monkeypatch.setattr(retroarch, "send", FakeRetroArch(emu))
    menu = playing(window, game)
    menu.load_state_button.click()
    window.menu_page.gamepad_back()
    assert window.menu_page is None and menu.isVisible() and window._asides == []


def test_a_game_that_cannot_be_saved_says_so(qtbot, window, emu, game, monkeypatch):
    monkeypatch.setattr(retroarch, "send", lambda text, port=None: False)
    menu = playing(window, game)
    menu.save_state_button.click()
    window.menu_page.tiles[0].tapped.emit()
    qtbot.waitUntil(lambda: any("Couldn't save" in t for t in toasts(window)), timeout=8000)


def test_the_slots_close_when_the_game_ends(qtbot, window, emu, game, monkeypatch):
    monkeypatch.setattr(retroarch, "send", FakeRetroArch(emu))
    menu = playing(window, game)
    menu.save_state_button.click()
    assert window.menu_page is not None
    window.game_over(game.appid)
    assert window.menu_page is None


# --- play time ----------------------------------------------------------------------------------

def test_played_text():
    from gamingcrypt.ui.save_states import played_text

    assert played_text(None) == "" and played_text(20) == "Less than a minute played"
    assert played_text(45 * 60 + 59) == "45 min played" and played_text(2 * 3600 + 5 * 60) == "2 h 05 min played"


def test_play_time_is_kept_with_its_state(emu, game):
    fake = FakeRetroArch(emu)
    assert savestates.capture(emu, game, 3, fake, sleep=lambda s: None, played=754)
    assert (emu.states / "Super Mario World.state3.time").read_text() == "754\n"
    write(emu, "Super Mario World.state5", "old 5", age=50)  # from before play time was counted
    slots = savestates.slots(emu, game)
    assert slots[3].played == 754 and slots[5].played is None
    assert savestates.capture(emu, game, 5, fake, sleep=lambda s: None, played=10)  # RetroArch saved into its slot 0
    slots = savestates.slots(emu, game)
    assert (slots[3].played, slots[5].played, slots[0].empty) == (754, 10, True)
    assert savestates.capture(emu, game, 3, fake, sleep=lambda s: None)  # saved over, time unknown: not the old one
    assert savestates.slots(emu, game)[3].played is None
    from gamingcrypt.emulation import removal

    assert "Super Mario World.state5.time" in {f.name for f in removal.save_files(emu, game)}


def test_play_time_moves_with_a_state_that_is_tidied_up(emu, game):
    write(emu, "Super Mario World.state30", "s30", folder="Snes9x")
    (emu.states / "Snes9x" / "Super Mario World.state30.time").write_text("3600\n")
    slots = savestates.slots(emu, game)
    assert slots[0].path.read_text() == "s30" and slots[0].played == 3600


def test_play_time_is_shown_below_the_date(qtbot, host, emu, game):
    from gamingcrypt.ui.save_states import SaveStatesPage

    write(emu, "Super Mario World.state")
    picture(emu.states / "Super Mario World.state.png")
    (emu.states / "Super Mario World.state.time").write_text("7500\n")
    write(emu, "Super Mario World.state1")
    page = SaveStatesPage(savestates.slots(emu, game), "load", parent=host)
    page.show()
    host.grab()
    counted, before, empty = page.tiles[0], page.tiles[1], page.tiles[2]
    assert counted.played.text() == "2 h 05 min played" and before.played.text() == "" and empty.played.text() == ""
    assert counted.played.geometry().top() >= counted.when.geometry().bottom()
    assert counted.when.geometry().top() >= counted.picture.geometry().bottom()
    assert counted.rect().contains(counted.played.geometry())


def test_play_time_counts_from_the_start_and_from_a_loaded_state(qtbot, window, emu, game, monkeypatch):
    """Started without a state: from the start. A state loaded: its time, and on from there."""
    import time as time_module

    clock = {"now": 1000.0}
    monkeypatch.setattr(time_module, "monotonic", lambda: clock["now"])
    fake = FakeRetroArch(emu)
    monkeypatch.setattr(retroarch, "send", fake)
    menu = playing(window, game)
    clock["now"] += 600  # ten minutes in
    monkeypatch.setattr(savestates, "capture", lambda paths, rom, slot, send, **k: fake.sent.append(
        ("saved", slot, k.get("played"))) or True)
    menu.save_state_button.click()
    window.menu_page.tiles[0].tapped.emit()
    qtbot.waitUntil(lambda: ("saved", 0, 600) in fake.sent)
    clock["now"] += 300  # saved again later: the time went on
    window.toggle_quick_menu()
    menu.save_state_button.click()
    window.menu_page.tiles[1].tapped.emit()
    qtbot.waitUntil(lambda: ("saved", 1, 900) in fake.sent)
    write(emu, "Super Mario World.state4")
    (emu.states / "Super Mario World.state4.time").write_text("7200\n")  # two hours in
    window.toggle_quick_menu()
    menu.load_state_button.click()
    window.menu_page.tiles[4].tapped.emit()
    clock["now"] += 60
    assert window.state_played() == 7260
    write(emu, "Super Mario World.state7")  # a state without a time: counted from loading it
    window.toggle_quick_menu()
    menu.load_state_button.click()
    window.menu_page.tiles[7].tapped.emit()
    clock["now"] += 30
    assert window.state_played() == 30
    window.game_over(game.appid)
    window.game_watcher._stop()
    window.launch_rom(game)  # the next start: from zero again
    clock["now"] += 5
    assert window.state_played() == 5
