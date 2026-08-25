"""P6 command services publish and rebuild exact Spine 4.2 bundles."""

from __future__ import annotations

from contextlib import ExitStack
from dataclasses import replace
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from autospine_workbench.spine42_commands import (  # noqa: E402
    Spine42CommandError,
    compile_spine42_bundle,
    verify_spine42_bundle,
)
from autospine_workbench.spine42_pipeline import (  # noqa: E402
    VerifiedSpine42Pipeline,
)
from tests.test_spine42_pipeline import (  # noqa: E402
    PROJECT,
    mesh_source,
    motion_bundle,
)


def state_tree(root: Path) -> tuple[tuple[str, bytes], ...]:
    return tuple(sorted(
        (path.relative_to(root).as_posix(), path.read_bytes())
        for path in root.rglob("*") if path.is_file()
    ))


class Spine42CommandTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.state = Path(self.temporary.name) / "state"
        self.state.mkdir()
        self.mesh = mesh_source()
        self.motion = motion_bundle(self.mesh)

    def upstream(self, *, motion: bool = False) -> ExitStack:
        stack = ExitStack()
        stack.enter_context(patch(
            "autospine_workbench.spine42_pipeline."
            "VerifiedMeshSourceReader.load",
            return_value=self.mesh,
        ))
        if motion:
            stack.enter_context(patch(
                "autospine_workbench.spine42_pipeline."
                "VerifiedMotionRetargetBundleReader.load",
                return_value=self.motion,
            ))
        return stack

    def compile(self, *, motion: bool = False):
        keywords = {}
        if motion:
            keywords = {
                "motion_instance_sha256": self.motion.instance_sha256,
                "motion_bundle_sha256": self.motion.bundle_sha256,
            }
        with self.upstream(motion=motion):
            return compile_spine42_bundle(
                self.state,
                PROJECT,
                p3_rig_sha256=self.mesh.p3_rig_sha256,
                p3_bundle_sha256=self.mesh.p3_bundle_sha256,
                **keywords,
            )

    def test_setup_compile_publishes_reads_rebuilds_and_reuses(self):
        first = self.compile()
        second = self.compile()

        self.assertFalse(first.reused)
        self.assertTrue(second.reused)
        self.assertEqual(first.path, second.path)
        self.assertEqual("setup-only", first.mode)
        self.assertIsNone(first.clip_id)
        self.assertEqual({
            "p3": {
                "rig_sha256": self.mesh.p3_rig_sha256,
                "bundle_sha256": self.mesh.p3_bundle_sha256,
            },
            "p5": None,
        }, first.source_addresses)
        self.assertEqual(first.bundle_sha256, first.path.name)
        self.assertEqual(first.skeleton_json_sha256, first.path.parent.name)
        self.assertIn("mode=setup-only;clip=none", first.summary)
        self.assertEqual(7, len(first.output_sha256s))
        changed = first.source_addresses
        changed["p3"]["rig_sha256"] = "f" * 64
        self.assertEqual(
            self.mesh.p3_rig_sha256,
            first.source_addresses["p3"]["rig_sha256"],
        )

    def test_motion_compile_binds_both_addresses_and_clip(self):
        result = self.compile(motion=True)

        self.assertEqual("motion", result.mode)
        self.assertEqual(self.motion.clip_id, result.clip_id)
        self.assertEqual(
            self.motion.instance_sha256,
            result.source_addresses["p5"]["motion_instance_sha256"],
        )
        self.assertEqual(
            self.motion.bundle_sha256,
            result.source_addresses["p5"]["bundle_sha256"],
        )
        self.assertIn(f"clip={self.motion.clip_id}", result.summary)

    def test_verify_is_read_only_and_rebuilds_exact_upstream(self):
        compiled = self.compile(motion=True)
        before = state_tree(self.state)
        with self.upstream(motion=True):
            verified = verify_spine42_bundle(
                self.state,
                PROJECT,
                skeleton_json_sha256=compiled.skeleton_json_sha256,
                bundle_sha256=compiled.bundle_sha256,
            )

        self.assertIsNone(verified.reused)
        self.assertEqual(compiled.output_sha256s, verified.output_sha256s)
        self.assertEqual(compiled.source_addresses, verified.source_addresses)
        self.assertEqual(before, state_tree(self.state))

    def test_incomplete_motion_pair_fails_before_pipeline_or_store(self):
        with patch(
            "autospine_workbench.spine42_commands.VerifiedSpine42Pipeline"
        ) as pipeline, patch(
            "autospine_workbench.spine42_commands.Spine42BundleStore"
        ) as store, self.assertRaisesRegex(Spine42CommandError, "together"):
            compile_spine42_bundle(
                self.state,
                PROJECT,
                p3_rig_sha256=self.mesh.p3_rig_sha256,
                p3_bundle_sha256=self.mesh.p3_bundle_sha256,
                motion_instance_sha256=self.motion.instance_sha256,
            )
        pipeline.assert_not_called()
        store.assert_not_called()
        self.assertEqual((), state_tree(self.state))

    def test_readback_rebuild_drift_is_rejected(self):
        with self.upstream():
            compilation = VerifiedSpine42Pipeline(self.state).build(
                PROJECT,
                self.mesh.p3_rig_sha256,
                self.mesh.p3_bundle_sha256,
            )
        drifted = replace(compilation, bundle_sha256="f" * 64)
        with patch(
            "autospine_workbench.spine42_commands.VerifiedSpine42Pipeline"
        ) as pipeline, self.upstream():
            pipeline.return_value.build.return_value = compilation
            pipeline.return_value.rebuild_and_verify.return_value = drifted
            with self.assertRaisesRegex(
                Spine42CommandError, "readback rebuild differs"
            ):
                compile_spine42_bundle(
                    self.state,
                    PROJECT,
                    p3_rig_sha256=self.mesh.p3_rig_sha256,
                    p3_bundle_sha256=self.mesh.p3_bundle_sha256,
                )

    def test_bad_verify_address_and_pipeline_failure_are_unified(self):
        with self.assertRaisesRegex(
            Spine42CommandError, "bundle verification failed"
        ):
            verify_spine42_bundle(
                self.state,
                PROJECT,
                skeleton_json_sha256="not-a-sha",
                bundle_sha256="also-not-a-sha",
            )
        with patch(
            "autospine_workbench.spine42_commands.VerifiedSpine42Pipeline"
        ) as pipeline, patch(
            "autospine_workbench.spine42_commands."
            "VerifiedSpine42BundleReader"
        ) as reader:
            reader.return_value.load.return_value = object()
            pipeline.return_value.rebuild_and_verify.side_effect = RuntimeError(
                "boom"
            )
            with self.assertRaisesRegex(
                Spine42CommandError, "bundle verification failed"
            ):
                verify_spine42_bundle(
                    self.state,
                    PROJECT,
                    skeleton_json_sha256="a" * 64,
                    bundle_sha256="b" * 64,
                )


if __name__ == "__main__":
    unittest.main()
