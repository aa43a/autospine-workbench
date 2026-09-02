"""Shared reader-issued P10.7a v2 pure-core fixture."""

from __future__ import annotations

from contextlib import ExitStack, contextmanager
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from autospine_workbench.mesh_source_images import (
    VerifiedAttachmentImage, VerifiedMeshSource,
)
from autospine_workbench.motion_instance_v3_bundle_reader_v2 import (
    MotionInstanceV3BundleReaderV2,
)
from autospine_workbench.png_rgba import RgbaImage, encode_rgba_png
from autospine_workbench.reviewed_motion_bundle_upstream import (
    require_reviewed_motion_upstreams,
)
from autospine_workbench.spine42_atlas import build_spine42_atlas
from autospine_workbench.spine42_contract_v3_v2 import (
    spine42_motion_source_v3_v2,
)
from autospine_workbench.spine42_json_adapter_v3_v2 import (
    build_spine42_json_v3_v2,
)
from autospine_workbench.spine42_v3_bundle_contract_v2 import (
    build_spine42_v3_bundle_contract_v2,
)
from tests.motion_instance_v3_bundle_v2_helpers import (
    MotionInstanceV3BundleV2Fixture,
)


PIPELINE = "autospine_workbench.spine42_v3_pipeline_v2."
V3_READER = "autospine_workbench.motion_instance_v3_bundle_reader_v2."


class Spine42V3V2Fixture:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.motion_fixture = MotionInstanceV3BundleV2Fixture(self.root)
        self.state_root = self.motion_fixture.state_root
        self.published = self.motion_fixture.publish()
        with self.motion_fixture.historical_replay(), patch(
            V3_READER + "VerifiedReviewedMotionBundleReader.load",
            return_value=self.motion_fixture.reviewed,
        ):
            self.motion_bundle = MotionInstanceV3BundleReaderV2(
                self.state_root
            ).load(
                self.motion_fixture.contract.project_id,
                self.published.motion_instance_v3_sha256,
                self.published.bundle_sha256,
            )
        self.reviewed = self.motion_fixture.reviewed
        self.mesh_bundle = self.motion_fixture.p9_fixture.mesh
        self.mesh = _mesh_source(self.mesh_bundle)
        self.retarget = self.motion_fixture.p9_fixture.retarget
        _base, self.target = require_reviewed_motion_upstreams(
            self.mesh_bundle, self.retarget,
        )

    def contract(self):
        skeleton = build_spine42_json_v3_v2(
            self.mesh.rig, motion_bundle=self.motion_bundle,
            reviewed_bundle=self.reviewed, target_profile=self.target,
        )
        images = {item.attachment_id: item.png_bytes
                  for item in self.mesh.images}
        source = {item.attachment_id: item.image_sha256
                  for item in self.mesh.images}
        atlas = build_spine42_atlas(images, page_name="skeleton.png")
        return build_spine42_v3_bundle_contract_v2(
            self.motion_bundle.project_id, self.motion_bundle.clip_id,
            {"rig_sha256": self.mesh.p3_rig_sha256,
             "bundle_sha256": self.mesh.p3_bundle_sha256},
            spine42_motion_source_v3_v2(self.motion_bundle), skeleton,
            atlas.atlas_bytes, atlas.png_bytes, source,
        )

    @contextmanager
    def pipeline_sources(self):
        readers = {
            "MotionInstanceV3BundleReaderV2": self.motion_bundle,
            "VerifiedReviewedMotionBundleReader": self.reviewed,
            "VerifiedMotionRetargetBundleReader": self.retarget,
            "VerifiedMeshSourceReader": self.mesh,
        }
        mocks = {}
        with ExitStack() as stack:
            for name, value in readers.items():
                load = Mock(return_value=value)
                reader = SimpleNamespace(load=load)
                mocks[name] = stack.enter_context(patch(
                    PIPELINE + name, return_value=reader,
                ))
                mocks[name + ".load"] = load
            mocks["_source_images"] = stack.enter_context(patch(
                PIPELINE + "_source_images",
                return_value=(
                    self.mesh.png_by_attachment,
                    {item["id"]: item["image_sha256"]
                     for item in self.mesh.rig["attachments"]},
                ),
            ))
            yield mocks


def _mesh_source(bundle):
    """Give the legacy synthetic P3 fixture deterministic raster payloads."""

    rig, images = bundle.rig, []
    for index, attachment in enumerate(rig["attachments"]):
        if attachment["type"] == "region":
            width, height = attachment["size"]
        else:
            width = max(point[0] for point in attachment["vertices"])
            height = max(point[1] for point in attachment["vertices"])
        pixel = bytes((40 + index, 80 + index, 120 + index, 255))
        raw = encode_rgba_png(RgbaImage(
            width, height, pixel * (width * height),
        ))
        images.append(VerifiedAttachmentImage(
            attachment["id"], attachment["image_path"],
            attachment["image_sha256"], width, height, raw,
        ))
    return VerifiedMeshSource(
        bundle.path, bundle.project_id, bundle.rig_sha256,
        bundle.bundle_sha256, bundle.base_rig_sha256,
        bundle.base_bundle_sha256,
        json.dumps(rig, allow_nan=False, sort_keys=True, separators=(",", ":")),
        tuple(images),
    )


__all__ = ["Spine42V3V2Fixture"]
