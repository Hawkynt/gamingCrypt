"""Settings -> Security -> Users, and the app with more than one user."""

import copy

import pytest

from gamingcrypt import users
from gamingcrypt.config import DEFAULTS
from gamingcrypt.system.controls import SystemControls
from gamingcrypt.ui.users_page import CodeFlow, NamePage
from gamingcrypt.unlock import kdf
from tests.test_users import ADMIN_CODE, FAST, Volume, verify


def config():
    cfg = copy.deepcopy(DEFAULTS)
    cfg["unlock"].update(method="pin", volume="/tmp/x.vc", kdf=kdf.new_params(**FAST))
    return cfg


@pytest.fixture
def tab(qtbot):
    from gamingcrypt.ui.settings_tab import SettingsTab

    saved = []
    tab = SettingsTab(config(), lambda c: saved.append(copy.deepcopy(c)), system=SystemControls(), admin_check=verify)
    tab._saved = saved
    qtbot.addWidget(tab)
    tab.resize(1280, 800)
    tab.show()
    tab.show_sub_tab("Security")
    return tab


def enter_new(flow, method, code, repeat=None):
    flow.choose_method(method)
    flow.input.secret_entered.emit(code)
    flow.input.secret_entered.emit(code if repeat is None else repeat)


def add(qtbot, tab, name, method, code, admin_code=ADMIN_CODE):
    section = tab.users_section
    section.add_button.click()
    page = tab.currentWidget()
    assert isinstance(page, NamePage)
    page.edit.setText(name)
    page.ok_button.click()
    flow = tab.currentWidget()
    assert isinstance(flow, CodeFlow)
    enter_new(flow, method, code)
    flow.input.secret_entered.emit(admin_code)
    return flow


def test_one_admin_at_first(tab):
    section = tab.users_section
    assert list(section.rows) == ["admin"] and "admin  ·  Admin" in section.rows["admin"]["label"].text()
    assert set(section.rows["admin"]) == {"label", "rename"}  # no age, no deleting, the code is the drive's own
    assert section.add_button.isVisibleTo(tab) and tab.reset_button.isVisibleTo(tab)


def test_adding_a_user(qtbot, tab):
    section = tab.users_section
    flow = add(qtbot, tab, "Mia", "pattern", "14789")
    qtbot.waitUntil(lambda: tab.currentWidget() is tab.overview, timeout=10000)
    cfg = tab.config
    mia = users.all_users(cfg)[1]
    assert (mia.name, mia.method, mia.admin) == ("Mia", "pattern", False) and "Mia can log in now" in tab.status.text()
    assert users.volume_password(cfg, mia.id, "14789") == kdf.derive_password(ADMIN_CODE, cfg["unlock"]["kdf"])
    assert tab._saved[-1]["users"][0]["name"] == "Mia" and "keyring" in tab._saved[-1]["unlock"]
    assert set(section.rows[mia.id]) == {"label", "rename", "age", "code", "delete"}
    assert flow is not tab.currentWidget()


def test_the_admins_code_has_to_be_right(qtbot, tab):
    flow = add(qtbot, tab, "Mia", "pin", "1111", admin_code="000000")
    qtbot.waitUntil(lambda: "not the admin's code" in flow.status.text(), timeout=10000)
    assert tab.currentWidget() is flow and len(users.all_users(tab.config)) == 1 and flow.index == 0  # from the start
    enter_new(flow, "pin", "1111")
    flow.input.secret_entered.emit(ADMIN_CODE)
    qtbot.waitUntil(lambda: tab.currentWidget() is tab.overview, timeout=10000)
    assert len(users.all_users(tab.config)) == 2


def test_a_new_code_has_to_be_repeated(qtbot, tab):
    tab.users_section.add_button.click()
    tab.currentWidget().edit.setText("Mia")
    tab.currentWidget().ok_button.click()
    flow = tab.currentWidget()
    enter_new(flow, "pin", "1111", repeat="1112")
    assert "didn't match" in flow.status.text() and flow.index == 0 and "Choose the new PIN" in flow.prompt.text()
    flow.input.secret_entered.emit("1111")
    assert "Repeat" in flow.prompt.text()
    assert flow.gamepad_back() and tab.currentWidget() is tab.overview  # given up: nothing happened
    assert len(users.all_users(tab.config)) == 1


def test_names(qtbot, tab):
    section = tab.users_section
    section.add_button.click()
    page = tab.currentWidget()
    page.edit.setText("ADMIN")
    page.ok_button.click()
    assert "already a user called" in page.status.text() and tab.currentWidget() is page
    page.cancel_button.click()
    assert tab.currentWidget() is tab.overview
    section.rows["admin"]["rename"].click()
    page = tab.currentWidget()
    assert page.edit.text() == "admin"
    page.edit.setText("Papa")
    page.ok_button.click()
    assert users.admin(tab.config).name == "Papa" and tab._saved[-1]["admin"] == {"name": "Papa"}
    assert "Papa  ·  Admin" in section.rows["admin"]["label"].text()


def test_age_new_code_and_deleting(qtbot, tab):
    from gamingcrypt.ui.modal import open_modal

    add(qtbot, tab, "Mia", "pin", "1111")
    qtbot.waitUntil(lambda: tab.currentWidget() is tab.overview, timeout=10000)
    section, cfg = tab.users_section, tab.config
    mia = users.all_users(cfg)[1]
    age = section.rows[mia.id]["age"]
    assert age.currentData() is None and [age.itemData(i) for i in range(age.count())] == [None, 0, 6, 12, 16, 18]
    age.setCurrentIndex(age.findData(12))
    assert users.get(cfg, mia.id).age == 12 and tab._saved[-1]["users"][0]["age"] == 12
    assert section.rows[mia.id]["age"].currentData() == 12
    section.rows[mia.id]["code"].click()  # the admin gives her another one
    flow = tab.currentWidget()
    enter_new(flow, "password", "geheim")
    flow.input.secret_entered.emit(ADMIN_CODE)
    qtbot.waitUntil(lambda: tab.currentWidget() is tab.overview, timeout=10000)
    assert users.volume_password(cfg, mia.id, "1111") is None and users.volume_password(cfg, mia.id, "geheim")
    assert users.get(cfg, mia.id).method == "password" and users.get(cfg, mia.id).age == 12
    section.rows[mia.id]["delete"].click()
    modal = open_modal(tab)
    assert "Delete the user Mia?" in modal.content.question.text() and len(users.all_users(cfg)) == 2
    modal.content.action_button.click()
    assert [u.name for u in users.all_users(cfg)] == ["admin"] and tab._saved[-1]["users"] == []


def test_a_user_sees_only_themselves_and_changes_their_own_code(qtbot):
    from gamingcrypt.ui.settings_tab import SettingsTab

    cfg = config()
    master = users.admin_master(cfg, ADMIN_CODE, verify)
    mia = users.add(cfg, "Mia", "pin", "1111", master)
    users.add(cfg, "Ben", "pin", "2222", master)
    users.enter(cfg, mia.id)
    tab = SettingsTab(cfg, lambda c: None, system=SystemControls())
    qtbot.addWidget(tab)
    tab.show()
    tab.show_sub_tab("Security")
    section = tab.users_section
    assert list(section.rows) == [mia.id] and set(section.rows[mia.id]) == {"label", "code"}
    assert not section.add_button.isVisibleTo(tab) and not tab.reset_button.isVisibleTo(tab)
    assert "logged in as Mia" in section.hint.text()
    section.rows[mia.id]["code"].click()
    flow = tab.currentWidget()
    flow.input.secret_entered.emit("9999")  # not her current one
    enter_new(flow, "pin", "3333")
    qtbot.waitUntil(lambda: "not your current code" in flow.status.text(), timeout=10000)
    flow.input.secret_entered.emit("1111")
    enter_new(flow, "pin", "3333")
    qtbot.waitUntil(lambda: tab.currentWidget() is tab.overview, timeout=10000)
    assert users.volume_password(cfg, mia.id, "3333") and users.volume_password(cfg, mia.id, "1111") is None


# --- the app -----------------------------------------------------------------------------------

def test_logging_in_as_a_user_and_locking_again(qtbot, tmp_path):
    from gamingcrypt.app import MainWindow

    cfg = config()
    master = users.admin_master(cfg, ADMIN_CODE, verify)
    mia = users.add(cfg, "Mia", "pattern", "14789", master, age=12)
    volume_file = tmp_path / "x.vc"
    volume_file.write_bytes(b"x")
    cfg["unlock"]["volume"] = str(volume_file)
    cfg["steam"]["api_key"] = "A" * 32
    volume = Volume(kdf.derive_password(ADMIN_CODE, cfg["unlock"]["kdf"]))
    saved = []
    window = MainWindow(cfg, lambda c: saved.append(copy.deepcopy(c)), volume.factory, page_factory=lambda c: {})
    qtbot.addWidget(window)
    lock = window.stack.currentWidget()
    assert window.screen_name == "lock" and lock.user_row.isVisibleTo(lock) and lock.user.admin
    lock.user_buttons[mia.id].click()
    lock.input.secret_entered.emit("14789")
    qtbot.waitUntil(lambda: window.screen_name == "shell", timeout=10000)
    assert users.current(cfg).id == mia.id and cfg["steam"]["api_key"] == ""  # her own Steam settings
    assert saved[-1]["last_user"] == mia.id and "session" not in saved[-1]
    assert saved[-1]["steam"]["api_key"] == "A" * 32  # the admin's are written as the admin's
    assert window.verifier["user"] == mia.id and not window.is_admin_code(ADMIN_CODE)
    settings = window.shell.pages["Settings"]
    assert list(settings.users_section.rows) == [mia.id] and not settings.reset_button.isVisibleTo(settings)
    window.panic_lock()
    lock = window.stack.currentWidget()
    assert window.screen_name == "lock" and users.current(cfg).admin and cfg["steam"]["api_key"] == "A" * 32
    assert lock.user.id == mia.id and lock.method == "pattern"  # who was there last is chosen
    lock.user_buttons["admin"].click()
    lock.input.secret_entered.emit(ADMIN_CODE)
    qtbot.waitUntil(lambda: window.screen_name == "shell", timeout=10000)
    assert users.current(cfg).admin and window.is_admin_code(ADMIN_CODE) and not window.is_admin_code("14789")
    assert len(window.shell.pages["Settings"].users_section.rows) == 2


def test_a_config_from_before_starts_as_ever(qtbot, tmp_path):
    from gamingcrypt.app import MainWindow

    cfg = config()
    volume_file = tmp_path / "x.vc"
    volume_file.write_bytes(b"x")
    cfg["unlock"]["volume"] = str(volume_file)
    before = copy.deepcopy(cfg)
    volume = Volume(kdf.derive_password(ADMIN_CODE, cfg["unlock"]["kdf"]))
    saved = []
    window = MainWindow(cfg, lambda c: saved.append(copy.deepcopy(c)), volume.factory, page_factory=lambda c: {})
    qtbot.addWidget(window)
    lock = window.stack.currentWidget()
    assert not lock.user_row.isVisibleTo(lock) and lock.method == "pin"
    lock.input.secret_entered.emit(ADMIN_CODE)
    qtbot.waitUntil(lambda: window.screen_name == "shell", timeout=10000)
    assert users.current(cfg).admin and saved == []  # nothing rewritten
    assert {k: v for k, v in cfg.items() if k != "session"} == before


# --- what a user can't do, and what's their own --------------------------------------------------

@pytest.fixture
def emu(tmp_path):
    from gamingcrypt.emulation.library import EmulationPaths

    paths = EmulationPaths(tmp_path / "GamingCrypt" / "Emulation")
    paths.ensure()
    (paths.roms / "snes" / "Mario.sfc").write_bytes(b"m" * 500)
    (paths.cores / "snes9x_libretro.so").write_text("x")
    (paths.states / "Mario.state").write_text("the admin's")
    (paths.saves / "Mario.srm").write_text("the admin's card")
    return paths


def games_tab(qtbot, emu, user):
    from gamingcrypt.steam.models import SteamGame
    from gamingcrypt.ui.games_tab import GamesTab
    from tests.fakes import FakeService

    tab = GamesTab(FakeService(games=[SteamGame(620, "Portal 2", installed=True)]), emulation_root=str(emu.root),
                   user=user)
    qtbot.addWidget(tab)
    tab.show()
    qtbot.waitUntil(lambda: len(tab.roms.get("snes", [])) == 1)
    return tab


def a_user(age=None):
    cfg = config()
    master = users.admin_master(cfg, ADMIN_CODE, verify)
    return cfg, users.add(cfg, "Mia", "pin", "1111", master, age=age)


def test_only_the_admin_can_delete_games(qtbot, emu):
    from gamingcrypt.ui.game_detail import GameDetailPage

    cfg, mia = a_user()
    for user, allowed in ((None, True), (users.admin(cfg), True), (mia, False)):
        tab = games_tab(qtbot, emu, user)
        assert tab.can_delete is allowed
        tab.open_rom(tab.roms["snes"][0])
        page = tab.currentWidget()
        page.options_button.click()
        assert page.remove_button.isVisibleTo(page.window()) is allowed
        page.ask_remove()
        assert (page.confirm is not None) is allowed
        tab.games[620] = tab.service.games[0]
        steam_page = GameDetailPage(tab, tab.service.games[0])
        qtbot.addWidget(steam_page)
        steam_page.show()
        steam_page.options_button.click()
        assert steam_page.uninstall_button.isVisibleTo(steam_page.window()) is allowed
        tab.close()


def test_storage_offers_no_deleting_to_a_user(qtbot, emu):
    from gamingcrypt.emulation.library import scan
    from gamingcrypt.emulation.systems import BY_ID
    from gamingcrypt.ui.storage_page import StoragePage

    page = StoragePage(lambda: None, games_running=lambda: set(), emulation_fn=lambda: emu, can_delete=lambda: False)
    qtbot.addWidget(page)
    page.show()
    page.refresh()
    qtbot.waitUntil(lambda: len(page.rom_rows) == 1)
    qtbot.wait(300)  # (the list is filled when the page shows and when it's refreshed)
    mario = scan(emu, BY_ID["snes"])[0]
    text, remove = page.rom_rows[mario.appid]
    assert not text.isHidden() and remove.isHidden()
    page.ask_remove(mario, 0)
    assert page.confirm is None and mario.path.exists()


def test_each_user_has_saves_and_save_states_of_their_own(qtbot, emu):
    from gamingcrypt.emulation import retroarch, savestates
    from gamingcrypt.emulation.library import EmulationPaths

    cfg, mia = a_user()
    assert EmulationPaths(emu.root).states == emu.root / "states"  # the admin's: where they always were
    admin_tab, mia_tab = games_tab(qtbot, emu, users.admin(cfg)), games_tab(qtbot, emu, mia)
    assert admin_tab.emulation.states == emu.root / "states" and admin_tab.emulation.saves == emu.root / "saves"
    own = mia_tab.emulation
    assert own.states == emu.root / "users" / mia.id / "states" and own.saves == emu.root / "users" / mia.id / "saves"
    assert own.roms == emu.roms and own.cores == emu.cores and own.config == emu.config  # the games are everybody's
    game = mia_tab.roms["snes"][0]
    assert not savestates.slots(admin_tab.emulation, game)[0].empty
    assert all(s.empty for s in savestates.slots(own, game))  # none of the admin's
    text = retroarch.write_config(own).read_text()
    assert f'savestate_directory = "{own.states}"' in text and f'savefile_directory = "{own.saves}"' in text
    assert own.states.is_dir() and own.saves.is_dir()  # RetroArch finds them there
    (own.states / "Mario.state").write_text("Mia's")
    assert savestates.slots(own, game)[0].path.read_text() == "Mia's"
    assert savestates.slots(admin_tab.emulation, game)[0].path.read_text() == "the admin's"


def test_settings_storage_follows_who_is_logged_in(qtbot, emu):
    from gamingcrypt.ui.settings_tab import SettingsTab

    cfg, mia = a_user()
    cfg["unlock"]["mount_point"] = str(emu.root.parent)
    users.enter(cfg, mia.id)
    tab = SettingsTab(cfg, lambda c: None, system=SystemControls())
    qtbot.addWidget(tab)
    assert tab.emulation_paths().states == emu.root / "users" / mia.id / "states"
    assert not tab.storage_page.can_delete()
    users.enter(cfg, "admin")
    assert tab.emulation_paths().states == emu.root / "states" and tab.storage_page.can_delete()


def test_steam_is_switched_to_the_account_of_who_logs_in(qtbot, tmp_path):
    from types import SimpleNamespace

    from PySide6.QtWidgets import QWidget

    from gamingcrypt.app import MainWindow

    cfg, mia = a_user()
    cfg["steam"]["account"] = "111"  # the admin's
    users.enter(cfg, mia.id)
    cfg["steam"]["account"] = "222"  # Mia chose hers in Settings -> Games
    users.leave(cfg)
    volume_file = tmp_path / "x.vc"
    volume_file.write_bytes(b"x")
    cfg["unlock"]["volume"] = str(volume_file)
    volume = Volume(kdf.derive_password(ADMIN_CODE, cfg["unlock"]["kdf"]))
    accounts = [SimpleNamespace(steam_id="111", persona="Papa", most_recent=True),
                SimpleNamespace(steam_id="222", persona="Mia", most_recent=False)]
    switched = []

    class Service:
        def accounts(self):
            return accounts

        def switch_account(self, account):
            switched.append(account.steam_id)
            for a in accounts:
                a.most_recent = a is account
            return True, "ok"

    def pages(config):
        games = QWidget()
        games.service = Service()
        return {"Games": games}

    window = MainWindow(cfg, lambda c: None, volume.factory, page_factory=pages)
    qtbot.addWidget(window)
    lock = window.stack.currentWidget()
    lock.user_buttons[mia.id].click()
    lock.input.secret_entered.emit("1111")
    qtbot.waitUntil(lambda: switched == ["222"], timeout=10000)
    window.panic_lock()
    lock = window.stack.currentWidget()
    lock.user_buttons["admin"].click()
    lock.input.secret_entered.emit(ADMIN_CODE)
    qtbot.waitUntil(lambda: switched == ["222", "111"], timeout=10000)
    window.panic_lock()  # the admin again: Steam is theirs already
    lock = window.stack.currentWidget()
    lock.user_buttons["admin"].click()
    lock.input.secret_entered.emit(ADMIN_CODE)
    qtbot.waitUntil(lambda: window.screen_name == "shell", timeout=10000)
    qtbot.wait(200)
    assert switched == ["222", "111"]
