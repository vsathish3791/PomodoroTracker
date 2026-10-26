"""A system-wide keyboard shortcut (Windows only), e.g. Ctrl+Alt+P for Start / Pause.

Windows sends a WM_HOTKEY message to our window when the keys are pressed in
any app; a native event filter catches it and calls the callback.
"""

import ctypes
import sys
from ctypes import wintypes

from PySide6.QtCore import QAbstractNativeEventFilter
from PySide6.QtGui import QKeySequence

WM_HOTKEY = 0x0312
MOD_ALT, MOD_CONTROL, MOD_SHIFT, MOD_WIN, MOD_NOREPEAT = 0x1, 0x2, 0x4, 0x8, 0x4000
HOTKEY_ID = 0xB0B0


def parse_shortcut(text: str) -> tuple[int, int] | None:
    """'Ctrl+Alt+P' -> (Windows modifier flags, virtual-key code), or None if unsupported.

    Supported keys: letters, digits, F1-F24 and Space, with at least Ctrl, Alt or Win
    (a plain letter would stop you from typing it anywhere else).
    """
    parts = [p.strip().lower() for p in text.split("+") if p.strip()]
    if len(parts) < 2:
        return None
    *modifiers, key = parts
    flags = 0
    for mod in modifiers:
        flag = {"ctrl": MOD_CONTROL, "alt": MOD_ALT, "shift": MOD_SHIFT,
                "meta": MOD_WIN, "win": MOD_WIN}.get(mod)
        if flag is None:
            return None
        flags |= flag
    if not flags & (MOD_CONTROL | MOD_ALT | MOD_WIN):
        return None

    if len(key) == 1 and key.isalnum():
        vk = ord(key.upper())                   # 'A'-'Z' and '0'-'9' match their VK codes
    elif key.startswith("f") and key[1:].isdigit() and 1 <= int(key[1:]) <= 24:
        vk = 0x70 + int(key[1:]) - 1            # VK_F1 = 0x70
    elif key == "space":
        vk = 0x20
    else:
        return None
    return flags, vk


class _MSG(ctypes.Structure):
    _fields_ = [("hwnd", wintypes.HWND), ("message", wintypes.UINT),
                ("wParam", wintypes.WPARAM), ("lParam", wintypes.LPARAM),
                ("time", wintypes.DWORD), ("pt", wintypes.POINT)]


class GlobalHotkey(QAbstractNativeEventFilter):
    def __init__(self, app, window_handle: int, callback):
        super().__init__()
        self.callback = callback
        self.hwnd = window_handle
        self.registered = False
        self.available = sys.platform == "win32"
        if self.available:
            self.user32 = ctypes.windll.user32
            self.user32.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int,
                                                   wintypes.UINT, wintypes.UINT]
            self.user32.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
            app.installNativeEventFilter(self)

    def register(self, shortcut: str) -> bool:
        """Register the shortcut, replacing any previous one. False if unsupported or taken."""
        self.unregister()
        parsed = parse_shortcut(normalise(shortcut))
        if not self.available or parsed is None:
            return False
        flags, vk = parsed
        self.registered = bool(self.user32.RegisterHotKey(self.hwnd, HOTKEY_ID,
                                                          flags | MOD_NOREPEAT, vk))
        return self.registered

    def unregister(self):
        if self.available and self.registered:
            self.user32.UnregisterHotKey(self.hwnd, HOTKEY_ID)
        self.registered = False

    def nativeEventFilter(self, event_type, message):
        if event_type in (b"windows_generic_MSG", b"windows_dispatcher_MSG",
                          "windows_generic_MSG", "windows_dispatcher_MSG"):
            msg = _MSG.from_address(int(message))
            if msg.message == WM_HOTKEY and msg.wParam == HOTKEY_ID:
                self.callback()
                return True, 0
        return False, 0


def normalise(shortcut: str) -> str:
    """Qt writes shortcuts like 'Ctrl+Alt+P'; make sure we read Qt's own spelling."""
    return QKeySequence(shortcut).toString(QKeySequence.PortableText) or shortcut
