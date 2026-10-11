"""A file the automatic matching doesn't recognise: the game is chosen from a list (emulation/names)."""

import json
from types import SimpleNamespace

import pytest

from gamingcrypt.emulation import names as names_mod
from gamingcrypt.emulation.covers import Covers
from gamingcrypt.emulation.library import EmulationPaths, scan
from gamingcrypt.emulation.names import Names
from gamingcrypt.emulation.rom_facts import RomFacts
from gamingcrypt.emulation.systems import BY_ID
from tests.fakes import FakeService

PNG = b"\x89PNG\r\n\x1a\n" + b"x" * 20
LISTED = ["Chrono Trigger (USA)", "Super Mario Kart (USA)", "Super Mario World (Europe)", "Super Mario World (USA)",
          "Super Mario World 2 - Yoshi's Island (USA)", "Terranigma (Europe)", "Terranigma (Germany)"]
TABLE = {"fetched": 1000, "genre": {"Terranigma (Europe)": "Role-Playing", "Super Mario World (USA)": "Platform",
                                   "Secret of Mana (USA)": "Role-Playing"},
         "releaseyear": {"Terranigma (Europe)": "1996", "Super Mario World (USA)": "1990"}}


@pytest.fixture
def emu(tmp_path):
    paths = EmulationPaths(tmp_path / "GamingCrypt" / "Emulation")
    paths.ensure()
    for name in ("smw_hack_v3.sfc", "Terra DE patched.sfc"):
        (paths.roms_for(BY_ID["snes"]) / name).write_bytes(b"x")
    (paths.config / "metadata").mkdir(parents=True)
    (paths.config / "metadata" / "snes.json").write_text(json.dumps(TABLE))
    return paths


def games(emu):
    return {g.path.name: g for g in scan(emu, BY_ID["snes"])}


def libretro(asked):
    """The covers' server: a list of all of them, and the pictures."""
    def get(url):
        asked.append(url)
        if url.endswith("/Named_Boxarts/"):
            html = "".join(f'<a href="{name.replace(" ", "%20")}.png">x</a>' for name in LISTED)
            return SimpleNamespace(status_code=200, content=html.encode())
        known = any(name.replace(" ", "%20").replace("(", "%28").replace(")", "%29") in url for name in LISTED)
        return SimpleNamespace(status_code=200 if known else 404, content=PNG if known else b"")
    return get


def test_the_choice_is_kept_on_the_drive(emu):
    hack = games(emu)["smw_hack_v3.sfc"]
    names = Names(emu)
    assert names.get(hack) is None
    names.set(hack, "Super Mario World (USA)")
    assert Names(emu).get(hack) == "Super Mario World (USA)"
    assert json.loads((emu.config / "names.json").read_text()) == {"snes/smw_hack_v3.sfc": "Super Mario World (USA)"}
    names.set(hack, None)  # automatic again
    assert Names(emu).get(hack) is None
    (emu.config / "names.json").write_text("broken")
    assert Names(emu).get(hack) is None


def test_every_game_of_the_system_to_choose_from(emu):
    hack = games(emu)["smw_hack_v3.sfc"]

    def offline(url):
        import requests

        raise requests.ConnectionError("no network")

    assert names_mod.titles(hack, Covers(emu, get=offline), None) is None
    assert names_mod.titles(hack, Covers(emu, get=offline), RomFacts(emu, now=lambda: 2000)) == sorted(TABLE["genre"])
    asked = []
    found = names_mod.titles(hack, Covers(emu, get=libretro(asked)), RomFacts(emu, now=lambda: 2000))
    assert "Secret of Mana (USA)" in found and "Chrono Trigger (USA)" in found  # with a genre, or with a cover
    assert found == sorted(set(LISTED) | set(TABLE["genre"]))
    assert names_mod.titles(hack, Covers(emu, get=offline), None) == sorted(LISTED)  # the list is kept on the drive


def test_suggestions():
    # nothing typed: what shares a word with the file's name, the most alike first, its region first
    assert names_mod.suggest("Terra DE patched.sfc", LISTED) == []
    assert names_mod.suggest("Terranigma DE patched.sfc", LISTED) == ["Terranigma (Germany)", "Terranigma (Europe)"]
    assert names_mod.suggest("mario world.sfc", LISTED)[:2] == ["Super Mario World (Europe)", "Super Mario World (USA)"]
    # typed: every word in the name, whatever the file is called
    assert names_mod.suggest("smw_hack_v3.sfc", LISTED, "mario wor") == [
        "Super Mario World (Europe)", "Super Mario World (USA)", "Super Mario World 2 - Yoshi's Island (USA)"]
    assert names_mod.suggest("smw_hack_v3.sfc", LISTED, "zelda") == []
    assert len(names_mod.suggest("smw.sfc", LISTED, "a", limit=3)) == 3


def test_cover_genre_and_year_come_by_the_chosen_name(emu):
    hack = games(emu)["smw_hack_v3.sfc"]
    asked = []
    names = Names(emu)
    covers, facts = Covers(emu, get=libretro(asked), names=names), RomFacts(emu, now=lambda: 2000, names=names)
    assert covers.fetch(hack) is None and facts.facts(hack) == ((), None)  # not recognised
    names.set(hack, "Super Mario World (USA)")
    covers.forget(hack)
    facts.forget(hack)
    asked.clear()
    assert covers.fetch(hack).read_bytes() == PNG
    assert len(asked) == 1 and asked[0].endswith("/Named_Boxarts/Super%20Mario%20World%20%28USA%29.png")
    assert facts.facts(hack) == (("Platform",), 1990)
    names.set(hack, "Super Mario World (Europe)")  # no genre under that name: the title's
    facts.forget(hack)
    assert facts.facts(hack) == (("Platform",), 1990)


@pytest.fixture
def tab(qtbot, emu):
    from gamingcrypt.ui.games_tab import GamesTab

    tab = GamesTab(FakeService(), emulation_root=str(emu.root))
    tab._asked = []
    tab.covers.get = libretro(tab._asked)
    tab.rom_facts.now = lambda: 2000
    qtbot.addWidget(tab)
    tab.resize(1280, 800)
    tab.show()
    qtbot.waitUntil(lambda: len(tab.roms.get("snes", [])) == 2)
    return tab


def test_choosing_the_game_on_its_page(qtbot, tab, emu):
    from gamingcrypt import game_facts
    from gamingcrypt.ui.emulation_pages import RomGamePage
    from gamingcrypt.ui.identify_page import IdentifyPage

    hack = next(g for g in tab.roms["snes"] if g.path.name == "smw_hack_v3.sfc")
    tab.open_rom(hack)
    page = tab.currentWidget()
    assert isinstance(page, RomGamePage)
    qtbot.waitUntil(lambda: page.unknown_button.isVisibleTo(page))  # looked for a cover: there's none
    assert page.identify_button.text() == "🔍 Which game is this?"
    assert game_facts.facts_of(hack, tab).genres == ()
    page.unknown_button.click()
    picker = tab.currentWidget()
    assert isinstance(picker, IdentifyPage) and "smw_hack_v3.sfc" in picker.hint.text()
    assert not picker.automatic_button.isVisibleTo(picker)
    qtbot.waitUntil(lambda: picker.names is not None)
    assert picker.buttons == [] and "type a part" in picker.status.text()  # nothing looks like "smw hack v3"
    picker.search.setText("mario world")
    assert [b.text() for b in picker.buttons] == ["Super Mario World (Europe)", "Super Mario World (USA)",
                                                  "Super Mario World 2 - Yoshi's Island (USA)"]
    assert "3 games" in picker.status.text()
    picker.search.setText("qqq")
    assert picker.buttons == [] and "No game with that name" in picker.status.text()
    picker.search.setText("mario world (usa")
    picker.buttons[0].click()
    assert tab.currentWidget() is page and tab.rom_names.get(hack) == "Super Mario World (USA)"
    assert not page.unknown_button.isVisibleTo(page)
    assert page.identify_button.text() == "🔍 Game: Super Mario World (USA)"
    facts = game_facts.facts_of(hack, tab)
    assert facts.genres == ("Platform",) and facts.year == 1990  # what the filters go by
    qtbot.waitUntil(lambda: tab.covers.cached(hack) is not None)  # its cover came by the name
    page.identify_button.click()  # changed one's mind
    picker = tab.currentWidget()
    assert "Chosen: Super Mario World (USA)" in picker.hint.text() and picker.automatic_button.isVisibleTo(picker)
    picker.automatic_button.click()
    assert tab.currentWidget() is page and tab.rom_names.get(hack) is None
    assert game_facts.facts_of(hack, tab).genres == ()


def test_a_recognised_game_is_not_asked_about(qtbot, tab, emu):
    recognised = next(g for g in tab.roms["snes"] if g.path.name == "Terra DE patched.sfc")
    tab.rom_names.set(recognised, "Terranigma (Germany)")
    tab.open_rom(recognised)
    page = tab.currentWidget()
    qtbot.wait(200)
    assert not page.unknown_button.isVisibleTo(page) and page.identify_button.text() == "🔍 Game: Terranigma (Germany)"


def test_the_list_cannot_be_loaded(qtbot, tab, emu):
    import requests

    from gamingcrypt.ui.identify_page import IdentifyPage

    def offline(url):
        raise requests.ConnectionError("no network")

    tab.covers.get = offline
    tab.rom_facts = None
    hack = next(g for g in tab.roms["snes"] if g.path.name == "smw_hack_v3.sfc")
    qtbot.wait(300)  # the cards looked for their covers: the list they fetched is gone again
    (emu.config / "covers" / "snes" / ".index.json").unlink(missing_ok=True)
    tab.open_identify(hack)
    picker = tab.currentWidget()
    assert isinstance(picker, IdentifyPage)
    qtbot.waitUntil(lambda: "no network" in picker.status.text())
    assert picker.buttons == []
