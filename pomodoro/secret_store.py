"""Keep secrets (the Notion token) encrypted at rest.

On Windows this uses DPAPI (CryptProtectData): only your Windows user account on this
PC can decrypt the value, so copying the database file elsewhere doesn't expose it.
On other systems the value is only base64-encoded (and labelled as such).
"""

import base64
import ctypes
import sys
from ctypes import wintypes

PREFIX_DPAPI = "dpapi:"
PREFIX_PLAIN = "b64:"


class _Blob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]


def _to_blob(data: bytes) -> _Blob:
    buffer = ctypes.create_string_buffer(data, len(data))
    return _Blob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_char)))


def _from_blob(blob: _Blob) -> bytes:
    data = ctypes.string_at(blob.pbData, blob.cbData)
    ctypes.windll.kernel32.LocalFree(blob.pbData)
    return data


def protect(text: str) -> str:
    """Encrypt text for storage. Empty text -> empty string."""
    if not text:
        return ""
    raw = text.encode("utf-8")
    if sys.platform == "win32":
        source, result = _to_blob(raw), _Blob()
        if ctypes.windll.crypt32.CryptProtectData(ctypes.byref(source), "PomodoroTracker", None,
                                                  None, None, 0, ctypes.byref(result)):
            return PREFIX_DPAPI + base64.b64encode(_from_blob(result)).decode("ascii")
    return PREFIX_PLAIN + base64.b64encode(raw).decode("ascii")


def unprotect(stored: str) -> str:
    """Decrypt a value made by protect(). Returns '' if it can't be read here."""
    if not stored:
        return ""
    if stored.startswith(PREFIX_PLAIN):
        return base64.b64decode(stored[len(PREFIX_PLAIN):]).decode("utf-8")
    if stored.startswith(PREFIX_DPAPI) and sys.platform == "win32":
        source, result = _to_blob(base64.b64decode(stored[len(PREFIX_DPAPI):])), _Blob()
        if ctypes.windll.crypt32.CryptUnprotectData(ctypes.byref(source), None, None, None,
                                                    None, 0, ctypes.byref(result)):
            return _from_blob(result).decode("utf-8")
    return ""
