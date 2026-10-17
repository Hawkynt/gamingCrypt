"""The systems GamingCrypt knows: folder name, game file types, RetroArch cores (best first)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class System:
    id: str
    name: str
    extensions: tuple[str, ...]
    cores: tuple[str, ...]  # RetroArch core names (file "<name>_libretro.so"), preferred first
    bios: tuple[str, ...] = ()  # files the cores need in bios/ (checked, never shipped)
    emulator: str = "retroarch"  # or a standalone one: "eden"
    video: str = ""  # RetroArch video driver the core needs ("": RetroArch's own choice)
    save_states: bool = True  # the core can save states (Cemu can't)
    extra: tuple[tuple[str, str], ...] = ()  # RetroArch settings for its games (e.g. which controller)
    folder_name: str = ""  # its folder in roms/ ("": its id)
    also_in: tuple[str, ...] = ()  # other folder names its games are found in too

    @property
    def folder(self) -> str:
        return self.folder_name or self.id


ARCHIVES = (".zip", ".7z")
DISCS = (".cue", ".chd", ".iso", ".m3u", ".pbp", ".cso")

SYSTEMS: tuple[System, ...] = (
    System("nes", "Nintendo Entertainment System", (".nes", ".fds", ".unf") + ARCHIVES,
           ("mesen", "nestopia", "fceumm")),
    System("snes", "Super Nintendo", (".sfc", ".smc", ".fig", ".swc") + ARCHIVES, ("snes9x", "bsnes")),
    System("n64", "Nintendo 64", (".n64", ".z64", ".v64") + ARCHIVES, ("mupen64plus_next", "parallel_n64")),
    System("gb", "Game Boy", (".gb",) + ARCHIVES, ("gambatte", "sameboy", "mgba")),
    System("gbc", "Game Boy Color", (".gbc",) + ARCHIVES, ("gambatte", "sameboy", "mgba")),
    System("gba", "Game Boy Advance", (".gba",) + ARCHIVES, ("mgba", "vba_next"), ("gba_bios.bin",)),
    System("nds", "Nintendo DS", (".nds",) + ARCHIVES, ("melonds", "desmume")),
    System("3ds", "Nintendo 3DS", (".3ds", ".cci", ".cxi", ".3dsx", ".app", ".z3dsx", ".zcci", ".zcxi"),
           ("azahar", "citra"), video="glcore"),
    System("gc", "GameCube", (".iso", ".gcm", ".gcz", ".rvz", ".ciso"), ("dolphin",)),
    # Dolphin as for GameCube; the controller is a Wii Remote with Nunchuk (RetroArch's device 769 -
    # the core's RETRO_DEVICE_WIIMOTE_NC), not a GameCube pad
    System("wii", "Nintendo Wii", (".iso", ".wbfs", ".rvz", ".wia", ".gcz", ".ciso", ".wad"), ("dolphin",),
           extra=(("input_libretro_device_p1", "769"),)),
    # Cemu: draws with Vulkan (its OpenGL path is black under gamescope), can't save states;
    # one-file games (.wua, or .wud / .wux disc images with the console's keys.txt). Player 1 is a
    # Wii U Pro Controller (RetroArch's device 513 - the core's RETRO_DEVICE_PRO), not the GamePad:
    # some games want one; one that needs the GamePad's screen gets it back in its Options
    # (retroarch.GAME_PADS). The core maps no Home button: Guide / Windows stay the quick menu.
    System("wiiu", "Nintendo Wii U", (".wua", ".wud", ".wux"), ("cemu",), video="vulkan", save_states=False,
           extra=(("input_libretro_device_p1", "513"),)),
    System("mastersystem", "Sega Master System", (".sms",) + ARCHIVES, ("genesis_plus_gx", "picodrive")),
    System("megadrive", "Sega Mega Drive / Genesis", (".md", ".gen", ".smd", ".bin") + ARCHIVES,
           ("genesis_plus_gx", "picodrive")),
    # the Mega Drive's add-on: PicoDrive (it needs no BIOS for it), the Mega Drive's 6-button pad
    System("sega32x", "Sega 32X", (".32x",) + ARCHIVES, ("picodrive",), folder_name="32x",
           also_in=("sega32x",)),
    System("gamegear", "Sega Game Gear", (".gg",) + ARCHIVES, ("genesis_plus_gx",)),
    System("segacd", "Sega CD", (".cue", ".chd", ".iso", ".m3u"), ("genesis_plus_gx",),
           ("bios_CD_U.bin", "bios_CD_E.bin", "bios_CD_J.bin")),
    System("saturn", "Sega Saturn", (".cue", ".chd", ".m3u"), ("mednafen_saturn", "yabasanshiro"),
           ("sega_101.bin", "mpr-17933.bin")),
    System("dreamcast", "Sega Dreamcast", (".cdi", ".gdi", ".chd", ".m3u"), ("flycast",)),
    System("psx", "PlayStation (PS1)", DISCS, ("swanstation", "mednafen_psx_hw", "pcsx_rearmed"),
           ("scph5501.bin",)),
    # LRPS2 (tested on the handheld): RetroArch's "gl" driver shows only black under gamescope;
    # its Vulkan renderer draws NFSU2's light passes dark with ghost images; OpenGL on "glcore"
    # is right and fast. paraLLEl-GS (an option per game) needs "vulkan" - see retroarch.RENDERERS.
    System("ps2", "PlayStation 2 (PS2)", (".iso", ".chd", ".cso", ".gz", ".m3u"), ("pcsx2",), video="glcore"),
    System("psp", "PlayStation Portable", (".iso", ".cso", ".pbp", ".chd"), ("ppsspp",)),
    System("pce", "PC Engine / TurboGrafx-16", (".pce", ".cue", ".chd") + ARCHIVES, ("mednafen_pce_fast",)),
    System("atari2600", "Atari 2600", (".a26", ".bin") + ARCHIVES, ("stella",)),
    System("arcade", "Arcade", (".zip", ".7z"), ("fbneo", "mame2003_plus")),
    System("switch", "Nintendo Switch", (".nsp", ".xci", ".nro"), (), emulator="eden"),
)
BY_ID = {s.id: s for s in SYSTEMS}
# short names for the library cards (the full name is on the system's page)
SHORT = {"nes": "NES", "snes": "SNES", "n64": "N64", "gb": "Game Boy", "gbc": "Game Boy Color",
         "gba": "GBA", "nds": "Nintendo DS", "gc": "GameCube", "mastersystem": "Master System",
         "megadrive": "Mega Drive", "gamegear": "Game Gear", "segacd": "Sega CD", "saturn": "Saturn",
         "dreamcast": "Dreamcast", "psx": "PS1", "ps2": "PS2", "psp": "PSP", "pce": "PC Engine",
         "atari2600": "Atari 2600", "arcade": "Arcade", "switch": "Switch", "sega32x": "32X", "3ds": "3DS", "wii": "Wii",
         "wiiu": "Wii U"}


def short_name(system_id: str) -> str:
    return SHORT.get(system_id, BY_ID[system_id].name)
