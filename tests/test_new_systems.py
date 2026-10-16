"""3DS (Azahar), Wii (Dolphin) and Wii U (Cemu) - all through RetroArch."""

import io
import zipfile

import pytest

from gamingcrypt.emulation import bios, cores, layouts, retroarch
from gamingcrypt.emulation.covers import PLAYLISTS
from gamingcrypt.emulation.library import EmulationPaths, scan
from gamingcrypt.emulation.systems import BY_ID, short_name


@pytest.fixture
def paths(tmp_path, monkeypatch):
    monkeypatch.setattr(retroarch, "CORE_DIRS", ())
    p = EmulationPaths(tmp_path / "Emulation")
    p.ensure()
    return p


def test_the_new_systems():
    assert BY_ID["3ds"].cores == ("azahar", "citra") and short_name("3ds") == "3DS"
    assert BY_ID["wii"].cores == ("dolphin",) and short_name("wii") == "Wii"
    assert BY_ID["wiiu"].cores == ("cemu",) and short_name("wiiu") == "Wii U"
    assert all(BY_ID[s].emulator == "retroarch" for s in ("3ds", "wii", "wiiu"))
    assert not BY_ID["wiiu"].save_states and BY_ID["wii"].save_states and BY_ID["3ds"].save_states
    assert PLAYLISTS["3ds"] == "Nintendo - Nintendo 3DS" and PLAYLISTS["wiiu"] == "Nintendo - Wii U"
    assert layouts.console("wii")["Home"] == "r3" and layouts.console("wiiu")["ZR"] == "r2"
    keys = bios.REQUIREMENTS["wiiu"]
    assert not keys.required and "Cemu/keys.txt" in keys.files  # only for encrypted disc images


def test_their_games_are_found(paths):
    for system, name in (("3ds", "Mario Kart 7.3ds"), ("wii", "Wii Sports.wbfs"), ("wii", "Zelda.rvz"),
                         ("wiiu", "Mario Kart 8.wua"), ("wiiu", "Zelda.wux")):
        (paths.roms_for(BY_ID[system]) / name).write_text("x")
    assert [g.name for g in scan(paths, BY_ID["wii"])] == ["Wii Sports", "Zelda"]
    assert [g.name for g in scan(paths, BY_ID["wiiu"])] == ["Mario Kart 8", "Zelda"]
    assert [g.name for g in scan(paths, BY_ID["3ds"])] == ["Mario Kart 7"]


def launch(paths, tmp_path, system, name):
    (paths.roms_for(BY_ID[system]) / name).write_text("x")
    game = next(g for g in scan(paths, BY_ID[system]) if g.path.name == name)
    ok, _ = retroarch.launch(game, paths, tmp_path / "d", tmp_path / "l", popen=lambda cmd, **k: None,
                             which=lambda n: "/usr/bin/retroarch")
    assert ok
    return game, (paths.config / "gamingcrypt.cfg").read_text()


def test_wii_u_draws_with_vulkan(paths, tmp_path):
    (paths.cores / "cemu_libretro.so").write_text("x")
    game, config = launch(paths, tmp_path, "wiiu", "Mario Kart 8.wua")
    assert 'video_driver = "vulkan"' in config
    assert 'cemu_gpu_api = "Vulkan"' in retroarch.core_options_file(paths, game).read_text()


def test_wii_has_a_wii_remote_with_nunchuk_and_gamecube_a_pad(paths, tmp_path):
    (paths.cores / "dolphin_libretro.so").write_text("x")
    _game, config = launch(paths, tmp_path, "wii", "Wii Sports.wbfs")
    assert 'input_libretro_device_p1 = "769"' in config
    _game, config = launch(paths, tmp_path, "gc", "Zelda.iso")
    assert "input_libretro_device_p1" not in config


def test_3ds_on_glcore(paths, tmp_path):
    (paths.cores / "azahar_libretro.so").write_text("x")
    _game, config = launch(paths, tmp_path, "3ds", "Mario Kart 7.3ds")
    assert 'video_driver = "glcore"' in config


class Response:
    def __init__(self, status, content=b""):
        self.status_code, self.content = status, content


def dolphin_zip() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("dolphin-emu/Sys/GC/font_western.bin", "font")
        archive.writestr("dolphin-emu/Sys/GameSettings/GALE01.ini", "ini")
        archive.writestr("../outside.txt", "no")  # nothing outside its folder
    return buffer.getvalue()


def test_dolphins_system_files_are_downloaded_with_the_core(paths):
    asked = []

    def get(url):
        asked.append(url)
        if url.endswith("Dolphin.zip"):
            return Response(200, dolphin_zip())
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("dolphin_libretro.so", "core")
        return Response(200, buffer.getvalue())

    (paths.roms_for(BY_ID["wii"]) / "Wii Sports.wbfs").write_text("x")
    assert cores.missing(paths, [BY_ID["wii"]]) == [BY_ID["wii"]]
    assert cores.ensure(paths, BY_ID["wii"], get=get, machine="x86_64") is not None
    assert asked[-1] == "https://buildbot.libretro.com/assets/system/Dolphin.zip"
    assert (paths.bios / "dolphin-emu" / "Sys" / "GC" / "font_western.bin").read_text() == "font"
    assert not (paths.bios.parent / "outside.txt").exists() and not (paths.bios / "outside.txt").exists()
    assert not list(paths.bios.glob("*.part"))
    assert cores.missing(paths, [BY_ID["wii"], BY_ID["gc"]]) == []
    asked.clear()
    assert cores.download_system_files(paths, "dolphin", get) is not None and asked == []  # there already


def test_a_core_already_there_gets_its_system_files(paths):
    (paths.cores / "dolphin_libretro.so").write_text("x")
    assert cores.missing(paths, [BY_ID["gc"]]) == [BY_ID["gc"]]  # the core, but no Sys folder
    assert cores.needs_system_files(paths, paths.cores / "dolphin_libretro.so")
    assert not cores.needs_system_files(paths, paths.cores / "snes9x_libretro.so")
    assert cores.download_system_files(paths, "dolphin", lambda url: Response(404)) is None  # offline etc.
    assert cores.needs_system_files(paths, "dolphin")


def test_no_save_states_in_the_quick_menu_for_wii_u(qtbot):
    from PySide6.QtWidgets import QWidget

    from gamingcrypt.system.controls import SystemControls
    from gamingcrypt.ui.quick_menu import QuickMenu
    from tests.test_quick_menu import Audio, Brightness

    host = QWidget()
    qtbot.addWidget(host)
    host.resize(1280, 800)
    menu = QuickMenu(host, SystemControls(audio=Audio(), brightness=Brightness()))
    menu.set_emulated(True, 1.0, states=False)
    menu.open_menu(0x70000001, "Mario Kart 8")
    assert not menu.state_row.isVisibleTo(menu) and menu.controls_row.isVisibleTo(menu)
    menu.set_emulated(True, 1.0)
    assert menu.state_row.isVisibleTo(menu)


def test_sega_32x(paths, tmp_path):
    """Through PicoDrive (no BIOS needed), with the Mega Drive's 6-button pad."""
    from gamingcrypt.ui import console_pictures

    system = BY_ID["sega32x"]
    assert system.cores == ("picodrive",) and short_name("sega32x") == "32X"
    assert PLAYLISTS["sega32x"] == "Sega - 32X" and "sega32x" not in bios.REQUIREMENTS
    assert layouts.console("sega32x") == layouts.console("megadrive")
    assert set(layouts.console("sega32x")) <= set(console_pictures.picture("sega32x").buttons)
    (paths.roms_for(system) / "Knuckles Chaotix.32x").write_text("x")
    (paths.cores / "picodrive_libretro.so").write_text("x")
    game, _config = launch(paths, tmp_path, "sega32x", "Virtua Racing Deluxe.32x")
    assert [g.name for g in scan(paths, system)] == ["Knuckles Chaotix", "Virtua Racing Deluxe"]
