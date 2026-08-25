"""Exact-address P4 IK command tests."""

from __future__ import annotations

from contextlib import redirect_stdout
from copy import deepcopy
import io
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from autospine_workbench.cli import main as cli_main  # noqa: E402
from autospine_workbench.ik_bundle_reader import (  # noqa: E402
    VerifiedIkBundleReaderError,
)
from autospine_workbench.ik_bundle_store import IkBundleStoreError  # noqa: E402
from autospine_workbench.ik_commands import (  # noqa: E402
    compile_ik_targets_command,
    verify_ik_bundle_command,
)
from autospine_workbench.ik_pipeline import VerifiedIkPipelineError  # noqa: E402
from autospine_workbench.ik_target_geometry import SOURCE_IDENTITY_FIELDS  # noqa: E402
from tests.test_ik_target_profile import verified_bundle  # noqa: E402


PROJECT = "sample-a"
SOURCE = dict(zip(SOURCE_IDENTITY_FIELDS, (
    "a" * 64, "b" * 64, "c" * 64, "d" * 64, "e" * 64,
    "f" * 64, "1" * 64, "2" * 64, "3" * 64,
)))
PROFILE, PROBES, BUNDLE = "4" * 64, "5" * 64, "6" * 64


def fake_pipeline():
    return SimpleNamespace(
        project_id=PROJECT, summary="handles=4",
        profile={"source": deepcopy(SOURCE), "handles": [{}, {}, {}, {}]},
        probes={"status": "passed"}, input_sha256s=deepcopy(SOURCE),
        output_sha256s={"profile_sha256": PROFILE, "probes_sha256": PROBES},
    )


def fake_verified(state: Path):
    return SimpleNamespace(
        path=state / "builds" / PROJECT / "ik-targets" / PROFILE / BUNDLE,
        project_id=PROJECT, profile_sha256=PROFILE, probes_sha256=PROBES,
        bundle_sha256=BUNDLE, p3_rig_sha256=SOURCE["rig_sha256"],
        p3_bundle_sha256=SOURCE["bundle_sha256"],
        source_identities=deepcopy(SOURCE),
        profile={"handles": [{}, {}, {}, {}]}, probes={"status": "passed"},
    )


def invoke(function, *args, **kwargs):
    output = io.StringIO()
    with redirect_stdout(output):
        status = function(*args, **kwargs)
    return status, json.loads(output.getvalue())


class CompileIkTargetsCommandTests(unittest.TestCase):
    def setUp(self):
        self.state = Path("exact-state")
        self.pipeline = fake_pipeline()
        self.verified = fake_verified(self.state)
        self.published = SimpleNamespace(
            path=self.verified.path, profile_sha256=PROFILE, bundle_sha256=BUNDLE,
        )

    def run_success(self, *, verified=None):
        verified = verified or self.verified
        with (
            patch("autospine_workbench.ik_commands.VerifiedIkPipeline") as pipeline,
            patch("autospine_workbench.ik_commands.IkBundleStore") as store,
            patch("autospine_workbench.ik_commands.VerifiedIkBundleReader") as reader,
        ):
            pipeline.return_value.build.return_value = self.pipeline
            store.return_value.publish.return_value = self.published
            reader.return_value.load.return_value = verified
            result = invoke(
                compile_ik_targets_command, PROJECT, self.state,
                p3_rig_sha256=SOURCE["rig_sha256"],
                p3_bundle_sha256=SOURCE["bundle_sha256"],
            )
        return result, pipeline, store, reader

    def test_success_runs_exact_pipeline_publish_and_strict_readback(self):
        (status, response), pipeline, store, reader = self.run_success()
        self.assertEqual(0, status)
        self.assertEqual({
            "ok": True, "status": "passed", "summary": "handles=4",
            "project_id": PROJECT, "p3_source": SOURCE,
            "profile_sha256": PROFILE, "probes_sha256": PROBES,
            "bundle_sha256": BUNDLE, "path": str(self.verified.path),
        }, response)
        pipeline.assert_called_once_with(self.state)
        pipeline.return_value.build.assert_called_once_with(
            PROJECT, SOURCE["rig_sha256"], SOURCE["bundle_sha256"]
        )
        store.assert_called_once_with(self.state)
        store.return_value.publish.assert_called_once_with(
            PROJECT, self.pipeline.profile, self.pipeline.probes
        )
        reader.assert_called_once_with(self.state)
        reader.return_value.load.assert_called_once_with(PROJECT, PROFILE, BUNDLE)

    def test_all_nine_p3_identities_and_every_p4_readback_identity_are_compared(self):
        cases = [(f"p3:{field}", field, "source") for field in SOURCE_IDENTITY_FIELDS]
        cases.extend((
            ("profile", "profile_sha256", "field"),
            ("probes", "probes_sha256", "field"),
            ("bundle", "bundle_sha256", "field"),
            ("path", "path", "field"),
        ))
        for label, field, kind in cases:
            changed = fake_verified(self.state)
            if kind == "source":
                changed.source_identities[field] = "9" * 64
            elif field == "path":
                changed.path = changed.path.parent / ("9" * 64)
            else:
                setattr(changed, field, "9" * 64)
            with self.subTest(label=label):
                (status, response), *_rest = self.run_success(verified=changed)
                self.assertEqual(2, status)
                self.assertIn(field, response["error"])

    def test_pipeline_store_and_reader_domain_errors_exit_two(self):
        stages = ("pipeline", "store", "reader")
        for stage in stages:
            with (
                self.subTest(stage=stage),
                patch("autospine_workbench.ik_commands.VerifiedIkPipeline") as pipeline,
                patch("autospine_workbench.ik_commands.IkBundleStore") as store,
                patch("autospine_workbench.ik_commands.VerifiedIkBundleReader") as reader,
            ):
                pipeline.return_value.build.return_value = self.pipeline
                store.return_value.publish.return_value = self.published
                reader.return_value.load.return_value = self.verified
                if stage == "pipeline":
                    pipeline.return_value.build.side_effect = VerifiedIkPipelineError("bad pipeline")
                elif stage == "store":
                    store.return_value.publish.side_effect = IkBundleStoreError("bad store")
                else:
                    reader.return_value.load.side_effect = VerifiedIkBundleReaderError("bad reader")
                status, response = invoke(
                    compile_ik_targets_command, PROJECT, self.state,
                    p3_rig_sha256=SOURCE["rig_sha256"],
                    p3_bundle_sha256=SOURCE["bundle_sha256"],
                )
                self.assertEqual(2, status)
                self.assertEqual("error", response["status"])
                if stage == "pipeline":
                    store.assert_not_called()
                    reader.assert_not_called()
                elif stage == "store":
                    reader.assert_not_called()

    def test_summary_requires_exactly_four_handles_and_passed_probes(self):
        for field in ("handles", "probes"):
            changed = fake_verified(self.state)
            if field == "handles":
                changed.profile["handles"].pop()
            else:
                changed.probes["status"] = "rejected"
            with self.subTest(field=field):
                (status, response), *_rest = self.run_success(verified=changed)
                self.assertEqual(2, status)
                self.assertIn("handle inventory", response["error"])


class VerifyIkBundleCommandTests(unittest.TestCase):
    def test_verify_passes_only_exact_address_and_domain_errors_exit_two(self):
        state, verified = Path("state"), fake_verified(Path("state"))
        with patch("autospine_workbench.ik_commands.VerifiedIkBundleReader") as reader:
            reader.return_value.load.return_value = verified
            status, response = invoke(
                verify_ik_bundle_command, PROJECT, state,
                profile_sha256=PROFILE, bundle_sha256=BUNDLE,
            )
        self.assertEqual(0, status)
        self.assertEqual("handles=4", response["summary"])
        reader.assert_called_once_with(state)
        reader.return_value.load.assert_called_once_with(PROJECT, PROFILE, BUNDLE)
        with patch("autospine_workbench.ik_commands.VerifiedIkBundleReader") as reader:
            reader.return_value.load.side_effect = VerifiedIkBundleReaderError("tampered")
            status, response = invoke(
                verify_ik_bundle_command, PROJECT, state,
                profile_sha256=PROFILE, bundle_sha256=BUNDLE,
            )
        self.assertEqual(2, status)
        self.assertEqual("tampered", response["error"])

    def test_real_noop_compile_then_verify_is_read_only(self):
        with tempfile.TemporaryDirectory() as directory:
            state, base = Path(directory) / "state", verified_bundle(converted=False)
            with (
                patch("autospine_workbench.ik_pipeline.VerifiedMeshBundleReader") as pipeline_reader,
                patch("autospine_workbench.ik_bundle_integrity.VerifiedMeshBundleReader") as integrity_reader,
            ):
                pipeline_reader.return_value.load.return_value = base
                integrity_reader.return_value.load.return_value = base
                status, compiled = invoke(
                    compile_ik_targets_command, base.project_id, state,
                    p3_rig_sha256=base.rig_sha256,
                    p3_bundle_sha256=base.bundle_sha256,
                )
                self.assertEqual(0, status)
                before = _tree(state)
                status, verified = invoke(
                    verify_ik_bundle_command, base.project_id, state,
                    profile_sha256=compiled["profile_sha256"],
                    bundle_sha256=compiled["bundle_sha256"],
                )
                after = _tree(state)
        self.assertEqual(0, status)
        self.assertEqual("handles=4", verified["summary"])
        self.assertEqual(compiled["path"], verified["path"])
        self.assertEqual(before, after)


class IkCliWiringTests(unittest.TestCase):
    def test_main_routes_both_exact_commands_without_latest(self):
        with patch("autospine_workbench.cli._compile_ik_targets", return_value=7) as command:
            status = cli_main([
                "compile-ik-targets", PROJECT,
                "--p3-rig-sha256", SOURCE["rig_sha256"],
                "--p3-bundle-sha256", SOURCE["bundle_sha256"],
                "--state-root", "state",
            ])
        self.assertEqual(7, status)
        command.assert_called_once_with(
            PROJECT, Path("state"), p3_rig_sha256=SOURCE["rig_sha256"],
            p3_bundle_sha256=SOURCE["bundle_sha256"],
        )
        with patch("autospine_workbench.cli._verify_ik_bundle", return_value=8) as command:
            status = cli_main([
                "verify-ik-bundle", PROJECT,
                "--profile-sha256", PROFILE, "--bundle-sha256", BUNDLE,
                "--state-root", "state",
            ])
        self.assertEqual(8, status)
        command.assert_called_once_with(
            PROJECT, Path("state"), profile_sha256=PROFILE,
            bundle_sha256=BUNDLE,
        )


def _tree(root: Path) -> dict[str, bytes]:
    return {item.relative_to(root).as_posix(): item.read_bytes()
            for item in root.rglob("*") if item.is_file()}


if __name__ == "__main__":
    unittest.main()
