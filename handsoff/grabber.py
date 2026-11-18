"""Kernel-level input grabbing via evdev.

Grabbing a device with ``EVIOCGRAB`` gives Hands Off *exclusive* access to it,
so no other application receives its events while a lock is active. This happens
below the display server, so it works identically under X11 and Wayland.

The grabber runs its read loop in a background thread and reports state changes
to the Qt side through thread-safe signals.
"""
import selectors
import threading
import time

from evdev import InputDevice, ecodes, list_devices
from PyQt5.QtCore import QObject, pyqtSignal


def _is_keyboard(dev):
    keys = dev.capabilities().get(ecodes.EV_KEY, [])
    return ecodes.KEY_A in keys and ecodes.KEY_Z in keys


def _is_pointer(dev):
    caps = dev.capabilities()
    keys = caps.get(ecodes.EV_KEY, [])
    return ecodes.BTN_LEFT in keys and ecodes.EV_REL in caps


KP_DIGITS = {getattr(ecodes, "KEY_KP%d" % d): str(d) for d in range(10)}
CODE_TIMEOUT = 3.0  # seconds allowed between PIN digits


class Grabber(QObject):
    locked = pyqtSignal()
    unlocked = pyqtSignal()
    error = pyqtSignal(str)

    def __init__(self, config):
        super().__init__()
        self.config = config
        self._running = False
        self._is_locked = False
        self._held = set()          # activation keys currently down (combo mode)
        self._seq = []              # recent activation-key presses (sequence mode)
        self._buffer = []           # recent key-down scancodes (unlock word)
        self._code_buf = ""         # recent Num-pad digits (toggle code)
        self._code_last = 0.0
        self._pending_toggle = None  # key whose release fires the toggle
        self._grabbed = []
        self._keyboards = []
        self._pointers = []
        self._selector = selectors.DefaultSelector()
        self._thread = None
        self.reload(config)

    def reload(self, config):
        """Recompute derived state after a config change (e.g. unlock word)."""
        self.config = config
        self._activation = {getattr(ecodes, k) for k in config["activation_keys"]}
        self._activation_order = [getattr(ecodes, k) for k in config["activation_keys"]]
        word = config["unlock_word"].lower()
        self._target = [
            ecodes.ecodes["KEY_" + c.upper()]
            for c in word
            if ("KEY_" + c.upper()) in ecodes.ecodes
        ]
        code = str(config.get("toggle_code") or "")
        self._code = code if code.isdigit() else ""
        self._code_buf = ""

    # --- lifecycle -----------------------------------------------------
    def start(self):
        try:
            self._open_devices()
        except PermissionError:
            self.error.emit(
                "No permission to read input devices.\n\n"
                "Add your user to the 'input' group:\n"
                "    sudo usermod -aG input $USER\n\n"
                "then log out and back in."
            )
            return False
        if not self._keyboards:
            self.error.emit("No accessible keyboard devices were found.")
            return False
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        return True

    def stop(self):
        self._running = False
        self._ungrab()

    def _open_devices(self):
        for path in list_devices():
            try:
                dev = InputDevice(path)
            except OSError:
                continue
            if _is_keyboard(dev):
                self._keyboards.append(dev)
            elif _is_pointer(dev):
                self._pointers.append(dev)
            else:
                dev.close()
        for dev in self._keyboards + self._pointers:
            self._selector.register(dev, selectors.EVENT_READ)

    # --- main loop -----------------------------------------------------
    def _loop(self):
        while self._running:
            for key, _ in self._selector.select(timeout=0.5):
                dev = key.fileobj
                try:
                    for event in dev.read():
                        if event.type == ecodes.EV_KEY:
                            self._handle_key(event)
                except OSError:
                    pass

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
        targets = list(self._keyboards)
        if self.config["grab_mouse"]:
            targets += self._pointers
        for dev in targets:
            try:
                dev.grab()
                self._grabbed.append(dev)
            except OSError:
                pass
        self._is_locked = True
        self._held.clear()
        self._seq.clear()
        self._buffer.clear()
        self.locked.emit()

    def unlock(self):
        if not self._is_locked:
            return
        self._ungrab()
        self._is_locked = False
        self._held.clear()
        self._seq.clear()
        self.unlocked.emit()

    def _ungrab(self):
        for dev in self._grabbed:
            try:
                dev.ungrab()
            except OSError:
                pass
        self._grabbed = []

    @property
    def is_locked(self):
        return self._is_locked
