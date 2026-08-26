"""Canonical Chrome/Chromium version identity with bounded evidence reads."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import re
import subprocess
import threading

from .windows_file_version import WindowsFileVersionError, read_windows_file_version


MAX_VERSION_OUTPUT_BYTES = 4 * 1024
VERSION_TIMEOUT_SECONDS = 5.0
KILL_GRACE_SECONDS = 1.0
VERSION_IDENTITY_HASH_SEMANTICS = (
    "version_output_sha256 hashes canonical UTF-8 '<browser> <four-part-version>\\n' "
    "identity bytes derived from Windows VERSIONINFO or bounded process output"
)
_VERSION_PATTERNS = (
    (
        "google-chrome",
        re.compile(
            r"Google Chrome(?: for Testing)? "
            r"(?P<version>[0-9]{1,6}(?:\.[0-9]{1,6}){3})"
        ),
    ),
    (
        "chromium",
        re.compile(
            r"Chromium (?P<version>[0-9]{1,6}(?:\.[0-9]{1,6}){3})"
            r"(?: built on [^\r\n]{1,160})?"
        ),
    ),
)
_CANONICAL_LABELS = {"google-chrome": "Google Chrome", "chromium": "Chromium"}
_WINDOWS_PRODUCTS = {"Google Chrome", "Google Chrome for Testing", "Chromium"}


class BrowserVersionIdentityError(ValueError):
    """Raised when a browser version identity cannot be established safely."""


@dataclass(frozen=True, slots=True)
class BrowserVersionIdentity:
    """Parsed fields plus canonical bytes hashed by the public snapshot."""

    family: str
    reported_version: str
    canonical_bytes: bytes


def identify_browser_version(path: Path) -> BrowserVersionIdentity:
    """Identify a browser and canonicalize source evidence before hashing."""

    evidence = _version_evidence(path)
    family, reported_version = _parse_version_output(evidence)
    canonical = f"{_CANONICAL_LABELS[family]} {reported_version}\n".encode("utf-8")
    return BrowserVersionIdentity(family, reported_version, canonical)


def _version_evidence(path: Path) -> bytes:
    if os.name != "nt":
        return _bounded_version_output(path)
    try:
        info = read_windows_file_version(path)
        if info.product_name not in _WINDOWS_PRODUCTS:
            raise BrowserVersionIdentityError(
                "Windows VERSIONINFO does not identify Google Chrome or Chromium"
            )
        version = ".".join(map(str, info.file_version))
        return f"{info.product_name} {version}\n".encode("utf-8")
    except (BrowserVersionIdentityError, WindowsFileVersionError) as info_error:
        try:
            return _bounded_version_output(path)
        except BrowserVersionIdentityError as command_error:
            failures = ExceptionGroup(
                "browser version identity failures", [info_error, command_error]
            )
            raise BrowserVersionIdentityError(
                "browser version is unavailable from Windows VERSIONINFO and command"
            ) from failures


def _bounded_version_output(path: Path) -> bytes:
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
    try:
        process = subprocess.Popen(
            [os.fspath(path), "--version"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            shell=False,
            cwd=os.fspath(path.parent),
            close_fds=True,
            creationflags=creationflags,
        )
    except OSError as exc:
        raise BrowserVersionIdentityError(
            "browser version command could not be started"
        ) from exc
    if process.stdout is None:  # pragma: no cover - guaranteed by PIPE
        process.kill()
        raise BrowserVersionIdentityError("browser version output is unavailable")
    output, overflow = bytearray(), threading.Event()
    read_failed = threading.Event()

    def read_output() -> None:
        try:
            while chunk := process.stdout.read(1024):
                remaining = MAX_VERSION_OUTPUT_BYTES + 1 - len(output)
                if remaining > 0:
                    output.extend(chunk[:remaining])
                if len(output) > MAX_VERSION_OUTPUT_BYTES or len(chunk) > remaining:
                    overflow.set()
                    process.kill()
        except (OSError, ValueError):
            read_failed.set()

    reader = threading.Thread(target=read_output, daemon=True)
    reader.start()
    timed_out = False
    try:
        return_code = process.wait(timeout=VERSION_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        timed_out = True
        process.kill()
        try:
            return_code = process.wait(timeout=KILL_GRACE_SECONDS)
        except subprocess.TimeoutExpired:
            return_code = None
    reader.join(KILL_GRACE_SECONDS)
    if reader.is_alive():
        process.stdout.close()
        reader.join(KILL_GRACE_SECONDS)
    elif not process.stdout.closed:
        process.stdout.close()
    if timed_out:
        raise BrowserVersionIdentityError("browser version command timed out")
    if reader.is_alive() or read_failed.is_set():
        raise BrowserVersionIdentityError("browser version output could not be read")
    if overflow.is_set():
        raise BrowserVersionIdentityError("browser version output exceeds its limit")
    if return_code != 0:
        raise BrowserVersionIdentityError("browser version command failed")
    return bytes(output)


def _parse_version_output(output: bytes) -> tuple[str, str]:
    try:
        text = output.decode("utf-8").strip()
    except UnicodeError as exc:
        raise BrowserVersionIdentityError(
            "browser version output is not valid UTF-8"
        ) from exc
    for family, pattern in _VERSION_PATTERNS:
        match = pattern.fullmatch(text)
        if match is not None:
            return family, match.group("version")
    raise BrowserVersionIdentityError(
        "browser must report itself as Google Chrome or Chromium"
    )
