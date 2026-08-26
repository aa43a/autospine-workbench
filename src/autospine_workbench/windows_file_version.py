"""Bounded Windows VERSIONINFO access for executable identity checks."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path


MAX_VERSION_INFO_BYTES = 16 * 1024 * 1024
MAX_TRANSLATION_BYTES = 64
MAX_PRODUCT_NAME_CHARS = 64
_FIXED_INFO_DWORDS = 13
_FIXED_INFO_SIGNATURE = 0xFEEF04BD


class WindowsFileVersionError(ValueError):
    """Raised when embedded Windows version metadata is unavailable or unsafe."""


@dataclass(frozen=True, slots=True)
class WindowsFileVersion:
    """Product name and four-part file version from one VERSIONINFO resource."""

    product_name: str
    file_version: tuple[int, int, int, int]


def read_windows_file_version(path: str | Path) -> WindowsFileVersion:
    """Read bounded ProductName and VS_FIXEDFILEINFO through version.dll."""

    if os.name != "nt":
        raise WindowsFileVersionError("Windows VERSIONINFO is unavailable")
    try:
        import ctypes
        from ctypes import wintypes

        executable = Path(path)
        if not executable.is_absolute():
            raise OSError("VERSIONINFO path must be absolute")
        api = ctypes.WinDLL("version", use_last_error=True)
        _configure_api(api, ctypes, wintypes)
        ignored = wintypes.DWORD()
        size = api.GetFileVersionInfoSizeW(os.fspath(executable), ctypes.byref(ignored))
        if not 0 < size <= MAX_VERSION_INFO_BYTES:
            raise OSError("invalid VERSIONINFO size")
        buffer = ctypes.create_string_buffer(size)
        if not api.GetFileVersionInfoW(os.fspath(executable), 0, size, buffer):
            raise OSError("VERSIONINFO cannot be read")
        query = _query_factory(api, buffer, ctypes, wintypes)
        fixed_pointer, fixed_length = query("\\")
        fixed_bytes = _FIXED_INFO_DWORDS * ctypes.sizeof(wintypes.DWORD)
        _require_buffer_range(buffer, size, fixed_pointer, fixed_bytes, ctypes)
        if fixed_length < fixed_bytes:
            raise OSError("fixed VERSIONINFO is truncated")
        fixed_type = ctypes.POINTER(wintypes.DWORD * _FIXED_INFO_DWORDS)
        fixed = ctypes.cast(fixed_pointer, fixed_type).contents
        if fixed[0] != _FIXED_INFO_SIGNATURE:
            raise OSError("fixed VERSIONINFO signature is invalid")
        product = _read_product_name(query, buffer, size, ctypes, wintypes)
        version = _decode_file_version(fixed[2], fixed[3])
        return WindowsFileVersion(product_name=product, file_version=version)
    except WindowsFileVersionError:
        raise
    except (AttributeError, ImportError, OSError, TypeError, ValueError) as exc:
        raise WindowsFileVersionError(
            "Windows VERSIONINFO cannot be read safely"
        ) from exc


def _configure_api(api: object, ctypes: object, wintypes: object) -> None:
    api.GetFileVersionInfoSizeW.argtypes = [wintypes.LPCWSTR, wintypes.LPDWORD]
    api.GetFileVersionInfoSizeW.restype = wintypes.DWORD
    api.GetFileVersionInfoW.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.LPVOID,
    ]
    api.GetFileVersionInfoW.restype = wintypes.BOOL
    api.VerQueryValueW.argtypes = [
        wintypes.LPCVOID,
        wintypes.LPCWSTR,
        ctypes.POINTER(ctypes.c_void_p),
        wintypes.PUINT,
    ]
    api.VerQueryValueW.restype = wintypes.BOOL


def _query_factory(api: object, buffer: object, ctypes: object, wintypes: object):
    def query(key: str) -> tuple[int, int]:
        pointer, length = ctypes.c_void_p(), wintypes.UINT()
        found = api.VerQueryValueW(
            buffer, key, ctypes.byref(pointer), ctypes.byref(length)
        )
        if not found or not pointer.value:
            raise OSError(f"VERSIONINFO field is absent: {key}")
        return int(pointer.value), int(length.value)

    return query


def _read_product_name(query, buffer, size: int, ctypes: object, wintypes: object) -> str:
    pointer, length = query("\\VarFileInfo\\Translation")
    if length < 4 or length > MAX_TRANSLATION_BYTES or length % 4:
        raise OSError("VERSIONINFO translation is invalid")
    _require_buffer_range(buffer, size, pointer, length, ctypes)
    translation = ctypes.cast(
        pointer, ctypes.POINTER(wintypes.WORD * 2)
    ).contents
    key = f"\\StringFileInfo\\{translation[0]:04X}{translation[1]:04X}\\ProductName"
    pointer, length = query(key)
    if not 1 < length <= MAX_PRODUCT_NAME_CHARS:
        raise OSError("VERSIONINFO ProductName is invalid")
    byte_length = length * ctypes.sizeof(ctypes.c_wchar)
    _require_buffer_range(buffer, size, pointer, byte_length, ctypes)
    return ctypes.wstring_at(pointer, length).rstrip("\0")


def _require_buffer_range(
    buffer: object, size: int, pointer: int, length: int, ctypes: object
) -> None:
    start = ctypes.addressof(buffer)
    if length <= 0 or pointer < start or pointer > start + size - length:
        raise OSError("VERSIONINFO field points outside its buffer")


def _decode_file_version(ms: int, ls: int) -> tuple[int, int, int, int]:
    return ms >> 16, ms & 0xFFFF, ls >> 16, ls & 0xFFFF
