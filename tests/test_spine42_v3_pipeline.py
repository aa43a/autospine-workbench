"""Pure verified MIv3-to-Spine 4.2 pipeline tests."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import FrozenInstanceError, replace
import hashlib
import inspect
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from autospine_workbench.body_sway_motion_consumer_admission import (  # noqa: E402
    compile_body_sway_motion_consumer_admission_core,
    seal_body_sway_motion_consumer_admission,
)
from autospine_workbench.mesh_source_images import (  # noqa: E402
    VerifiedMeshSourceReader,
)
from autospine_workbench.motion_instance_v3_bundle_reader import (  # noqa: E402
    VerifiedMotionInstanceV3BundleReader,
)
from autospine_workbench.motion_instance_v3_bundle_store import (  # noqa: E402
    MotionInstanceV3BundleStore,
)
from autospine_workbench.motion_instance_v3_compiler import (  # noqa: E402
    compile_motion_instance_v3,
)
from autospine_workbench.spine42_v3_bundle_integrity import (  # noqa: E402
    Spine42V3BundleSnapshot,
    verify_spine42_v3_bundle_snapshot,
)
from autospine_workbench.spine42_v3_bundle_contract import (  # noqa: E402
    build_spine42_v3_bundle_contract,
)
from autospine_workbench.spine42_v3_pipeline import (  # noqa: E402
    VerifiedSpine42V3Pipeline,
    VerifiedSpine42V3PipelineError,
)
from tests.body_sway_motion_consumer_helpers import (  # noqa: E402
    certified_probe,
    head_identity,
    head_observation,
    patched_probe_replay,
)
from tests.p10_candidate_helpers import P10PersistedFixture  # noqa: E402


class VerifiedSpine42V3PipelineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temporary = TemporaryDirectory()
        cls.fixture = P10PersistedFixture(Path(cls.temporary.name))
        cls.project = cls.fixture.reviewed.project_id
        cls.probe = certified_probe(cls.fixture.reviewed)
        cls.identity = head_identity(cls.project)
        observation = head_observation(cls.identity)
        with patched_probe_replay(cls.probe, cls.identity):
            core = compile_body_sway_motion_consumer_admission_core(
                cls.probe, cls.fixture.reviewed
            )
            admission = seal_body_sway_motion_consumer_admission(
                core, observation, observation
            )
            instance = compile_motion_instance_v3(
                admission.document, cls.fixture.reviewed
            )
            with patch(
                "autospine_workbench.motion_instance_v3_bundle_store."
                "require_current_body_sway_dynamic_seam_heads",
                side_effect=(observation, observation),
            ):
                cls.published = MotionInstanceV3BundleStore(
                    cls.fixture.state
                ).publish(
                    cls.project, admission.document, instance.document,
                    cls.fixture.reviewed,
                )
            cls.v3 = VerifiedMotionInstanceV3BundleReader(
                cls.fixture.state
            ).load(
                cls.project, cls.published.motion_instance_v3_sha256,
                cls.published.bundle_sha256,
                reviewed_bundle=cls.fixture.reviewed,
            )
        motion_v2 = cls.fixture.reviewed.document("motion-instance-v2.json")
        source = motion_v2["source"]
        cls.mesh = VerifiedMeshSourceReader(cls.fixture.state).load(
            cls.project, source["p3_rig_sha256"],
            source["p3_bundle_sha256"],
        )

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temporary.cleanup()

    def _build(self):
        with patched_probe_replay(self.probe, self.identity):
            return VerifiedSpine42V3Pipeline(self.fixture.state).build(
                self.project, self.published.motion_instance_v3_sha256,
                self.published.bundle_sha256,
            )

    def test_public_build_accepts_only_project_and_exact_miv3_address(self):
        parameters = list(inspect.signature(
            VerifiedSpine42V3Pipeline.build
        ).parameters)
        self.assertEqual(parameters, [
            "self", "project_id", "motion_instance_v3_sha256",
            "motion_instance_v3_bundle_sha256",
        ])

    def test_build_is_deterministic_frozen_copy_isolated_and_pure(self):
        before = _state_snapshot(self.fixture.state)
        first = self._build()
        second = self._build()
        self.assertEqual(first, second)
        self.assertEqual(before, _state_snapshot(self.fixture.state))
        self.assertEqual(self.v3.clip_id, first.clip_id)
        self.assertEqual(5, len(first.document_bytes))
        self.assertEqual({self.v3.clip_id}, set(
            first.skeleton_json["animations"]
        ))
        changed = first.skeleton_json
        changed["bones"].clear()
        self.assertGreater(len(first.skeleton_json["bones"]), 0)
        documents = first.document_bytes
        documents.clear()
        self.assertEqual(5, len(first.document_bytes))
        with self.assertRaises(FrozenInstanceError):
            first.clip_id = "changed"  # type: ignore[misc]

    def test_rebuild_accepts_verified_bundle_and_compares_every_byte(self):
        built = self._build()
        bundle = verify_spine42_v3_bundle_snapshot(
            Spine42V3BundleSnapshot(
                Path("unused"), tuple(built.document_bytes.items())
            ),
            expected_project_id=built.project_id,
            expected_skeleton_json_sha256=built.skeleton_json_sha256,
            expected_bundle_sha256=built.bundle_sha256,
            require_address_path=False,
        )
        with patched_probe_replay(self.probe, self.identity):
            rebuilt = VerifiedSpine42V3Pipeline(
                self.fixture.state
            ).rebuild_and_verify(bundle)
        self.assertEqual(built, rebuilt)
        forged = replace(bundle, bundle_sha256="f" * 64)
        with patched_probe_replay(self.probe, self.identity), \
                self.assertRaisesRegex(
                    VerifiedSpine42V3PipelineError,
                    "exact upstream rebuild",
                ):
            VerifiedSpine42V3Pipeline(
                self.fixture.state
            ).rebuild_and_verify(forged)

    def test_structural_reseal_cannot_impersonate_exact_upstream_output(self):
        built = self._build()
        skeleton = built.skeleton_json
        animation = skeleton["animations"][built.clip_id]
        timeline = next(
            values
            for tracks in animation["bones"].values()
            for values in tracks.values()
        )
        field = "value" if "value" in timeline[1] else "x"
        timeline[1][field] += 0.25
        resealed = build_spine42_v3_bundle_contract(
            built.project_id,
            built.clip_id,
            built.p3_source,
            built.motion_instance_v3_source,
            skeleton,
            built.atlas_bytes,
            built.png_bytes,
            built.source_image_sha256s,
        )
        self.assertNotEqual(built.bundle_sha256, resealed.bundle_sha256)
        structurally_verified = verify_spine42_v3_bundle_snapshot(
            Spine42V3BundleSnapshot(
                Path("unused"), tuple(resealed.document_bytes.items())
            ),
            expected_project_id=resealed.project_id,
            expected_skeleton_json_sha256=resealed.skeleton_json_sha256,
            expected_bundle_sha256=resealed.bundle_sha256,
            require_address_path=False,
        )
        with patched_probe_replay(self.probe, self.identity), \
                self.assertRaisesRegex(
                    VerifiedSpine42V3PipelineError,
                    "exact upstream rebuild",
                ):
            VerifiedSpine42V3Pipeline(
                self.fixture.state
            ).rebuild_and_verify(structurally_verified)

    def test_cross_wired_v3_p9_p3_rig_and_target_fail_closed(self):
        cases = (
            (
                "v3/P9 clip",
                "VerifiedMotionInstanceV3BundleReader.load",
                replace(self.v3, clip_id="wrong-clip"),
            ),
            (
                "P3 project/address",
                "VerifiedMeshSourceReader.load",
                replace(self.mesh, project_id="wrong-project"),
            ),
            (
                "target identity",
                "VerifiedMotionRetargetBundleReader.load",
                replace(
                    self.fixture.retarget,
                    target_profile_sha256="f" * 64,
                ),
            ),
        )
        for label, method, value in cases:
            with self.subTest(label=label), patched_probe_replay(
                self.probe, self.identity
            ), patch(
                f"autospine_workbench.spine42_v3_pipeline.{method}",
                return_value=value,
            ), self.assertRaises(VerifiedSpine42V3PipelineError):
                VerifiedSpine42V3Pipeline(self.fixture.state).build(
                    self.project,
                    self.published.motion_instance_v3_sha256,
                    self.published.bundle_sha256,
                )

    def test_mutated_rig_bytes_cannot_reuse_the_exact_p3_address(self):
        rig = deepcopy(self.mesh.rig)
        rig["canvas"]["width"] += 1
        forged = replace(
            self.mesh,
            _rig_json=json.dumps(
                rig, ensure_ascii=False, allow_nan=False,
                sort_keys=True, separators=(",", ":"),
            ),
        )
        with patched_probe_replay(self.probe, self.identity), patch(
            "autospine_workbench.spine42_v3_pipeline."
            "VerifiedMeshSourceReader.load",
            return_value=forged,
        ), self.assertRaisesRegex(
            VerifiedSpine42V3PipelineError, "P9, P5, P3, or rig"
        ):
            VerifiedSpine42V3Pipeline(self.fixture.state).build(
                self.project, self.published.motion_instance_v3_sha256,
                self.published.bundle_sha256,
            )


def _state_snapshot(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(
            path.read_bytes()
        ).hexdigest()
        for path in sorted(root.rglob("*")) if path.is_file()
    }


if __name__ == "__main__":
    unittest.main()
