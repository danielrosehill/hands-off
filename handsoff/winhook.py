"""Windows backend: low-level keyboard and mouse hooks (WH_KEYBOARD_LL / WH_MOUSE_LL).

The hooks see every key and mouse event in the session and swallow them while
locked. Windows never lets an application block Ctrl+Alt+Del (the secure
attention sequence) or Win+L, and by design (UIPI) a non-elevated hook does not
see input aimed at an elevated window that has focus.

Keys are identified by hardware scan code, which matches Hands Off's Linux key
codes (see keycodes.py), so Num-pad digits are recognised regardless of
NumLock and never confused with the top-row digits.
"""
import ctypes
import threading
from ctypes import wintypes

from .grabber import Grabber, KeyEvent
from .keycodes import EXTENDED

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

WH_KEYBOARD_LL, WH_MOUSE_LL = 13, 14
WM_KEYDOWN, WM_KEYUP, WM_SYSKEYDOWN, WM_SYSKEYUP = 0x0100, 0x0101, 0x0104, 0x0105
WM_QUIT = 0x0012
LLKHF_EXTENDED, LLKHF_INJECTED = 0x01, 0x10
LLMHF_INJECTED = 0x01

LRESULT = ctypes.c_ssize_t
HOOKPROC = ctypes.WINFUNCTYPE(LRESULT, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)


class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [("vkCode", wintypes.DWORD), ("scanCode", wintypes.DWORD),
                ("flags", wintypes.DWORD), ("time", wintypes.DWORD),
                ("dwExtraInfo", ctypes.c_size_t)]


class MSLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [("pt", wintypes.POINT), ("mouseData", wintypes.DWORD),
                ("flags", wintypes.DWORD), ("time", wintypes.DWORD),
                ("dwExtraInfo", ctypes.c_size_t)]


user32.SetWindowsHookExW.argtypes = [ctypes.c_int, HOOKPROC, wintypes.HINSTANCE, wintypes.DWORD]
user32.SetWindowsHookExW.restype = wintypes.HHOOK
user32.CallNextHookEx.argtypes = [wintypes.HHOOK, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM]
user32.CallNextHookEx.restype = LRESULT
user32.UnhookWindowsHookEx.argtypes = [wintypes.HHOOK]
user32.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
user32.PostThreadMessageW.argtypes = [wintypes.DWORD, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
kernel32.GetModuleHandleW.restype = wintypes.HMODULE


class WindowsGrabber(Grabber):
    def __init__(self, config):
        super().__init__(config)
        self._thread = None
        self._thread_id = None
        self._ready = threading.Event()
        self._hook_error = None
        # Keep references so the callbacks are not garbage-collected.
        self._kb_proc = HOOKPROC(self._kb_hook)
        self._ms_proc = HOOKPROC(self._ms_hook)

    def start(self):
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        self._ready.wait(5)
        if self._hook_error:
            self.error.emit(self._hook_error)
            return False
        return True

    def stop(self):
        if self._thread_id:
            user32.PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)

    def _run(self):
        self._thread_id = kernel32.GetCurrentThreadId()
        hmod = kernel32.GetModuleHandleW(None)
        kb = user32.SetWindowsHookExW(WH_KEYBOARD_LL, self._kb_proc, hmod, 0)
        ms = user32.SetWindowsHookExW(WH_MOUSE_LL, self._ms_proc, hmod, 0)
        if not kb:
            self._hook_error = "Could not install the keyboard hook (error %d)." % ctypes.get_last_error()
        self._ready.set()
        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            pass
        for h in (kb, ms):
            if h:
                user32.UnhookWindowsHookEx(h)

    def _kb_hook(self, n_code, w_param, l_param):
        if n_code == 0:
            info = ctypes.cast(l_param, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
            if not info.flags & LLKHF_INJECTED:
                was_locked = self._is_locked
                value = 1 if w_param in (WM_KEYDOWN, WM_SYSKEYDOWN) else 0
                code = info.scanCode | (EXTENDED if info.flags & LLKHF_EXTENDED else 0)
                try:
                    self._handle_key(KeyEvent(code, value))
                except Exception:  # never let an exception escape a hook
                    pass
                # Swallow based on the state *before* this event: the key-up
                # that triggers a lock still reaches the app (no stuck key),
                # and the one that triggers an unlock does not.
                if was_locked:
                    return 1
        return user32.CallNextHookEx(None, n_code, w_param, l_param)

    def _ms_hook(self, n_code, w_param, l_param):
        if n_code == 0 and self._is_locked and self.config["grab_mouse"]:
            return 1
        return user32.CallNextHookEx(None, n_code, w_param, l_param)
