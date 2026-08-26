"""Exact P10 preview plus fake pinned runtime helpers for capture tests."""

from __future__ import annotations

import hashlib
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

from autospine_workbench.body_sway_runtime_capture_session import (
    build_body_sway_runtime_capture_sessions,
)
from autospine_workbench.png_rgba import RgbaImage, encode_rgba_png
from autospine_workbench.spine42_runtime_inputs import Spine42RuntimePackage
from autospine_workbench.temporary_body_sway_preview import (
    compile_temporary_body_sway_preview,
)
from tests.body_sway_preview_helpers import BodySwayPreviewFixture


RUNTIME_JS = b"fake-official-runtime-js"
RUNTIME_CSS = b"fake-official-runtime-css"
RUNTIME_JS_SHA = hashlib.sha256(RUNTIME_JS).hexdigest()
RUNTIME_CSS_SHA = hashlib.sha256(RUNTIME_CSS).hexdigest()


def fake_runtime(root: Path) -> Spine42RuntimePackage:
    return Spine42RuntimePackage(
        root=root,
        javascript=root / "spine-player.min.js",
        stylesheet=root / "spine-player.min.css",
        license_file=root / "LICENSE",
        javascript_bytes=RUNTIME_JS,
        stylesheet_bytes=RUNTIME_CSS,
        javascript_sha256=RUNTIME_JS_SHA,
        stylesheet_sha256=RUNTIME_CSS_SHA,
    )


def capture_png(
    width=640, height=640, *, pixel: tuple[int, int, int, int] = (20, 40, 60, 255),
) -> bytes:
    pixels = bytes(pixel) * (width * height)
    return encode_rgba_png(RgbaImage(width, height, pixels))


@contextmanager
def fake_runtime_profile():
    """Pin the deterministic tiny runtime fixture at trusted-load boundaries."""

    with patch(
        "autospine_workbench.body_sway_runtime_capture_session."
        "SPINE_PLAYER_JAVASCRIPT_SHA256",
        RUNTIME_JS_SHA,
    ), patch(
        "autospine_workbench.body_sway_runtime_capture_session."
        "SPINE_PLAYER_STYLESHEET_SHA256",
        RUNTIME_CSS_SHA,
    ), patch(
        "autospine_workbench.body_sway_runtime_capture_session_validation."
        "SPINE_PLAYER_JAVASCRIPT_SHA256",
        RUNTIME_JS_SHA,
    ), patch(
        "autospine_workbench.body_sway_runtime_capture_session_validation."
        "SPINE_PLAYER_STYLESHEET_SHA256",
        RUNTIME_CSS_SHA,
    ):
        yield


class RuntimeCaptureFixture:
    def __init__(self, root: Path) -> None:
        self.preview_fixture = BodySwayPreviewFixture(root)
        self.preview = compile_temporary_body_sway_preview(
            self.preview_fixture.preview_inputs,
            self.preview_fixture.chain.mesh_bundle,
        )
        self.runtime = fake_runtime(root / "runtime")
        with fake_runtime_profile():
            self.sessions = build_body_sway_runtime_capture_sessions(
                self.preview, self.runtime
            )
