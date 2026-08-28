"""Shared deterministic inputs for Kimodo pilot intake tests."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from tests.fixtures.kimodo_npz_archive import build_npz, motion_member_bytes
from tests.kimodo_npz_helpers import map_document, source_document


def camera_document() -> dict:
    return {
        "format": "autospine-camera-model",
        "format_version": 1,
        "camera_id": "kimodo-front-v1",
        "projection": "static_orthographic",
        "basis": {"screen_x": "+X", "screen_y": "-Y", "depth": "+Z"},
        "depth_positive": "away_from_camera",
        "origin": "source_root_frame0",
        "normalization": "map_reference_length",
        "reference_length_meters": 1.0,
    }


class KimodoPilotInputs:
    def __init__(self) -> None:
        self.raw = build_npz(motion_member_bytes())
        self.checkpoint = b'{"checkpoint":"fixture-v1"}'
        self.request = b'{"prompt":"walk","seed":42}'
        self.source = source_document(self.raw, recorded=True)
        self.source["producer"]["checkpoint_manifest_sha256"] = \
            hashlib.sha256(self.checkpoint).hexdigest()
        self.source["producer"]["generation_request_sha256"] = \
            hashlib.sha256(self.request).hexdigest()
        self.mapping = map_document()
        self.camera = camera_document()

    def arguments(self) -> tuple:
        return (
            self.raw, self.source, self.mapping, self.camera,
            self.checkpoint, self.request,
        )

    def write(self, root: Path) -> tuple[Path, ...]:
        paths = (
            root / "motion.npz",
            root / "motion.source.json",
            root / "motion.map.json",
            root / "camera.json",
            root / "checkpoint.manifest",
            root / "generation.request",
        )
        paths[0].write_bytes(self.raw)
        for path, value in zip(
            paths[1:4], (self.source, self.mapping, self.camera), strict=True
        ):
            path.write_text(
                json.dumps(value, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        paths[4].write_bytes(self.checkpoint)
        paths[5].write_bytes(self.request)
        return paths
