"""Qt system-tray front end for Hands Off."""
import shutil
import signal
import subprocess
import sys
from pathlib import Path

from PyQt5.QtCore import QRegExp, QTimer
from PyQt5.QtGui import QIcon, QRegExpValidator
from PyQt5.QtWidgets import (
    QAction,
    QApplication,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLineEdit,
    QMenu,
    QMessageBox,
    QSystemTrayIcon,
    QVBoxLayout,
)

from .config import load_config, save_config
from .grabber import Grabber

ICON_DIR = Path(__file__).parent / "resources"


SOUND_DIR = ICON_DIR / "sounds"
APP_NAME = "Hands Off"


def icon(name):
    return QIcon(str(ICON_DIR / name))


def play(clip):
    """Play a bundled clip without blocking (pw-play, paplay or ffplay)."""
    path = SOUND_DIR / clip
    if not path.exists():
        return
    for cmd in (["pw-play"], ["paplay"], ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet"]):
        if shutil.which(cmd[0]):
            subprocess.Popen(cmd + [str(path)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return


class Notifier:
    """Desktop notifications via notify-send, named "Hands Off" with its own icon.

    Qt's QSystemTrayIcon.showMessage reports the interpreter (python3) as the
    sender on Plasma, so we go through libnotify instead and fall back to Qt.
    Each new notification replaces the previous one rather than stacking.
    """

    def __init__(self, tray):
        self.tray = tray
        self.last_id = None
        self.has_cli = bool(shutil.which("notify-send"))

    def show(self, title, body, icon_file, timeout_ms):
        if not self.has_cli:
            self.tray.showMessage(title, body, icon(icon_file), timeout_ms)
            return
        cmd = ["notify-send", "--app-name", APP_NAME, "--icon", str(ICON_DIR / icon_file),
               "--expire-time", str(timeout_ms), "--hint", "string:desktop-entry:handsoff",
               "--transient", "--print-id"]
        if self.last_id:
            cmd += ["--replace-id", self.last_id]
        try:
            out = subprocess.run(cmd + [title, body], capture_output=True, text=True, timeout=3)
            self.last_id = out.stdout.strip() or None
        except (OSError, subprocess.SubprocessError):
            self.tray.showMessage(title, body, icon(icon_file), timeout_ms)


class SettingsDialog(QDialog):
    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Hands Off — Settings")
        self.word = QLineEdit(config["unlock_word"])
        self.code = QLineEdit(config.get("toggle_code", ""))
        self.code.setValidator(QRegExpValidator(QRegExp(r"\d{0,8}")))
        self.code.setPlaceholderText("e.g. 4827 (blank = off)")
        self.allow_word = QCheckBox("Unlock by typing the word")
        self.allow_word.setChecked(config["allow_unlock_word"])
        self.allow_tray = QCheckBox("Unlock by clicking the tray icon")
        self.allow_tray.setChecked(config["allow_unlock_tray"])
        self.grab_mouse = QCheckBox("Also lock the mouse (tray click won't work while locked)")
        self.grab_mouse.setChecked(config["grab_mouse"])
        self.notify = QCheckBox("Show notifications")
        self.notify.setChecked(config["notifications"])
        self.sounds = QCheckBox("Play voice announcements")
        self.sounds.setChecked(config.get("sounds", True))

        form = QFormLayout()
        form.addRow("Num-pad toggle code:", self.code)
        form.addRow("Unlock word:", self.word)
        form.addRow(self.allow_word)
        form.addRow(self.allow_tray)
        form.addRow(self.grab_mouse)
        form.addRow(self.notify)
        form.addRow(self.sounds)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

    def values(self):
        return {
            "unlock_word": self.word.text().strip() or "quit",
            "toggle_code": self.code.text().strip() if len(self.code.text().strip()) >= 4 else "",
            "allow_unlock_word": self.allow_word.isChecked(),
            "allow_unlock_tray": self.allow_tray.isChecked(),
            "grab_mouse": self.grab_mouse.isChecked(),
            "notifications": self.notify.isChecked(),
            "sounds": self.sounds.isChecked(),
        }


class HandsOffApp:
    def __init__(self):
        self.config = load_config()
        self.app = QApplication(sys.argv)
        self.app.setApplicationName("handsoff")
        self.app.setApplicationDisplayName(APP_NAME)
        self.app.setDesktopFileName("handsoff")
        self.app.setQuitOnLastWindowClosed(False)

        self.grabber = Grabber(self.config)
        self.grabber.locked.connect(self._on_locked)
        self.grabber.unlocked.connect(self._on_unlocked)
        self.grabber.error.connect(self._on_error)

        self.tray = QSystemTrayIcon(icon("handsoff.svg"))
        self.tray.setToolTip("Hands Off — ready")
        self.tray.activated.connect(self._on_tray_activated)
        self._build_menu()
        self.tray.show()
        self.notifier = Notifier(self.tray)

    # --- run -----------------------------------------------------------
    def run(self):
        signal.signal(signal.SIGINT, signal.SIG_DFL)
        # Keep the Python interpreter responsive to signals during exec_().
        self._ticker = QTimer()
        self._ticker.start(500)
        self._ticker.timeout.connect(lambda: None)

        self.grabber.start()
        return self.app.exec_()

    def _build_menu(self):
        menu = QMenu()
        self.act_lock = QAction("Lock now", menu)
        self.act_lock.triggered.connect(self.grabber.lock)
        self.act_unlock = QAction("Unlock", menu)
        self.act_unlock.triggered.connect(self.grabber.unlock)
        self.act_unlock.setEnabled(False)

        act_settings = QAction("Settings…", menu)
        act_settings.triggered.connect(self._open_settings)
        act_about = QAction("About", menu)
        act_about.triggered.connect(self._about)
        act_quit = QAction("Quit Hands Off", menu)
        act_quit.triggered.connect(self._quit)

        menu.addAction(self.act_lock)
        menu.addAction(self.act_unlock)
        menu.addSeparator()
        menu.addAction(act_settings)
        menu.addAction(act_about)
        menu.addSeparator()
        menu.addAction(act_quit)
        self.menu = menu
        self.tray.setContextMenu(menu)

    # --- callbacks -----------------------------------------------------
    def _on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.Trigger:  # left click
            if self.grabber.is_locked:
                if self.config["allow_unlock_tray"]:
                    self.grabber.unlock()
            else:
                self.grabber.lock()

    def _on_locked(self):
        self.tray.setIcon(icon("handsoff-locked.svg"))
        self.tray.setToolTip("Hands Off — LOCKED")
        self.act_lock.setEnabled(False)
        self.act_unlock.setEnabled(True)
        if self.config.get("sounds", True):
            play("locked.ogg")
        if self.config["notifications"]:
            ways = []
            if self.config.get("toggle_code"):
                ways.append("enter your code on the number pad")
            if self.config["allow_unlock_word"]:
                ways.append("type \u201c%s\u201d" % self.config["unlock_word"])
            if self.config["allow_unlock_tray"] and not self.config["grab_mouse"]:
                ways.append("click the tray icon")
            what = "Keyboard and mouse" if self.config["grab_mouse"] else "Keyboard"
            body = "%s locked." % what
            if ways:
                body += "\nTo unlock, " + " or ".join(ways) + "."
            self.notifier.show("\U0001F512  Locked", body, "handsoff-locked.svg", 5000)

    def _on_unlocked(self):
        self.tray.setIcon(icon("handsoff.svg"))
        self.tray.setToolTip("Hands Off — ready")
        self.act_lock.setEnabled(True)
        self.act_unlock.setEnabled(False)
        if self.config.get("sounds", True):
            play("unlocked.ogg")
        if self.config["notifications"]:
            self.notifier.show("\U0001F513  Unlocked", "Keyboard and mouse are back to normal.", "handsoff.svg", 3000)

    def _on_error(self, msg):
        QMessageBox.warning(None, "Hands Off", msg)

    def _open_settings(self):
        dlg = SettingsDialog(self.config)
        if dlg.exec_() == QDialog.Accepted:
            self.config.update(dlg.values())
            save_config(self.config)
            self.grabber.reload(self.config)

    def _about(self):
        keys = " + ".join(k.replace("KEY_KP", "Num-pad ") for k in self.config["activation_keys"])
        QMessageBox.information(
            None,
            "Hands Off",
            "Hands Off — toddler-proof keyboard & mouse lock.\n\n"
            "Activate:  %s%s\n"
            "Unlock:    type '%s'%s"
            % (
                keys,
                "  or your Num-pad code (toggles)" if self.config.get("toggle_code") else "",
                self.config["unlock_word"],
                "  or click this icon" if self.config["allow_unlock_tray"] else "",
            ),
        )

    def _quit(self):
        self.grabber.stop()
        self.app.quit()


def main():
    app = HandsOffApp()
    sys.exit(app.run())


if __name__ == "__main__":
    main()
