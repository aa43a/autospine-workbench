"""Copy-isolated pure result for P10.7a v2-source compilation."""

from __future__ import annotations

from dataclasses import dataclass, field
import json

from .spine42_contract_v3_v2 import MOTION_SOURCE_FIELDS
from .spine42_v3_bundle_contract_v2 import Spine42V3BundleContractV2


@dataclass(frozen=True, slots=True)
class VerifiedSpine42V3CompilationV2:
    project_id: str
    clip_id: str
    adapter_profile_sha256: str
    source_contract_sha256: str
    motion_instance_v3_source_sha256: str
    p3_rig_sha256: str
    p3_bundle_sha256: str
    motion_instance_v3_sha256: str
    motion_instance_v3_bundle_sha256: str
    admission_sha256: str
    source_set_sha256: str
    source_document_sha256: str
    dynamic_seam_probe_sha256: str
    dynamic_seam_bundle_sha256: str
    motion_instance_v2_sha256: str
    reviewed_motion_bundle_sha256: str
    motion_instance_v3_profile_sha256: str
    motion_domain_sha256: str
    rotation_timeline_sha256: str
    base_channels_sha256: str
    rig_ir_sha256: str
    target_profile_sha256: str
    motion_instance_v3_run_sha256: str
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
    def from_contract(cls, contract):
        if type(contract) is not Spine42V3BundleContractV2:
            raise TypeError("A P10.7a v2 bundle contract is required")
        names = tuple(cls.__dataclass_fields__)[:-2]
        return cls(
            *(getattr(contract, name) for name in names),
            tuple(contract.document_bytes.items()),
            tuple(sorted(contract.source_image_sha256s.items())),
        )

    @property
    def document_bytes(self):
        return dict(self._document_items)

    @property
    def inventory(self):
        return tuple(name for name, _data in self._document_items)

    @property
    def source_image_sha256s(self):
        return dict(self._source_images)

    @property
    def skeleton_json(self):
        return json.loads(self.document_bytes["skeleton.json"])

    @property
    def atlas_bytes(self):
        return self.document_bytes["skeleton.atlas"]

    @property
    def png_bytes(self):
        return self.document_bytes["skeleton.png"]

    @property
    def run_manifest(self):
        return json.loads(self.document_bytes["run-manifest.json"])

    @property
    def export_report(self):
        return json.loads(self.document_bytes["export-report.json"])

    @property
    def p3_source(self):
        return {"rig_sha256": self.p3_rig_sha256,
                "bundle_sha256": self.p3_bundle_sha256}

    @property
    def motion_instance_v3_source(self):
        values = (
            self.motion_instance_v3_sha256,
            self.motion_instance_v3_bundle_sha256,
            self.admission_sha256, self.source_set_sha256,
            self.source_document_sha256, self.dynamic_seam_probe_sha256,
            self.dynamic_seam_bundle_sha256,
            self.motion_instance_v2_sha256,
            self.reviewed_motion_bundle_sha256,
            self.motion_instance_v3_profile_sha256,
            self.motion_domain_sha256, self.rotation_timeline_sha256,
            self.base_channels_sha256, self.rig_ir_sha256,
            self.target_profile_sha256, self.motion_instance_v3_run_sha256,
        )
        return dict(zip(MOTION_SOURCE_FIELDS, values, strict=True))

    @property
    def contract_identities(self):
        names = tuple(self.__dataclass_fields__)[:-2]
        return {name: getattr(self, name) for name in names
                if name not in {"project_id", "clip_id"}}


__all__ = ["VerifiedSpine42V3CompilationV2"]
