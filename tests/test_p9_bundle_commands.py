"""Service tests for P9 reviewed-motion publication and exact replay."""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from autospine_workbench.p9_bundle_commands import (  # noqa: E402
    P9BundleCommandError,
    publish_reviewed_motion_bundle_command,
    verify_reviewed_motion_bundle_command,
)
from autospine_workbench.reviewed_motion_bundle_store import (  # noqa: E402
    PublishedReviewedMotionBundle,
)
from tests.p9_v2_helpers import tree  # noqa: E402
from tests.reviewed_motion_bundle_helpers import (  # noqa: E402
    ReviewedMotionStorageFixture,
)


class P9BundleCommandTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.fixture = ReviewedMotionStorageFixture(self.root)
        self.paths = tuple(
            self.write(name, document)
            for name, document in zip(
                ("foot.json", "depth.json", "decision.json", "policy.json"),
                self.fixture.documents[:4],
                strict=True,
            )
        )

    def write(self, name: str, document) -> Path:
        path = self.root / name
        path.write_text(json.dumps(
            document, ensure_ascii=False, allow_nan=False,
            sort_keys=True, separators=(",", ":"),
        ), encoding="utf-8")
        return path

    def publish(self, *, paths=None):
        mesh, p5 = self.fixture.mesh, self.fixture.retarget
        with patch(
            "autospine_workbench.p9_bundle_commands.VerifiedMeshBundleReader"
        ) as mesh_reader, patch(
            "autospine_workbench.p9_bundle_commands."
            "VerifiedMotionRetargetBundleReader"
        ) as p5_reader:
            mesh_reader.return_value.load.return_value = mesh
            p5_reader.return_value.load.return_value = p5
            result = publish_reviewed_motion_bundle_command(
                self.fixture.state_root,
                mesh.project_id,
                *(paths or self.paths),
                p3_rig_sha256=mesh.rig_sha256,
                p3_bundle_sha256=mesh.bundle_sha256,
                motion_instance_sha256=p5.instance_sha256,
                motion_retarget_bundle_sha256=p5.bundle_sha256,
            )
        mesh_reader.return_value.load.assert_called_once_with(
            mesh.project_id, mesh.rig_sha256, mesh.bundle_sha256
        )
        p5_reader.return_value.load.assert_called_once_with(
            mesh.project_id, p5.instance_sha256, p5.bundle_sha256
        )
        return result

    def test_integrated_publish_then_exact_verify_is_zero_write(self):
        published = self.publish()
        address = published.report["address"]
        self.assertTrue(published.output_path.is_dir())
        self.assertEqual(
            "autospine-reviewed-motion-bundle-publication",
            published.report["format"],
        )
        before = tree(self.fixture.state_root)
        with patch(
            "autospine_workbench.reviewed_motion_bundle_reader."
            "VerifiedMeshBundleReader"
        ) as mesh_reader, patch(
            "autospine_workbench.reviewed_motion_bundle_reader."
            "VerifiedMotionRetargetBundleReader"
        ) as p5_reader:
            mesh_reader.return_value.load.return_value = self.fixture.mesh
            p5_reader.return_value.load.return_value = self.fixture.retarget
            verified = verify_reviewed_motion_bundle_command(
                self.fixture.state_root,
                self.fixture.mesh.project_id,
                motion_instance_v2_sha256=address[
                    "motion_instance_v2_sha256"
                ],
                reviewed_motion_bundle_sha256=address["bundle_sha256"],
            )
        self.assertEqual(before, tree(self.fixture.state_root))
        self.assertIsNone(verified.output_path)
        self.assertEqual("passed", verified.report["verification"]["status"])
        self.assertEqual(address, verified.report["address"])

    def test_repeated_publish_keeps_canonical_report_stable(self):
        first = self.publish()
        second = self.publish()
        self.assertFalse(first.reused)
        self.assertTrue(second.reused)
        self.assertEqual(first.report, second.report)
        self.assertEqual(first.report_sha256, second.report_sha256)
        self.assertNotIn("reused", json.dumps(first.report))

    def test_stale_policy_cross_chain_fails_without_publication(self):
        policy = deepcopy(self.fixture.documents[3])
        policy["source"]["p5"]["instance_sha256"] = "f" * 64
        stale = (*self.paths[:3], self.write("stale-policy.json", policy))
        with self.assertRaises(P9BundleCommandError):
            self.publish(paths=stale)
        self.assertFalse(self.fixture.state_root.exists())

    def test_mismatched_store_result_fails_service_postcondition(self):
        mesh, p5 = self.fixture.mesh, self.fixture.retarget
        contract = self.fixture.contract
        fake_path = (
            self.root / "mock-store" / "builds" / contract.project_id
            / "reviewed-motion-instances"
            / contract.motion_instance_v2_sha256 / contract.bundle_sha256
        )
        fake_path.mkdir(parents=True)
        mismatch = PublishedReviewedMotionBundle(
            path=fake_path,
            project_id=contract.project_id,
            clip_id=contract.clip_id,
            motion_instance_v2_sha256=contract.motion_instance_v2_sha256,
            bundle_sha256=contract.bundle_sha256,
            run_sha256="c" * 64,
            reused=False,
        )
        with patch(
            "autospine_workbench.p9_bundle_commands.VerifiedMeshBundleReader"
        ) as mesh_reader, patch(
            "autospine_workbench.p9_bundle_commands."
            "VerifiedMotionRetargetBundleReader"
        ) as p5_reader, patch(
            "autospine_workbench.p9_bundle_commands.ReviewedMotionBundleStore"
        ) as store, self.assertRaisesRegex(
            P9BundleCommandError, "postcondition"
        ):
            mesh_reader.return_value.load.return_value = mesh
            p5_reader.return_value.load.return_value = p5
            store.return_value.publish.return_value = mismatch
            publish_reviewed_motion_bundle_command(
                self.fixture.state_root,
                mesh.project_id,
                *self.paths,
                p3_rig_sha256=mesh.rig_sha256,
                p3_bundle_sha256=mesh.bundle_sha256,
                motion_instance_sha256=p5.instance_sha256,
                motion_retarget_bundle_sha256=p5.bundle_sha256,
            )
        store.return_value.publish.assert_called_once()

    def test_duplicate_and_nan_json_fail_before_exact_readers_or_writes(self):
        bad = self.root / "duplicate.json"
        bad.write_text('{"format":"a","format":"b"}', encoding="utf-8")
        nan = self.root / "nan.json"
        nan.write_text('{"value":NaN}', encoding="utf-8")
        for path in (bad, nan):
            with self.subTest(path=path.name), patch(
                "autospine_workbench.p9_bundle_commands."
                "VerifiedMeshBundleReader"
            ) as mesh_reader, patch(
                "autospine_workbench.p9_bundle_commands."
                "VerifiedMotionRetargetBundleReader"
            ) as p5_reader, self.assertRaises(P9BundleCommandError):
                publish_reviewed_motion_bundle_command(
                    self.fixture.state_root,
                    self.fixture.mesh.project_id,
                    path, *self.paths[1:],
                    p3_rig_sha256=self.fixture.mesh.rig_sha256,
                    p3_bundle_sha256=self.fixture.mesh.bundle_sha256,
                    motion_instance_sha256=self.fixture.retarget.instance_sha256,
                    motion_retarget_bundle_sha256=(
                        self.fixture.retarget.bundle_sha256
                    ),
                )
            mesh_reader.assert_not_called()
            p5_reader.assert_not_called()
            self.assertFalse(self.fixture.state_root.exists())


if __name__ == "__main__":
    unittest.main()
