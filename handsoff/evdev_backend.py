"""Linux backend: kernel-level input grabbing via evdev (EVIOCGRAB).

A grabbed device delivers its events only to Hands Off, below the display
server, so the lock behaves the same under X11 and Wayland.
"""
import selectors
import threading

from evdev import InputDevice, ecodes, list_devices

from .grabber import Grabber, KeyEvent


def _is_keyboard(dev):
    keys = dev.capabilities().get(ecodes.EV_KEY, [])
    return ecodes.KEY_A in keys and ecodes.KEY_Z in keys


def _is_pointer(dev):
    caps = dev.capabilities()
    keys = caps.get(ecodes.EV_KEY, [])
    return ecodes.BTN_LEFT in keys and ecodes.EV_REL in caps


class EvdevGrabber(Grabber):
    def __init__(self, config):
        super().__init__(config)
        self._running = False
        self._grabbed = []
        self._keyboards = []
        self._pointers = []
        self._selector = selectors.DefaultSelector()
        self._thread = None

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
        self._unblock()

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

    def _loop(self):
        while self._running:
            for key, _ in self._selector.select(timeout=0.5):
                try:
                    for event in key.fileobj.read():
                        if event.type == ecodes.EV_KEY:
                            self._handle_key(KeyEvent(event.code, event.value))
                except OSError:
                    pass

    def _block(self):
        targets = list(self._keyboards)
        if self.config["grab_mouse"]:
            targets += self._pointers
        for dev in targets:
            try:
                dev.grab()
                self._grabbed.append(dev)
            except OSError:
                pass

    def _unblock(self):
        for dev in self._grabbed:
            try:
                dev.ungrab()
            except OSError:
                pass
        self._grabbed = []
