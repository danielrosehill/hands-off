"""Input locking: shared key logic plus per-platform backends.

``Grabber`` holds the platform-neutral logic (activation combo, Num-pad toggle
code, unlock word) and Qt signals. Backends only deliver key events and
block/unblock input:

* ``EvdevGrabber`` (Linux) grabs devices with ``EVIOCGRAB`` below the display
  server, so it works the same under X11 and Wayland.
* ``WindowsGrabber`` (``winhook.py``) installs low-level keyboard/mouse hooks
  and swallows events while locked.

``make_grabber()`` picks the right one.
"""
import sys
import time

from PyQt5.QtCore import QObject, pyqtSignal

from . import keycodes
from .keycodes import KP_DIGITS

CODE_TIMEOUT = 3.0  # seconds allowed between PIN digits


class KeyEvent:
    __slots__ = ("code", "value")

    def __init__(self, code, value):
        self.code = code    # keycodes value
        self.value = value  # 0 = up, 1 = down, 2 = autorepeat


class Grabber(QObject):
    locked = pyqtSignal()
    unlocked = pyqtSignal()
    error = pyqtSignal(str)

    def __init__(self, config):
        super().__init__()
        self.config = config
        self._is_locked = False
        self._held = set()          # activation keys currently down (combo mode)
        self._seq = []              # recent activation-key presses (sequence mode)
        self._buffer = []           # recent key-down scancodes (unlock word)
        self._code_buf = ""         # recent Num-pad digits (toggle code)
        self._code_last = 0.0
        self._pending_toggle = None  # key whose release fires the toggle
        self.reload(config)

    def reload(self, config):
        """Recompute derived state after a config change (e.g. unlock word)."""
        self.config = config
        names = config["activation_keys"]
        self._activation_order = [keycodes.code(k) for k in names if keycodes.code(k) is not None]
        self._activation = set(self._activation_order)
        word = config["unlock_word"].lower()
        self._target = [keycodes.code("KEY_" + c.upper()) for c in word
                        if keycodes.code("KEY_" + c.upper()) is not None]
        code = str(config.get("toggle_code") or "")
        self._code = code if code.isdigit() else ""
        self._code_buf = ""

    # --- backend hooks ------------------------------------------------
    def start(self):
        raise NotImplementedError

    def stop(self):
        pass

    def _block(self):
        """Start blocking input (called on lock)."""

    def _unblock(self):
        """Stop blocking input (called on unlock)."""

    def _handle_key(self, event):
        # event.value: 0 = up, 1 = down, 2 = autorepeat
        if self._pending_toggle is not None:
            # Toggle on release of the last PIN digit, so the key-up reaches the
            # compositor before/after the grab and no key is left "stuck".
            if event.code == self._pending_toggle and event.value == 0:
                self._pending_toggle = None
                self.unlock() if self._is_locked else self.lock()
            return
        if self._detect_code(event):
            return
        if self._is_locked:
            self._detect_unlock(event)
        else:
            self._detect_activation(event)

    def _detect_activation(self, event):
        if event.code not in self._activation:
            return
        if self.config["activation_mode"] == "sequence":
            if event.value == 1:
                self._seq.append(event.code)
                self._seq = self._seq[-len(self._activation_order):]
                if self._seq == self._activation_order:
                    self.lock()
            return
        # combo: both keys held at once
        if event.value == 1:
            self._held.add(event.code)
        elif event.value == 0:
            self._held.discard(event.code)
        if self._held >= self._activation:
            self.lock()

    def _detect_code(self, event):
        """Track the Num-pad toggle PIN. Returns True when it just matched."""
        if not self._code or event.value != 1:
            return False
        digit = KP_DIGITS.get(event.code)
        if digit is None:
            self._code_buf = ""
            return False
        now = time.monotonic()
        if now - self._code_last > CODE_TIMEOUT:
            self._code_buf = ""
        self._code_last = now
        self._code_buf = (self._code_buf + digit)[-len(self._code):]
        if self._code_buf == self._code:
            self._code_buf = ""
            self._pending_toggle = event.code
            return True
        return False

    def _detect_unlock(self, event):
        if not self.config["allow_unlock_word"] or event.value != 1:
            return
        self._buffer.append(event.code)
        self._buffer = self._buffer[-len(self._target):]
        if self._target and self._buffer == self._target:
            self.unlock()

    # --- lock / unlock -------------------------------------------------
    def lock(self):
        if self._is_locked:
            return
        self._block()
        self._is_locked = True
        self._held.clear()
        self._seq.clear()
        self._buffer.clear()
        self.locked.emit()

    def unlock(self):
        if not self._is_locked:
            return
        self._unblock()
        self._is_locked = False
        self._held.clear()
        self._seq.clear()
        self.unlocked.emit()

    @property
    def is_locked(self):
        return self._is_locked


def make_grabber(config):
    if sys.platform == "win32":
        from .winhook import WindowsGrabber
        return WindowsGrabber(config)
    from .evdev_backend import EvdevGrabber
    return EvdevGrabber(config)
