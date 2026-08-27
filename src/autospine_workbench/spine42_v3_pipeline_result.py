"""Frozen copy-isolated value object for verified Spine 4.2 v3 builds."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from typing import Any


@dataclass(frozen=True, slots=True)
class VerifiedSpine42V3Compilation:
    """Expose immutable bytes and fresh mappings for one pure v3 export."""

    project_id: str
    clip_id: str
    p3_rig_sha256: str
    p3_bundle_sha256: str
    motion_instance_v3_sha256: str
    motion_instance_v3_bundle_sha256: str
    admission_sha256: str
    motion_instance_v3_profile_sha256: str
    target_profile_sha256: str
    adapter_profile_sha256: str
    skeleton_json_sha256: str
    atlas_sha256: str
    png_sha256: str
    run_identity_sha256: str
    run_document_sha256: str
    report_sha256: str
    bundle_sha256: str
    _document_items: tuple[tuple[str, bytes], ...] = field(repr=False)
    _source_images: tuple[tuple[str, str], ...] = field(repr=False)

    @classmethod
    def from_contract(cls, contract: Any) -> VerifiedSpine42V3Compilation:
        """Freeze a detached pipeline result from a verified pure contract."""

        return cls(
            project_id=contract.project_id,
            clip_id=contract.clip_id,
            p3_rig_sha256=contract.p3_rig_sha256,
            p3_bundle_sha256=contract.p3_bundle_sha256,
            motion_instance_v3_sha256=contract.motion_instance_v3_sha256,
            motion_instance_v3_bundle_sha256=
                contract.motion_instance_v3_bundle_sha256,
            admission_sha256=contract.admission_sha256,
            motion_instance_v3_profile_sha256=
                contract.motion_instance_v3_profile_sha256,
            target_profile_sha256=contract.target_profile_sha256,
            adapter_profile_sha256=contract.adapter_profile_sha256,
            skeleton_json_sha256=contract.skeleton_json_sha256,
            atlas_sha256=contract.atlas_sha256,
            png_sha256=contract.png_sha256,
            run_identity_sha256=contract.run_identity_sha256,
            run_document_sha256=contract.run_document_sha256,
            report_sha256=contract.report_sha256,
            bundle_sha256=contract.bundle_sha256,
            _document_items=tuple(contract.document_bytes.items()),
            _source_images=tuple(sorted(
                contract.source_image_sha256s.items()
            )),
        )

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
    def inventory(self) -> tuple[str, ...]:
        return tuple(name for name, _data in self._document_items)

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
    def motion_instance_v3_source(self) -> dict[str, str]:
        return {
            "motion_instance_v3_sha256": self.motion_instance_v3_sha256,
            "bundle_sha256": self.motion_instance_v3_bundle_sha256,
            "admission_sha256": self.admission_sha256,
            "profile_sha256": self.motion_instance_v3_profile_sha256,
            "target_profile_sha256": self.target_profile_sha256,
        }

    @property
    def contract_identities(self) -> dict[str, str]:
        return {
            name: getattr(self, name) for name in (
                "adapter_profile_sha256", "p3_rig_sha256",
                "p3_bundle_sha256", "motion_instance_v3_sha256",
                "motion_instance_v3_bundle_sha256", "admission_sha256",
                "motion_instance_v3_profile_sha256",
                "target_profile_sha256", "skeleton_json_sha256",
                "atlas_sha256", "png_sha256", "run_identity_sha256",
                "run_document_sha256", "report_sha256", "bundle_sha256",
            )
        }


__all__ = ["VerifiedSpine42V3Compilation"]
