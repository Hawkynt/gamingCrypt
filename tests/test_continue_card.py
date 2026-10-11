"""Games tab: "Continue playing" - the game played last, one tap to play on."""

from gamingcrypt.steam.models import SteamGame
from gamingcrypt.ui.games_tab import GamesTab, last_played
from tests.fakes import FakeService


def games():
    return [SteamGame(620, "Portal 2", installed=True, playtime_minutes=1234, last_played=1700000000),
            SteamGame(1145360, "Hades", installed=True, playtime_minutes=60, last_played=1710000000),
            SteamGame(292030, "The Witcher 3", playtime_minutes=6000, last_played=1720000000)]  # not installed


def test_last_played_installed_game():
    assert last_played(games()).name == "Hades"
    assert last_played([SteamGame(1, "New", installed=True)]) is None  # never played


def tab_with(qtbot, game_list):
    service = FakeService(games=game_list)
    tab = GamesTab(service)
    qtbot.addWidget(tab)
    tab.show()
    tab.games.update({g.appid: g for g in game_list})  # the library load does this in the app
    tab.home.set_installed(service.installed_games())
    return tab, service


def test_continue_card_plays_and_opens(qtbot):
    tab, service = tab_with(qtbot, games())
    card = tab.home.continue_card
    assert card.isVisible() and card.title.text() == "Hades"
    assert card.meta.text().startswith("Last played") and "1.0 h played" in card.meta.text()
    card.play_button.click()
    assert service.client.actions == [("play", 1145360)]
    card.details_button.click()
    assert tab.currentWidget().game.appid == 1145360


def test_hidden_while_searching_and_without_played_games(qtbot):
    tab, _ = tab_with(qtbot, games())
    tab.home.search.setText("port")
    assert not tab.home.continue_card.isVisible()
    tab.home.search.setText("")
    assert tab.home.continue_card.isVisible()
    tab2, _ = tab_with(qtbot, [SteamGame(1, "New", installed=True)])
    assert not tab2.home.continue_card.isVisible()


# --- after a start: the main page, the controller on "Continue playing" ---------------------------

def focused(tab):
    from PySide6.QtWidgets import QApplication

    return QApplication.focusWidget()


def test_a_start_puts_the_controller_on_play(qtbot):
    tab, service = tab_with(qtbot, games())
    home = tab.home
    qtbot.waitUntil(lambda: focused(tab) is home.continue_card.play_button)
    assert tab.currentWidget() is home and home.continue_card.title.text() == "Hades"
    home.sort_combo.setFocus()  # moved on: it isn't taken back
    home.update_continue()
    qtbot.wait(2 * 30)
    assert focused(tab) is home.sort_combo and not home.start_focus.isActive()


def test_continue_playing_is_there_at_a_start_whatever_was_filtered(qtbot):
    """Filters are kept across restarts - they'd hide "Continue playing" right at the start."""
    from gamingcrypt.ui import view_state

    view_state.save("games", {"genre": "Racing", "platform": "", "decade": "", "sort": "name"})
    tab, service = tab_with(qtbot, games())
    home = tab.home
    assert home.genre_combo.currentData() == "Racing" and home.filtering()
    assert home.continue_card.isVisible()
    qtbot.waitUntil(lambda: focused(tab) is home.continue_card.play_button)
    home.decade_combo.setCurrentIndex(1)
    home.decade_combo.activated.emit(1)  # a filter chosen by hand: the results come first again
    assert not home.continue_card.isVisible()
    home.clear_filters()
    assert home.continue_card.isVisible()
    view_state.save("games", {"genre": "Racing", "platform": "", "decade": "", "sort": "name"})
    tab2, _ = tab_with(qtbot, games())
    tab2.home.clear_filters()  # cleared by hand at the start
    assert tab2.home.continue_card.isVisible() and not tab2.home.at_start


def test_the_highlight_waits_for_whats_new_to_close(qtbot, monkeypatch):
    from PySide6.QtWidgets import QMainWindow, QPushButton

    from gamingcrypt.ui import games_tab

    monkeypatch.setattr(games_tab, "START_FOCUS_MS", 10)
    window = QMainWindow()
    qtbot.addWidget(window)
    overlay = QPushButton("What's new - OK", window)
    covering = {"on": True}
    window.nav_root = lambda: overlay if covering["on"] else window
    tab = GamesTab(FakeService(games=games()))
    window.setCentralWidget(tab)
    window.show()
    overlay.setFocus()
    tab.games.update({g.appid: g for g in games()})
    tab.home.set_installed(tab.service.installed_games())
    qtbot.wait(60)
    assert focused(tab) is overlay and tab.home.start_focus.isActive()  # not taken from under it
    covering["on"] = False
    qtbot.waitUntil(lambda: focused(tab) is tab.home.continue_card.play_button)
    assert not tab.home.start_focus.isActive()


def test_no_highlight_once_another_page_is_open(qtbot, monkeypatch):
    from gamingcrypt.ui import games_tab

    monkeypatch.setattr(games_tab, "START_FOCUS_MS", 10)
    service = FakeService(games=games())
    tab = GamesTab(service)
    qtbot.addWidget(tab)
    tab.show()
    tab.games.update({g.appid: g for g in games()})
    tab.open_game(620)  # faster than the list: already on a game's page
    page = tab.currentWidget()
    tab.home.set_installed(service.installed_games())
    qtbot.wait(60)
    assert focused(tab) is not tab.home.continue_card.play_button and tab.currentWidget() is page
    assert not tab.home.start_focus.isActive()


def test_the_app_starts_on_the_games_tab(qtbot):
    from gamingcrypt.ui.shell import TABS, Shell

    shell = Shell({})
    qtbot.addWidget(shell)
    assert TABS[0] == "Games" and shell.current_tab == "Games"
