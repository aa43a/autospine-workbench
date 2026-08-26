"""Canonical Chrome/Chromium version identity with bounded evidence reads."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
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
_REPORTED_VERSION = re.compile(r"^[0-9]{1,6}(?:\.[0-9]{1,6}){3}$")
_POSIX_TERMINATE_SIGNAL = getattr(signal, "SIGTERM", 15)
_POSIX_KILL_SIGNAL = getattr(signal, "SIGKILL", 9)


class BrowserVersionIdentityError(ValueError):
    """Raised when a browser version identity cannot be established safely."""


@dataclass(frozen=True, slots=True)
class BrowserVersionIdentity:
    """Parsed fields plus canonical bytes hashed by the public snapshot."""

    family: str
    reported_version: str
    canonical_bytes: bytes


def canonical_browser_version_identity_bytes(
    family: str, reported_version: str,
) -> bytes:
    """Return the only canonical bytes accepted for a browser identity."""

    if type(family) is not str or family not in _CANONICAL_LABELS \
            or type(reported_version) is not str \
            or _REPORTED_VERSION.fullmatch(reported_version) is None:
        raise BrowserVersionIdentityError("browser version identity is invalid")
    return f"{_CANONICAL_LABELS[family]} {reported_version}\n".encode("utf-8")


def browser_version_identity_sha256(family: str, reported_version: str) -> str:
    """Hash canonical family/version identity bytes without external I/O."""

    canonical = canonical_browser_version_identity_bytes(family, reported_version)
    return hashlib.sha256(canonical).hexdigest()


def identify_browser_version(path: Path) -> BrowserVersionIdentity:
    """Identify a browser and canonicalize source evidence before hashing."""

    evidence = _version_evidence(path)
    family, reported_version = _parse_version_output(evidence)
    canonical = canonical_browser_version_identity_bytes(family, reported_version)
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
    except (BrowserVersionIdentityError, WindowsFileVersionError) as exc:
        raise BrowserVersionIdentityError(
            "browser requires valid Chrome or Chromium Windows VERSIONINFO"
        ) from exc


def _bounded_version_output(path: Path) -> bytes:
    launch_options = (
        {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0)}
        if os.name == "nt" else {"start_new_session": True}
    )
    try:
        process = subprocess.Popen(
            [os.fspath(path), "--version"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            shell=False,
            cwd=os.fspath(path.parent),
            close_fds=True,
            **launch_options,
        )
    except OSError as exc:
        raise BrowserVersionIdentityError(
            "browser version command could not be started"
        ) from exc
    if process.stdout is None:  # pragma: no cover - guaranteed by PIPE
        failure = BrowserVersionIdentityError(
            "browser version output is unavailable"
        )
        try:
            _cleanup_version_process(process)
        except Exception as cleanup_error:
            failure.add_note(
                "Browser version cleanup also failed: "
                f"{cleanup_error}"
            )
        raise failure
    output, overflow = bytearray(), threading.Event()
    read_failed = threading.Event()
    read_errors: list[BaseException] = []

    def read_output() -> None:
        try:
            while chunk := process.stdout.read(1024):
                remaining = MAX_VERSION_OUTPUT_BYTES + 1 - len(output)
                if remaining > 0:
                    output.extend(chunk[:remaining])
                if len(output) > MAX_VERSION_OUTPUT_BYTES or len(chunk) > remaining:
                    overflow.set()
        except (OSError, ValueError) as exc:
            read_errors.append(exc)
            read_failed.set()

    reader = threading.Thread(target=read_output, daemon=True)
    reader.start()
    try:
        try:
            return_code = process.wait(timeout=VERSION_TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired:
            raise BrowserVersionIdentityError(
                "browser version command timed out"
            ) from None
        reader.join(KILL_GRACE_SECONDS)
        if reader.is_alive() or read_failed.is_set():
            failure = BrowserVersionIdentityError(
                "browser version output could not be read"
            )
            if read_errors:
                raise failure from read_errors[0]
            raise failure
        if overflow.is_set():
            raise BrowserVersionIdentityError(
                "browser version output exceeds its limit"
            )
        if return_code != 0:
            raise BrowserVersionIdentityError("browser version command failed")
        return bytes(output)
    finally:
        primary_error = sys.exc_info()[1]
        cleanup_errors: list[BaseException] = []
        try:
            _cleanup_version_process(process)
        except Exception as exc:
            cleanup_errors.append(exc)
        try:
            if not process.stdout.closed:
                process.stdout.close()
            reader.join(KILL_GRACE_SECONDS)
            if reader.is_alive():
                raise BrowserVersionIdentityError(
                    "browser version output reader could not be stopped"
                )
        except Exception as exc:
            cleanup_errors.append(exc)
        if primary_error is not None:
            for read_error in read_errors:
                primary_error.add_note(
                    f"Browser version output reader also failed: {read_error}"
                )
            for cleanup_error in cleanup_errors:
                primary_error.add_note(
                    "Browser version cleanup also failed: "
                    f"{cleanup_error}"
                )
        elif cleanup_errors:
            _raise_version_cleanup_error(cleanup_errors)


def _raise_version_cleanup_error(errors: list[BaseException]) -> None:
    primary = errors[0]
    for secondary in errors[1:]:
        primary.add_note(
            f"Additional browser version cleanup failure: {secondary}"
        )
    if isinstance(primary, BrowserVersionIdentityError):
        raise primary
    raise BrowserVersionIdentityError(
        "browser version process cleanup failed"
    ) from primary


def _cleanup_version_process(process) -> None:
    """Bound cleanup to the process on Windows or its owned POSIX group."""

    if os.name == "nt":
        if process.poll() is None:
            process.kill()
            try:
                process.wait(timeout=KILL_GRACE_SECONDS)
            except subprocess.TimeoutExpired as exc:
                raise BrowserVersionIdentityError(
                    "browser version process could not be stopped"
                ) from exc
        return
    process_group = process.pid
    try:
        os.killpg(process_group, _POSIX_TERMINATE_SIGNAL)
    except ProcessLookupError:
        return
    try:
        process.wait(timeout=KILL_GRACE_SECONDS)
    except subprocess.TimeoutExpired:
        pass
    try:
        os.killpg(process_group, _POSIX_KILL_SIGNAL)
    except ProcessLookupError:
        pass
    try:
        process.wait(timeout=KILL_GRACE_SECONDS)
    except subprocess.TimeoutExpired as exc:
        raise BrowserVersionIdentityError(
            "browser version process group could not be stopped"
        ) from exc


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
