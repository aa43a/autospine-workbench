"""P10.6b application ordering, wrapper, drift, and verify tests."""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for item in (ROOT, SRC):
    if str(item) not in sys.path:
        sys.path.insert(0, str(item))

import autospine_workbench.p10_motion_instance_v3_commands as module  # noqa: E402
import autospine_workbench.motion_instance_v3_bundle_store as store_module  # noqa: E402
from autospine_workbench.p10_motion_instance_v3_commands import (  # noqa: E402
    P10MotionInstanceV3CommandError,
    compile_body_sway_motion_instance_v3_command,
    verify_body_sway_motion_instance_v3_command,
)
from autospine_workbench.seam_anchor_review_json import (  # noqa: E402
    canonical_json_bytes,
)
from tests.body_sway_motion_consumer_helpers import (  # noqa: E402
    head_observation,
    patched_probe_replay,
)
from tests.motion_instance_v3_bundle_helpers import (  # noqa: E402
    MotionInstanceV3StorageFixture,
)
from tests.p9_v2_helpers import tree  # noqa: E402


class P10MotionInstanceV3CommandTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.fixture = MotionInstanceV3StorageFixture(Path(temporary.name))
        self.wrapper_path = self._write_wrapper(self._wrapper())

    def _wrapper(self):
        admission = self.fixture.admission.document
        heads = admission["head_observations"]
        return {
            "ok": True,
            "status": "compiled",
            "project_id": admission["project_id"],
            "clip_id": admission["clip_id"],
            "dynamic_seam_probe_sha256": admission["source"][
                "dynamic_seam_probe_sha256"
            ],
            "reviewed_motion_address": {
                "motion_instance_v2_sha256": (
                    self.fixture.reviewed_bundle.motion_instance_v2_sha256
                ),
                "reviewed_motion_bundle_sha256": (
                    self.fixture.reviewed_bundle.bundle_sha256
                ),
            },
            "body_sway_motion_consumer_admission_sha256":
                self.fixture.admission.sha256,
            "admission": admission,
            "head_observation": {
                "method": "outer-before-after-consumer-core-compilation",
                "scope": "compile_time",
                "before": heads["before"]["observation"],
                "after": heads["after"]["observation"],
                "checks": {
                    "before_after_identity": "exact_match",
                    "before_after_documents":
                        "canonical_bytes_exact_match",
                },
                "permanent_authority_claimed": False,
            },
        }

    def _write_wrapper(self, value, *, suffix=b"\n"):
        path = self.fixture.root / "inputs" / "p10.6a-wrapper.json"
        path.parent.mkdir(exist_ok=True)
        path.write_bytes(canonical_json_bytes(value) + suffix)
        return path

    def compile(
        self, *, heads=None, admission_sha256=None,
        p9_readback_error=None,
    ):
        observation = head_observation(self.fixture.identity)
        values = heads or (observation, observation)
        with patched_probe_replay(
            self.fixture.probe, self.fixture.identity
        ), patch.object(
            module, "require_current_body_sway_dynamic_seam_heads",
            side_effect=values,
        ), patch.object(
            store_module, "require_current_body_sway_dynamic_seam_heads",
            side_effect=(observation, observation),
        ), patch.object(
            module, "VerifiedReviewedMotionBundleReader"
        ) as reader, patch(
            "autospine_workbench.motion_instance_v3_bundle_reader."
            "VerifiedReviewedMotionBundleReader"
        ) as disk_reader:
            reader.return_value.load.return_value = self.fixture.reviewed_bundle
            if p9_readback_error is None:
                disk_reader.return_value.load.return_value = (
                    self.fixture.reviewed_bundle
                )
            else:
                disk_reader.return_value.load.side_effect = p9_readback_error
            self.last_p9_reader = reader
            self.last_disk_p9_reader = disk_reader
            return compile_body_sway_motion_instance_v3_command(
                self.fixture.state_root,
                self.fixture.reviewed_bundle.project_id,
                self.wrapper_path,
                admission_sha256=(
                    admission_sha256 or self.fixture.admission.sha256
                ),
            )

    def test_compile_order_publishes_only_after_equal_head_snapshots(self):
        events = []
        observation = head_observation(self.fixture.identity)
        heads = iter((observation, observation))
        real_compile = module.compile_motion_instance_v3
        real_build = module.build_motion_instance_v3_bundle_contract
        real_publish = module.MotionInstanceV3BundleStore.publish
        real_readback = module.VerifiedMotionInstanceV3BundleReader.load

        def current(*_args):
            events.append("head")
            return next(heads)

        def store_current(*_args):
            events.append("store_head")
            return observation

        def load_p9(*_args):
            events.append("p9")
            return self.fixture.reviewed_bundle

        def compile_step(*args):
            events.append("compile")
            return real_compile(*args)

        def build_step(*args):
            events.append("construct")
            return real_build(*args)

        def publish_step(store, *args):
            events.append("publish")
            return real_publish(store, *args)

        def readback_step(reader, *args, **kwargs):
            events.append(
                "readback_auto_p9"
                if "reviewed_bundle" not in kwargs
                else "readback_cached_p9"
            )
            return real_readback(reader, *args, **kwargs)

        def load_readback_p9(*_args):
            events.append("readback_p9")
            return self.fixture.reviewed_bundle

        with patched_probe_replay(
            self.fixture.probe, self.fixture.identity
        ), patch.object(
            module, "VerifiedReviewedMotionBundleReader"
        ) as p9_reader, patch.object(
            p9_reader.return_value, "load", side_effect=load_p9,
        ), patch.object(
            module, "require_current_body_sway_dynamic_seam_heads",
            side_effect=current,
        ), patch.object(
            store_module, "require_current_body_sway_dynamic_seam_heads",
            side_effect=store_current,
        ), patch.object(
            module, "compile_motion_instance_v3", side_effect=compile_step,
        ), patch.object(
            module, "build_motion_instance_v3_bundle_contract",
            side_effect=build_step,
        ), patch.object(
            module.MotionInstanceV3BundleStore, "publish", autospec=True,
            side_effect=publish_step,
        ), patch.object(
            module.VerifiedMotionInstanceV3BundleReader, "load",
            autospec=True, side_effect=readback_step,
        ), patch(
            "autospine_workbench.motion_instance_v3_bundle_reader."
            "VerifiedReviewedMotionBundleReader.load",
            side_effect=load_readback_p9,
        ):
            result = compile_body_sway_motion_instance_v3_command(
                self.fixture.state_root,
                self.fixture.reviewed_bundle.project_id,
                self.wrapper_path,
                admission_sha256=self.fixture.admission.sha256,
            )
        self.assertEqual(
            [
                "p9", "head", "compile", "construct", "head", "publish",
                "store_head", "store_head", "readback_auto_p9",
                "readback_p9",
            ],
            events,
        )
        document = result.document
        self.assertEqual("compiled", result.mode)
        self.assertEqual("prepublication_compile", document[
            "head_check"
        ]["scope"])
        self.assertFalse(document["head_check"][
            "permanent_authority_claimed"
        ])
        self.assertTrue(document["head_check"]["current_heads_observed"])
        self.assertEqual(self.fixture.admission.sha256, document["source"][
            "admission_sha256"
        ])
        self.assertNotIn(str(self.fixture.root), json.dumps(document))
        detached = result.document
        detached["verification"]["status"] = "forged"
        self.assertEqual("passed", result.document["verification"]["status"])

    def test_head_identity_or_bytes_drift_causes_zero_publication_writes(self):
        attacks = (
            (
                SimpleNamespace(identity="before", canonical_bytes=b"same"),
                SimpleNamespace(identity="after", canonical_bytes=b"same"),
            ),
            (
                SimpleNamespace(identity="same", canonical_bytes=b"before"),
                SimpleNamespace(identity="same", canonical_bytes=b"after"),
            ),
        )
        for index, heads in enumerate(attacks):
            before = tree(self.fixture.state_root)
            with self.subTest(index=index), patch.object(
                module.MotionInstanceV3BundleStore, "publish"
            ) as publish, self.assertRaisesRegex(
                P10MotionInstanceV3CommandError,
                "MotionInstance v3 compilation failed",
            ):
                self.compile(heads=heads)
            publish.assert_not_called()
            self.assertEqual(before, tree(self.fixture.state_root))

    def test_wrapper_is_strict_successful_canonical_cli_output(self):
        attacks = []
        for field, value in (
            ("ok", False),
            ("status", "error"),
            ("project_id", "other-project"),
        ):
            changed = deepcopy(self._wrapper())
            changed[field] = value
            attacks.append((changed, b"\n"))
        unknown = deepcopy(self._wrapper())
        unknown["latest"] = True
        attacks.append((unknown, b"\n"))
        head = deepcopy(self._wrapper())
        head["head_observation"]["permanent_authority_claimed"] = True
        attacks.append((head, b"\n"))
        p9 = deepcopy(self._wrapper())
        p9["reviewed_motion_address"][
            "reviewed_motion_bundle_sha256"
        ] = "0" * 64
        attacks.append((p9, b"\n"))
        probe = deepcopy(self._wrapper())
        probe["dynamic_seam_probe_sha256"] = "0" * 64
        attacks.append((probe, b"\n"))
        observation = deepcopy(self._wrapper())
        observation["head_observation"]["before"] = {"forged": True}
        attacks.append((observation, b"\n"))
        attacks.append((self._wrapper(), b" \n"))
        for index, (value, suffix) in enumerate(attacks):
            self._write_wrapper(value, suffix=suffix)
            with self.subTest(index=index), self.assertRaises(
                P10MotionInstanceV3CommandError
            ):
                self.compile()
            self.last_p9_reader.assert_not_called()
        self._write_wrapper(self._wrapper())
        with self.assertRaises(P10MotionInstanceV3CommandError):
            self.compile(admission_sha256="0" * 64)

    def test_compile_rejects_a_failed_exact_address_readback(self):
        with patch.object(
            module.VerifiedMotionInstanceV3BundleReader,
            "load",
            return_value=SimpleNamespace(),
        ) as readback, self.assertRaisesRegex(
            P10MotionInstanceV3CommandError,
            "MotionInstance v3 compilation failed",
        ):
            self.compile()
        readback.assert_called_once()

    def test_compile_readback_reloads_the_exact_p9_disk_closure(self):
        with self.assertRaisesRegex(
            P10MotionInstanceV3CommandError,
            "MotionInstance v3 compilation failed",
        ):
            self.compile(
                p9_readback_error=OSError("simulated unavailable P9 bundle")
            )
        self.last_disk_p9_reader.return_value.load.assert_called_once_with(
            self.fixture.reviewed_bundle.project_id,
            self.fixture.reviewed_bundle.motion_instance_v2_sha256,
            self.fixture.reviewed_bundle.bundle_sha256,
        )

    def test_verify_is_exact_historical_path_free_and_never_checks_heads(self):
        compiled = self.compile()
        with patched_probe_replay(
            self.fixture.probe, self.fixture.identity
        ), patch(
            "autospine_workbench.motion_instance_v3_bundle_reader."
            "VerifiedReviewedMotionBundleReader"
        ) as p9_reader, patch.object(
            p9_reader.return_value, "load",
            return_value=self.fixture.reviewed_bundle,
        ), patch.object(
            module, "require_current_body_sway_dynamic_seam_heads",
            side_effect=AssertionError("historical head check attempted"),
        ) as heads:
            result = verify_body_sway_motion_instance_v3_command(
                self.fixture.state_root,
                self.fixture.reviewed_bundle.project_id,
                motion_instance_v3_sha256=
                    compiled.motion_instance_v3_sha256,
                bundle_sha256=compiled.bundle_sha256,
            )
        heads.assert_not_called()
        document = result.document
        self.assertEqual("verified", result.mode)
        self.assertFalse(document["head_check"]["current_heads_observed"])
        self.assertFalse(document["head_check"][
            "permanent_authority_claimed"
        ])
        self.assertIsNone(document["reused"])
        self.assertNotIn(str(self.fixture.root), json.dumps(document))
        with self.assertRaisesRegex(
            P10MotionInstanceV3CommandError,
            "MotionInstance v3 verification failed",
        ):
            verify_body_sway_motion_instance_v3_command(
                self.fixture.state_root,
                self.fixture.reviewed_bundle.project_id,
                motion_instance_v3_sha256="0" * 64,
                bundle_sha256=compiled.bundle_sha256,
            )


if __name__ == "__main__":
    unittest.main()
