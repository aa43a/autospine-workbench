"""Ordering, concurrency, input, and zero-write tests for P10.6a."""

from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for item in (ROOT, SRC):
    if str(item) not in sys.path:
        sys.path.insert(0, str(item))

from autospine_workbench.p10_motion_consumer_admission_commands import (  # noqa: E402
    P10MotionConsumerAdmissionCommandError,
    compile_body_sway_motion_consumer_admission_command,
)
from tests.p10_motion_consumer_admission_command_helpers import (  # noqa: E402
    SHAS,
    observation,
    patched_command_pipeline,
    probe_document,
    write_probe,
)
from tests.p9_v2_helpers import tree  # noqa: E402


def compile_at(root: Path, probe_path: Path, *, sha=SHAS[0]):
    return compile_body_sway_motion_consumer_admission_command(
        root, "fixture-project", probe_path,
        dynamic_seam_probe_sha256=sha,
    )


class P10MotionConsumerAdmissionCommandTests(unittest.TestCase):
    def test_exact_order_output_and_zero_write(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            probe_path = write_probe(root)
            before_tree = tree(root)
            with patched_command_pipeline() as fixture:
                result = compile_at(root, probe_path)
            after_tree = tree(root)
        self.assertEqual(before_tree, after_tree)
        self.assertEqual([
            "probe-hash", "bundle", "head", "compile", "head", "seal",
            "validate", "admission-hash",
        ], fixture.order)
        document = result.document
        self.assertEqual(fixture.admission.document, document["admission"])
        self.assertEqual(SHAS[4], document[
            "body_sway_motion_consumer_admission_sha256"
        ])
        self.assertEqual({
            "motion_instance_v2_sha256": SHAS[1],
            "reviewed_motion_bundle_sha256": SHAS[2],
        }, document["reviewed_motion_address"])
        head = document["head_observation"]
        self.assertEqual(
            "outer-before-after-consumer-core-compilation", head["method"]
        )
        self.assertEqual("compile_time", head["scope"])
        self.assertFalse(head["permanent_authority_claimed"])
        encoded = str(document)
        self.assertNotIn(str(root), encoded)
        self.assertNotIn("dynamic-seam-probe.json", encoded)

    def test_exact_probe_address_and_embedded_p9_feed_pipeline(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            probe_path = write_probe(root)
            with patched_command_pipeline() as fixture:
                compile_at(root, probe_path)
        fixture.reader_class.assert_called_once_with(root)
        fixture.reader_class.return_value.load.assert_called_once_with(
            "fixture-project", SHAS[1], SHAS[2]
        )
        fixture.compiler.assert_called_once_with(
            probe_document(), fixture.bundle
        )
        self.assertEqual(2, fixture.head_check.call_count)
        self.assertEqual(
            probe_document()["source"],
            fixture.head_check.call_args_list[0].args[1],
        )
        fixture.sealer.assert_called_once()
        fixture.validator.assert_called_once_with(
            fixture.admission.document,
            dynamic_seam_probe=probe_document(),
            reviewed_bundle=fixture.bundle,
        )
        fixture.admission_hash.assert_called_once_with(
            fixture.admission.document,
            dynamic_seam_probe=probe_document(),
            reviewed_bundle=fixture.bundle,
        )

    def test_explicit_probe_sha_project_and_bundle_must_match(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            probe_path = write_probe(root)
            with patched_command_pipeline() as fixture, self.assertRaisesRegex(
                P10MotionConsumerAdmissionCommandError, "explicit address"
            ):
                compile_at(root, probe_path, sha=SHAS[5])
            fixture.reader_class.return_value.load.assert_not_called()
        document = probe_document()
        document["project_id"] = "cross-project"
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            probe_path = write_probe(root, raw=json.dumps(document))
            with patched_command_pipeline() as fixture, self.assertRaisesRegex(
                P10MotionConsumerAdmissionCommandError, "project"
            ):
                compile_at(root, probe_path)
            fixture.reader_class.return_value.load.assert_not_called()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            probe_path = write_probe(root)
            with patched_command_pipeline() as fixture:
                fixture.bundle.bundle_sha256 = SHAS[5]
                with self.assertRaisesRegex(
                    P10MotionConsumerAdmissionCommandError, "embedded exact"
                ):
                    compile_at(root, probe_path)

    def test_head_drift_fails_before_seal_and_public_validation(self):
        attacks = (
            (observation(identity="before"), observation(identity="after")),
            (observation(marker="before"), observation(marker="after")),
        )
        for before, after in attacks:
            with self.subTest(identity=before.identity), \
                    tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                probe_path = write_probe(root)
                with patched_command_pipeline(
                    before=before, after=after
                ) as fixture, self.assertRaises(
                    P10MotionConsumerAdmissionCommandError
                ):
                    compile_at(root, probe_path)
                fixture.sealer.assert_not_called()
                fixture.validator.assert_not_called()

    def test_bounded_strict_input_and_domain_failures_are_closed(self):
        invalid = (
            '{"project_id":"fixture-project","project_id":"again"}',
            '{"project_id":"fixture-project","bad":NaN}',
            "[]",
        )
        for raw in invalid:
            with self.subTest(raw=raw), \
                    tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                probe_path = write_probe(root, raw=raw)
                with patched_command_pipeline() as fixture, self.assertRaises(
                    P10MotionConsumerAdmissionCommandError
                ):
                    compile_at(root, probe_path)
                fixture.probe_hash.assert_not_called()
        failures = (
            {"probe_failure": ValueError("private probe failure")},
            {"compile_failure": ValueError("private compile failure")},
            {"validation_failure": ValueError("private validation failure")},
        )
        for options in failures:
            with self.subTest(options=tuple(options)), \
                    tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                probe_path = write_probe(root)
                with patched_command_pipeline(**options), self.assertRaises(
                    P10MotionConsumerAdmissionCommandError
                ) as raised:
                    compile_at(root, probe_path)
                self.assertEqual(
                    "Body-sway motion-consumer admission compilation failed",
                    str(raised.exception),
                )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            probe_path = write_probe(root)
            with patch(
                "autospine_workbench.p10_motion_consumer_admission_commands."
                "MAX_DYNAMIC_SEAM_PROBE_BYTES", 1,
            ), patched_command_pipeline() as fixture, self.assertRaises(
                P10MotionConsumerAdmissionCommandError
            ):
                compile_at(root, probe_path)
            fixture.probe_hash.assert_not_called()

    def test_result_is_copy_isolated_and_command_has_no_mutation_boundary(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            probe_path = write_probe(root)
            with patched_command_pipeline():
                result = compile_at(root, probe_path)
            first = result.document
            first["admission"]["status"] = "forged"
            self.assertEqual("fixture-admitted", result.document[
                "admission"
            ]["status"])
        source = (SRC / "autospine_workbench" /
                  "p10_motion_consumer_admission_commands.py").read_text(
                      encoding="utf-8"
                  )
        for forbidden in (
            ".glob(", ".rglob(", "publish_", "write_", "mkdir(", "latest",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
