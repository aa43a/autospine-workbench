"""Frozen copy-isolated value object for verified Spine 4.2 builds."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from typing import Any


@dataclass(frozen=True, slots=True)
class VerifiedSpine42Compilation:
    """Expose immutable bytes and fresh mappings for one pure compilation."""

    project_id: str
    mode: str
    clip_id: str | None
    p3_rig_sha256: str
    p3_bundle_sha256: str
    p5_target_profile_sha256: str | None
    p5_motion_instance_sha256: str | None
    p5_bundle_sha256: str | None
    skeleton_json_sha256: str
    atlas_sha256: str
    png_sha256: str
    run_identity_sha256: str
    run_document_sha256: str
    report_sha256: str
    bundle_sha256: str
    _document_items: tuple[tuple[str, bytes], ...] = field(repr=False)
    _source_images: tuple[tuple[str, str], ...] = field(repr=False)

    def _json(self, name: str) -> dict[str, Any]:
        return json.loads(dict(self._document_items)[name])

    @property
    def skeleton_json(self) -> dict[str, Any]:
        return self._json("skeleton.json")

    @property
    def run_manifest(self) -> dict[str, Any]:
        return self._json("run-manifest.json")

    @property
    def export_report(self) -> dict[str, Any]:
        return self._json("export-report.json")

    @property
    def atlas_bytes(self) -> bytes:
        return dict(self._document_items)["skeleton.atlas"]

    @property
    def png_bytes(self) -> bytes:
        return dict(self._document_items)["skeleton.png"]

    @property
    def document_bytes(self) -> dict[str, bytes]:
        return dict(self._document_items)

    @property
    def source_image_sha256s(self) -> dict[str, str]:
        return dict(self._source_images)

    @property
    def p3_source(self) -> dict[str, str]:
        return {
            "rig_sha256": self.p3_rig_sha256,
            "bundle_sha256": self.p3_bundle_sha256,
        }

    @property
    def p5_source(self) -> dict[str, Any] | None:
        if self.p5_motion_instance_sha256 is None:
            return None
        return {
            "target_profile_sha256": self.p5_target_profile_sha256,
            "motion_instance_sha256": self.p5_motion_instance_sha256,
            "bundle_sha256": self.p5_bundle_sha256,
            "clip_id": self.clip_id,
        }

    @property
    def contract_identities(self) -> dict[str, str]:
        return {
            "skeleton_json_sha256": self.skeleton_json_sha256,
            "atlas_sha256": self.atlas_sha256,
            "png_sha256": self.png_sha256,
            "run_identity_sha256": self.run_identity_sha256,
            "run_document_sha256": self.run_document_sha256,
            "report_sha256": self.report_sha256,
            "bundle_sha256": self.bundle_sha256,
        }
