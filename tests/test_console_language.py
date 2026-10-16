"""The console's language for Wii, Wii U and GameCube games."""

import copy

import pytest

from gamingcrypt.config import DEFAULTS
from gamingcrypt.emulation import languages, retroarch
from gamingcrypt.emulation.library import EmulationPaths, scan
from gamingcrypt.emulation.systems import BY_ID

GERMAN = {"LANG": "de_DE.UTF-8"}


def test_which_systems_have_one():
    assert all(languages.has_language(BY_ID[s]) for s in ("wii", "wiiu", "gc"))
    assert not languages.has_language(BY_ID["snes"]) and not languages.has_language(BY_ID["ps2"])
    assert "Portuguese" in languages.languages(BY_ID["wiiu"]) and "Portuguese" not in languages.languages(BY_ID["wii"])


def test_without_a_choice_the_devices_language():
    wii = BY_ID["wii"]
    config = copy.deepcopy(DEFAULTS)
    assert languages.for_system(config, wii, GERMAN) == "German"
    assert languages.for_system(config, wii, {"LANG": "pt_BR.UTF-8"}) == "English"  # the Wii hasn't it
    assert languages.for_system(config, BY_ID["wiiu"], {"LANG": "pt_BR.UTF-8"}) == "Portuguese"
    assert languages.for_system(config, wii, {"LANG": "zh_TW.UTF-8"}) == "Traditional Chinese"
    assert languages.for_system(config, BY_ID["wiiu"], {"LANG": "zh_TW.UTF-8"}) == "Taiwanese"
    assert languages.for_system(config, wii, {}) == "English"
    assert languages.for_system(config, BY_ID["snes"], GERMAN) is None
    languages.set_chosen(config, "wii", "French")
    assert languages.for_system(config, wii, GERMAN) == "French"
    languages.set_chosen(config, "wii", None)
    assert "wii" not in config["console_language"]


def test_what_the_cores_get():
    assert languages.core_options("dolphin", "German") == {"dolphin_language": "2"}
    assert languages.core_options("dolphin", "Japanese") == {"dolphin_language": "0"}
    assert languages.core_options("cemu", "German") == {"cemu_console_language": "German"}
    assert languages.core_options("snes9x", "German") == {} and languages.core_options("cemu", None) == {}


@pytest.fixture
def paths(tmp_path, monkeypatch):
    monkeypatch.setattr(retroarch, "CORE_DIRS", ())
    p = EmulationPaths(tmp_path / "Emulation")
    p.ensure()
    return p


def test_a_game_starts_in_it(paths, tmp_path):
    (paths.cores / "dolphin_libretro.so").write_text("x")
    (paths.roms_for(BY_ID["wii"]) / "Wii Sports.wbfs").write_text("x")
    game = scan(paths, BY_ID["wii"])[0]
    run = dict(popen=lambda cmd, **k: None, which=lambda n: "/usr/bin/retroarch")
    retroarch.launch(game, paths, tmp_path / "d", tmp_path / "l", language="German", **run)
    options = retroarch.core_options_file(paths, game).read_text()
    assert 'dolphin_language = "2"' in options
    assert 'global_core_options = "true"' in (paths.config / "gamingcrypt.cfg").read_text()
    retroarch.launch(game, paths, tmp_path / "d", tmp_path / "l", language="English", **run)
    assert 'dolphin_language = "1"' in retroarch.core_options_file(paths, game).read_text()  # changed back


def test_the_system_page_sets_it(qtbot, paths):
    from gamingcrypt.ui.emulation_pages import SystemPage
    from gamingcrypt.ui.games_tab import GamesTab
    from tests.fakes import FakeService

    (paths.roms_for(BY_ID["wiiu"]) / "Mario Kart 8.wua").write_text("x")
    config, saved = copy.deepcopy(DEFAULTS), []
    tab = GamesTab(FakeService(), emulation_root=str(paths.root))
    tab.shader_config = (config, lambda c: saved.append(copy.deepcopy(c)))
    qtbot.addWidget(tab)
    tab.show()
    page = SystemPage(tab, BY_ID["wiiu"], scan(paths, BY_ID["wiiu"]))
    assert not page.language_button.isHidden()
    snes = SystemPage(tab, BY_ID["snes"], [])
    assert snes.language_button.isHidden()
    page.language_button.click()
    language = tab.currentWidget()
    assert language.combo.currentData() is None and language.combo.currentText().startswith("Like the device")
    language.combo.setCurrentIndex(language.combo.findData("Japanese"))
    assert saved[-1]["console_language"] == {"wiiu": "Japanese"}
    assert languages.for_system(config, BY_ID["wiiu"], GERMAN) == "Japanese"
    language.combo.setCurrentIndex(0)
    assert saved[-1]["console_language"] == {}
