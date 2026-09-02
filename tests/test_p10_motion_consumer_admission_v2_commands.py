"""Exact ordering and fail-closed tests for P10.6a v2 orchestration."""

from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for item in (ROOT, SRC):
    if str(item) not in sys.path:
        sys.path.insert(0, str(item))

from autospine_workbench.p10_motion_consumer_admission_commands_v2 import (  # noqa: E402
    P10MotionConsumerAdmissionCommandV2Error,
    compile_body_sway_motion_consumer_admission_v2_command,
)
from autospine_workbench.body_sway_dynamic_seam_bundle_contract_v2 import (  # noqa: E402
    DOCUMENT_NAMES,
)
from autospine_workbench.project_store import ProjectStore  # noqa: E402
from tests.body_sway_motion_consumer_v2_helpers import (  # noqa: E402
    consumer_v2_fixture,
    validated_dynamic_documents,
)
from tests.p10_motion_consumer_admission_v2_command_helpers import (  # noqa: E402
    SHAS,
    observation,
    patched_v2_command_pipeline,
)


def store(root):
    return ProjectStore(
        root, state_root=root / "state", measure_composite_quality=False,
    )


def compile_at(value):
    return compile_body_sway_motion_consumer_admission_v2_command(
        object_with_get(), value, "fixture-project",
        dynamic_seam_probe_sha256=SHAS[0],
        dynamic_seam_bundle_sha256=SHAS[1],
    )


def object_with_get():
    return type("ReadOnlyJobs", (), {"get": lambda self, _job: {}})()


def state_tree_bytes(root):
    return tuple(
        (path.relative_to(root).as_posix(), path.read_bytes())
        for path in sorted(root.rglob("*")) if path.is_file()
    )


class P10MotionConsumerAdmissionV2CommandTests(unittest.TestCase):
    def test_exact_read_p9_heads_core_seal_replay_order_and_output(self):
        with tempfile.TemporaryDirectory() as temporary, \
                patched_v2_command_pipeline() as fixture:
            value = store(Path(temporary))
            before = tuple(value.state_root.rglob("*"))
            result = compile_at(value)
            after = tuple(value.state_root.rglob("*"))
        self.assertEqual(before, after)
        self.assertEqual(
            ["dynamic", "p9", "head", "core", "head", "seal", "replay"],
            fixture.order,
        )
        fixture.dynamic_reader.assert_called_once_with(value.state_root)
        fixture.dynamic_reader.return_value.load.assert_called_once_with(
            "fixture-project", SHAS[0], SHAS[1],
        )
        fixture.reviewed_reader.return_value.load.assert_called_once_with(
            "fixture-project", SHAS[2], SHAS[3],
        )
        fixture.compiler.assert_called_once_with(
            fixture.dynamic, fixture.reviewed,
        )
        self.assertEqual(2, fixture.head_check.call_count)
        document = result.document
        self.assertEqual({
            "probe_sha256": SHAS[0], "bundle_sha256": SHAS[1],
        }, document["dynamic_seam_address"])
        self.assertEqual(2, document["admission"]["format_version"])
        self.assertFalse(document["head_observation"]
                         ["permanent_authority_claimed"])

    def test_head_identity_or_bytes_drift_fails_before_seal(self):
        cases = (
            (observation(identity=SHAS[6]), observation(identity=SHAS[7])),
            (observation(marker="before"), observation(marker="after")),
        )
        for before, after in cases:
            with self.subTest(identity=after.identity_sha256), \
                    tempfile.TemporaryDirectory() as temporary, \
                    patched_v2_command_pipeline(
                        before=before, after=after,
                    ) as fixture, self.assertRaises(
                        P10MotionConsumerAdmissionCommandV2Error
                    ):
                compile_at(store(Path(temporary)))
            fixture.sealer.assert_not_called()
            fixture.replay.assert_not_called()

    def test_invalid_stores_addresses_and_domain_failures_are_closed(self):
        with tempfile.TemporaryDirectory() as temporary, \
                self.assertRaises(P10MotionConsumerAdmissionCommandV2Error):
            compile_body_sway_motion_consumer_admission_v2_command(
                object(), store(Path(temporary)), "fixture-project",
                dynamic_seam_probe_sha256=SHAS[0],
                dynamic_seam_bundle_sha256=SHAS[1],
            )
        with tempfile.TemporaryDirectory() as temporary, \
                patched_v2_command_pipeline() as fixture, \
                self.assertRaises(P10MotionConsumerAdmissionCommandV2Error):
            compile_body_sway_motion_consumer_admission_v2_command(
                object_with_get(), store(Path(temporary)), "fixture-project",
                dynamic_seam_probe_sha256="not-a-digest",
                dynamic_seam_bundle_sha256=SHAS[1],
            )
        fixture.dynamic_reader.return_value.load.assert_not_called()
        failures = (
            {"read_failure": ValueError(r"C:\private\bundle")},
            {"compile_failure": ValueError(r"C:\private\core")},
            {"replay_failure": ValueError(r"C:\private\replay")},
        )
        for options in failures:
            with self.subTest(options=tuple(options)), \
                    tempfile.TemporaryDirectory() as temporary, \
                    patched_v2_command_pipeline(**options), \
                    self.assertRaises(
                        P10MotionConsumerAdmissionCommandV2Error
                    ) as raised:
                compile_at(store(Path(temporary)))
            self.assertEqual(
                "Body-sway motion-consumer admission v2 compilation failed",
                str(raised.exception),
            )

    def test_exact_disk_tamper_fails_without_writing_state(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _fixture, _p9, dynamic, _contract = consumer_v2_fixture(root)
            target = dynamic.path / DOCUMENT_NAMES[2]
            target.write_bytes(b"{}")
            value = store(root)
            before = state_tree_bytes(value.state_root)
            with validated_dynamic_documents(
                dynamic.source, dynamic.probe,
            ), self.assertRaises(P10MotionConsumerAdmissionCommandV2Error):
                compile_body_sway_motion_consumer_admission_v2_command(
                    object_with_get(), value, dynamic.project_id,
                    dynamic_seam_probe_sha256=dynamic.probe_sha256,
                    dynamic_seam_bundle_sha256=dynamic.bundle_sha256,
                )
            after = state_tree_bytes(value.state_root)
        self.assertEqual(before, after)

    def test_source_contains_no_path_scan_or_mutation_boundary(self):
        source = (SRC / "autospine_workbench" /
                  "p10_motion_consumer_admission_commands_v2.py").read_text(
                      encoding="utf-8"
                  )
        for forbidden in (
            ".glob(", ".rglob(", "publish_", "write_", "mkdir(", "latest",
            "read_real_file", "strict_json_object",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
