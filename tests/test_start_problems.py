"""RetroArch couldn't load a game: it stays open, empty - the loading screen never ended. Said why."""

from gamingcrypt.emulation import retroarch

# from the handheld: Final Fantasy VIII (Germany) - a LibCrypt protected disc, its .sbi missing
FF8 = """[INFO] [Content] Content loading skipped. Implementation will load it on its own.
[libretro INFO] [System] Loading CD image '/home/x/Emulation/config/playlists/psx/Final Fantasy VIII (Germany).m3u'...
[libretro WARN] [CheckForSBIFile] SBI file missing but required for SLES-02082 (Final Fantasy VIII (Germany))
[ERROR] [Environ] GET_VARIABLE: swanstation_CDROM_AllowBootingWithoutSBIFile - Invalid value.
[INFO] [Environ] SET_MESSAGE: ERROR: You are attempting to run a libcrypt protected game without an SBI file:

SLES-02082: Final Fantasy VIII (Germany)

Your dump is incomplete, you must add the SBI file to run this game. 

The name of the SBI file must match the name of the disc image.
[libretro ERROR] [ReportError] You are attempting to run a libcrypt protected game without an SBI file:

SLES-02082: Final Fantasy VIII (Germany)

Your dump is incomplete, you must add the SBI file to run this game. 

The name of the SBI file must match the name of the disc image.
[INFO] [Environ] SET_MESSAGE: ERROR: System failed to boot. The log may contain more information.
[libretro ERROR] [ReportError] System failed to boot. The log may contain more information.
[ERROR] [Content] Failed to load content.
[INFO] [Core] Unloading core...
"""


def test_a_libcrypt_game_without_its_sbi_files(tmp_path):
    log = tmp_path / "retroarch.log"
    log.write_text(FF8)
    problem = retroarch.start_problem(log)
    assert problem.startswith("Final Fantasy VIII (Germany) is copy protected (LibCrypt)")
    assert ".sbi file next to each disc image" in problem


def test_another_reason_in_the_cores_words(tmp_path):
    log = tmp_path / "retroarch.log"
    log.write_text("[libretro ERROR] [ReportError] Failed to open\n  the disc image.\n"
                   "[libretro ERROR] [ReportError] System failed to boot.\n[ERROR] [Content] Failed to load content.\n")
    assert retroarch.start_problem(log) == "The game didn't load: Failed to open the disc image."
    log.write_text("[ERROR] [Content] Failed to load content.\n")
    assert retroarch.start_problem(log) == "The game didn't load - the emulator couldn't open it"


def test_no_problem_while_it_starts_or_runs(tmp_path):
    log = tmp_path / "retroarch.log"
    assert retroarch.start_problem(log) is None  # (no log yet)
    log.write_text("[INFO] [Core] Loading dynamic libretro core\n[INFO] [Video] Set video size\n")
    assert retroarch.start_problem(log) is None


def test_the_loading_screen_ends_and_says_why(qtbot, monkeypatch, tmp_path):
    from gamingcrypt import config as config_mod
    from gamingcrypt.emulation.library import EMU_APPID_BASE
    from gamingcrypt.steam import running
    from tests.test_game_running import make_window

    window, service, calls = make_window(qtbot, monkeypatch)
    monkeypatch.setattr(config_mod, "cache_dir", lambda: tmp_path)
    quit_ = []
    monkeypatch.setattr(running, "force_quit", lambda appid: quit_.append(appid))
    appid = EMU_APPID_BASE | 0x123
    failures = []
    window.shell.pages["Games"].start_failed = lambda a, problem: failures.append((a, problem))
    window.game_launched(appid)
    assert window.game_watcher.describe(appid) == "Starting RetroArch…"  # (nothing wrong yet)
    (tmp_path / "logs").mkdir()
    (tmp_path / "logs" / retroarch.LOG_NAME).write_text(FF8)
    assert window.game_watcher.describe(appid) == "The game didn't load"
    qtbot.waitUntil(lambda: quit_ == [appid])
    assert not window.game_watcher.active and not window.launch_overlay.isVisible()
    assert failures and "LibCrypt" in failures[0][1]
    assert any("LibCrypt" in text for text in window.toasts.shown)


def test_the_games_page_shows_the_reason(qtbot, tmp_path):
    import copy

    from gamingcrypt.config import DEFAULTS
    from gamingcrypt.emulation.library import EmulationPaths, scan
    from gamingcrypt.emulation.systems import BY_ID
    from gamingcrypt.ui.emulation_pages import RomGamePage
    from gamingcrypt.ui.games_tab import GamesTab
    from tests.fakes import FakeService

    paths = EmulationPaths(tmp_path / "Emulation")
    paths.ensure()
    (paths.roms / "psx" / "Final Fantasy VIII (Germany).m3u").write_text("x")
    game = scan(paths, BY_ID["psx"])[0]
    tab = GamesTab(FakeService(), library_settings=copy.deepcopy(DEFAULTS)["libraries"],
                   emulation_root=str(paths.root))
    qtbot.addWidget(tab)
    page = RomGamePage(tab, game)
    qtbot.addWidget(page)
    page.start_failed(game.appid, "Final Fantasy VIII (Germany) is copy protected (LibCrypt): …")
    page.game_session_ended(game.appid, True)  # (comes right after: must not cover it)
    assert "LibCrypt" in page.status.text() and page.status.property("error")
    page.game_session_ended(game.appid, True)  # a later failure without a reason
    assert page.status.text() == "It didn't start"
