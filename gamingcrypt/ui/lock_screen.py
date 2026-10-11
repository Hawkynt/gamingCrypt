"""Start screen: unlock the VeraCrypt volume with the configured method - where there are more
users, first who it is (each has a code of their own, see gamingcrypt/users.py)."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from gamingcrypt.ui.secret_input import METHOD_LABELS, SecretInput
from gamingcrypt.ui.tasks import run_async
from gamingcrypt.ui.widgets import big_button, set_status
from gamingcrypt.unlock.veracrypt import UnlockResult, VeraCryptUnlocker


class LockScreen(QWidget):
    """Emits ``unlocked`` once the volume was mounted successfully."""

    unlocked = Signal()
    accepted = Signal(str)  # the code that worked (for the after-sleep check, see unlock/verifier)
    power_requested = Signal(str)  # "shutdown" / "restart" / "boot:<UEFI entry>"

    def __init__(self, unlocker: VeraCryptUnlocker, method: str, parent: QWidget | None = None,
                 users: list | None = None, unlocker_for=None, user_id: str | None = None):
        """users: who can log in (users.User), shown to choose from when there's more than one;
        unlocker_for(user) -> their unlocker. user_id: who is chosen at first."""
        super().__init__(parent)
        self.unlocker = unlocker
        self.busy = False
        self.users = list(users or [])
        self.unlocker_for = unlocker_for
        self.user = next((u for u in self.users if u.id == user_id), self.users[0] if self.users else None)
        if self.user is not None and unlocker_for is not None:
            self.unlocker, method = unlocker_for(self.user), self.user.method

        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 30, 40, 30)
        title = QLabel("🔒 GamingCrypt")
        title.setObjectName("title")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        # who: only where there's more than the admin
        self.user_buttons: dict[str, QWidget] = {}
        self.user_row = QWidget()
        chooser = QHBoxLayout(self.user_row)
        chooser.setContentsMargins(0, 0, 0, 0)
        chooser.addStretch()
        for user in self.users:
            button = big_button(user.name, choice=True)
            button.setChecked(user is self.user)
            button.clicked.connect(lambda _c=False, u=user: self.choose_user(u))
            chooser.addWidget(button)
            self.user_buttons[user.id] = button
        chooser.addStretch()
        layout.addWidget(self.user_row)
        self.user_row.setVisible(len(self.users) > 1)

        self.subtitle = QLabel("")
        self.subtitle.setObjectName("subtitle")
        self.subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.subtitle)
        self.input_box = QVBoxLayout()
        layout.addLayout(self.input_box, 1)
        self.input = None
        self._set_input(method)

        self.status = QLabel("")
        self.status.setObjectName("status")
        self.status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.status)

        self.skip_button = big_button("Continue without unlocking")
        self.skip_button.clicked.connect(self.unlocked.emit)
        layout.addWidget(self.skip_button, alignment=Qt.AlignmentFlag.AlignCenter)
        if unlocker.configured:
            self.skip_button.hide()
        else:
            set_status(self.status, "No VeraCrypt volume configured", error=True)

        # power: without unlocking (e.g. to start Windows instead)
        power = QHBoxLayout()
        power.addStretch()
        self.shutdown_button = big_button("⏻  Shut down")
        self.restart_button = big_button("↻  Restart")
        self.windows_button = big_button("⊞  Restart into Windows")
        self.shutdown_button.clicked.connect(lambda: self.power_requested.emit("shutdown"))
        self.restart_button.clicked.connect(lambda: self.power_requested.emit("restart"))
        self.windows_button.clicked.connect(self._boot_other)
        for button in (self.shutdown_button, self.restart_button, self.windows_button):
            power.addWidget(button)
        power.addStretch()
        layout.addLayout(power)
        self.other_system = None
        self.windows_button.hide()  # until another system was found

    def _set_input(self, method: str) -> None:
        """The pad for that method (each user has their own)."""
        if self.input is not None:
            self.input_box.removeWidget(self.input)
            self.input.deleteLater()
        self.input = SecretInput(method)
        self.method = self.input.method
        self.subtitle.setText(f"Enter your {METHOD_LABELS[self.method]}")
        self.input.secret_entered.connect(self._attempt)
        self.input.invalid.connect(lambda msg: set_status(self.status, msg, error=True))
        self.input_box.addWidget(self.input, 1)

    def choose_user(self, user) -> None:
        if self.busy:
            self.user_buttons[user.id].setChecked(user is self.user)
            return
        self.user = user
        for user_id, button in self.user_buttons.items():
            button.setChecked(user_id == user.id)
        if self.unlocker_for is not None:
            self.unlocker = self.unlocker_for(user)
        self._set_input(user.method)
        set_status(self.status, "")

    def set_systems(self, entries) -> None:
        """Offer the first other system (Windows preferred) - see system/boot.py."""
        entries = sorted(entries, key=lambda e: not e.windows)
        self.other_system = entries[0] if entries else None
        if self.other_system is not None:
            self.windows_button.setText(("⊞  " if self.other_system.windows else "↻  ")
                                        + f"Restart into {self.other_system.name}")
        self.windows_button.setVisible(self.other_system is not None)

    def _boot_other(self) -> None:
        if self.other_system is not None:
            self.power_requested.emit(f"boot:{self.other_system.num}")

    def show_error(self, message: str) -> None:
        set_status(self.status, message, error=True)

    def _attempt(self, secret: str) -> None:
        if self.busy:
            return
        self.busy = True
        self._secret = secret
        set_status(self.status, "Unlocking…")
        run_async(
            lambda: self.unlocker.unlock(secret),
            self._finished,
            lambda exc: self._finished(UnlockResult(False, str(exc))),
        )

    def _finished(self, result: UnlockResult) -> None:
        self.busy = False
        secret, self._secret = getattr(self, "_secret", ""), ""
        if result.success:
            set_status(self.status, result.message)
            self.input.clear()
            self.accepted.emit(secret)
            self.unlocked.emit()
        else:
            set_status(self.status, result.message, error=True)
            self.input.clear(error=True)
