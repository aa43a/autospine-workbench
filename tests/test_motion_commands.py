"""Exact-address command tests for reusable built-in MotionIR bundles."""

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

from autospine_workbench.cli import build_parser, main as cli_main  # noqa: E402
from autospine_workbench.motion_builtin import build_builtin_motion  # noqa: E402
from autospine_workbench.motion_bundle_contract import (  # noqa: E402
    build_motion_bundle_contract,
)
from autospine_workbench.motion_bundle_reader import (  # noqa: E402
    VerifiedMotionBundleReaderError,
)
from autospine_workbench.motion_bundle_store import (  # noqa: E402
    MotionBundleStoreError,
)
from autospine_workbench.motion_commands import (  # noqa: E402
    compile_builtin_motion_command,
    verify_motion_bundle_command,
)
from autospine_workbench.motion_compile_run import (  # noqa: E402
    build_builtin_motion_compile_run,
)


def invoke(function, *args, **kwargs):
    output = io.StringIO()
    with redirect_stdout(output):
        status = function(*args, **kwargs)
    return status, json.loads(output.getvalue())


def fake_stages(state: Path, clip_id: str = "idle"):
    motion = build_builtin_motion(clip_id)
    run = build_builtin_motion_compile_run(clip_id, motion.document)
    contract = build_motion_bundle_contract(motion.document, run.document)
    path = state / "motions" / contract.clip_sha256 / contract.bundle_sha256
    published = SimpleNamespace(
        path=path, clip_id=clip_id, clip_sha256=contract.clip_sha256,
        run_sha256=contract.run_sha256, bundle_sha256=contract.bundle_sha256,
        reused=False,
    )
    verified = SimpleNamespace(
        path=path, clip_id=clip_id, clip_sha256=contract.clip_sha256,
        run_sha256=contract.run_sha256, bundle_sha256=contract.bundle_sha256,
        document_bytes=contract.document_bytes,
    )
    return motion, run, published, verified


class CompileBuiltinMotionCommandTests(unittest.TestCase):
    def setUp(self):
        self.state = Path("exact-state")
        self.motion, self.run, self.published, self.verified = fake_stages(
            self.state
        )

    def run_success(self, *, published=None, verified=None):
        published = published or self.published
        verified = verified or self.verified
        with (
            patch("autospine_workbench.motion_commands.MotionBundleStore") as store,
            patch(
                "autospine_workbench.motion_commands.VerifiedMotionBundleReader"
            ) as reader,
        ):
            store.return_value.publish.return_value = published
            reader.return_value.load.return_value = verified
            result = invoke(
                compile_builtin_motion_command, "idle", self.state
            )
        return result, store, reader

    def test_runs_build_publish_readback_and_emits_stable_identity_json(self):
        (status, response), store, reader = self.run_success()
        self.assertEqual(0, status)
        self.assertEqual({
            "ok": True,
            "status": "passed",
            "clip_id": "idle",
            "clip_sha256": self.published.clip_sha256,
            "run_sha256": self.published.run_sha256,
            "bundle_sha256": self.published.bundle_sha256,
            "path": str(self.published.path),
            "reused": False,
        }, response)
        store.assert_called_once_with(self.state)
        store.return_value.publish.assert_called_once_with(
            self.motion.document, self.run.document
        )
        reader.assert_called_once_with(self.state)
        reader.return_value.load.assert_called_once_with(
            self.published.clip_sha256, self.published.bundle_sha256
        )

    def test_every_publication_and_reader_identity_plus_bytes_are_compared(self):
        publication_cases = (
            ("clip_id", "wave.left"),
            ("clip_sha256", "1" * 64),
            ("run_sha256", "2" * 64),
            ("bundle_sha256", None),
            ("path", "not-a-path"),
            ("reused", "yes"),
        )
        for field, value in publication_cases:
            changed = SimpleNamespace(**vars(self.published))
            setattr(changed, field, value)
            with self.subTest(stage="publish", field=field):
                (status, response), *_ = self.run_success(published=changed)
                self.assertEqual(2, status)
                self.assertIn("Published motion", response["error"])

        reader_cases = (
            ("clip_id", "wave.left"),
            ("clip_sha256", "3" * 64),
            ("run_sha256", "4" * 64),
            ("bundle_sha256", "5" * 64),
            ("path", self.verified.path.parent / ("6" * 64)),
            ("document_bytes", {"motion.json": b"{}"}),
        )
        for field, value in reader_cases:
            changed = SimpleNamespace(**vars(self.verified))
            setattr(changed, field, value)
            with self.subTest(stage="reader", field=field):
                (status, response), *_ = self.run_success(verified=changed)
                self.assertEqual(2, status)
                self.assertIn("Verified motion", response["error"])

    def test_invalid_id_algorithm_drift_and_domain_failures_are_json_exit_two(self):
        status, response = invoke(
            compile_builtin_motion_command, "latest", self.state
        )
        self.assertEqual(2, status)
        self.assertEqual({"ok", "status", "error"}, set(response))
        self.assertNotIn("Traceback", response["error"])

        with (
            patch(
                "autospine_workbench.motion_compile_run.build_builtin_motion",
                return_value=build_builtin_motion("wave.left"),
            ),
            patch("autospine_workbench.motion_commands.MotionBundleStore") as store,
        ):
            status, response = invoke(
                compile_builtin_motion_command, "idle", self.state
            )
        self.assertEqual(2, status)
        self.assertIn("differs", response["error"])
        store.assert_not_called()

        failures = (
            ("store", MotionBundleStoreError("store rejected")),
            ("reader", VerifiedMotionBundleReaderError("reader rejected")),
        )
        for stage, failure in failures:
            with (
                self.subTest(stage=stage),
                patch("autospine_workbench.motion_commands.MotionBundleStore") as store,
                patch(
                    "autospine_workbench.motion_commands.VerifiedMotionBundleReader"
                ) as reader,
            ):
                store.return_value.publish.return_value = self.published
                reader.return_value.load.return_value = self.verified
                target = store.return_value.publish if stage == "store" \
                    else reader.return_value.load
                target.side_effect = failure
                status, response = invoke(
                    compile_builtin_motion_command, "idle", self.state
                )
            self.assertEqual(2, status)
            self.assertEqual(str(failure), response["error"])


class VerifyMotionBundleCommandTests(unittest.TestCase):
    def test_exact_verify_is_read_only_and_idempotent_compile_reports_reuse(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory) / "state"
            first_status, first = invoke(
                compile_builtin_motion_command, "idle", state
            )
            second_status, second = invoke(
                compile_builtin_motion_command, "idle", state
            )
            before = _tree(state)
            verify_status, verified = invoke(
                verify_motion_bundle_command,
                state,
                clip_sha256=first["clip_sha256"],
                bundle_sha256=first["bundle_sha256"],
            )
            after = _tree(state)
        self.assertEqual((0, 0, 0), (first_status, second_status, verify_status))
        self.assertFalse(first["reused"])
        self.assertTrue(second["reused"])
        self.assertIsNone(verified["reused"])
        self.assertEqual(
            {key: first[key] for key in (
                "clip_id", "clip_sha256", "run_sha256", "bundle_sha256", "path"
            )},
            {key: verified[key] for key in (
                "clip_id", "clip_sha256", "run_sha256", "bundle_sha256", "path"
            )},
        )
        self.assertEqual(before, after)

    def test_invalid_addresses_and_reader_mismatch_fail_without_store_or_writes(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory) / "missing-state"
            for clip_sha, bundle_sha in (
                ("latest", "0" * 64),
                ("../escape", "0" * 64),
                ("0" * 64, "latest"),
            ):
                with self.subTest(clip=clip_sha, bundle=bundle_sha):
                    status, response = invoke(
                        verify_motion_bundle_command,
                        state,
                        clip_sha256=clip_sha,
                        bundle_sha256=bundle_sha,
                    )
                    self.assertEqual(2, status)
                    self.assertEqual("error", response["status"])
            self.assertFalse(state.exists())

        state = Path("state")
        _motion, _run, _published, verified = fake_stages(state)
        verified.document_bytes = {"motion.json": b"forged"}
        with (
            patch(
                "autospine_workbench.motion_commands.VerifiedMotionBundleReader"
            ) as reader,
            patch("autospine_workbench.motion_commands.MotionBundleStore") as store,
        ):
            reader.return_value.load.return_value = verified
            status, response = invoke(
                verify_motion_bundle_command,
                state,
                clip_sha256=verified.clip_sha256,
                bundle_sha256=verified.bundle_sha256,
            )
        self.assertEqual(2, status)
        self.assertIn("canonical bytes", response["error"])
        store.assert_not_called()


class MotionCliWiringTests(unittest.TestCase):
    def test_parsers_help_and_dispatch_preserve_only_exact_addresses(self):
        compile_args = build_parser().parse_args([
            "compile-builtin-motion", "idle", "--state-root", "state",
        ])
        self.assertEqual("idle", compile_args.clip_id)
        self.assertFalse(hasattr(compile_args, "bundle_sha256"))
        verify_args = build_parser().parse_args([
            "verify-motion-bundle", "--clip-sha256", "a" * 64,
            "--bundle-sha256", "b" * 64, "--state-root", "state",
        ])
        self.assertEqual("a" * 64, verify_args.clip_sha256)
        self.assertEqual("b" * 64, verify_args.bundle_sha256)
        self.assertFalse(hasattr(verify_args, "clip_id"))

        for command, expected in (
            ("compile-builtin-motion", "clip_id"),
            ("verify-motion-bundle", "--clip-sha256"),
        ):
            output = io.StringIO()
            with (
                self.subTest(help=command),
                redirect_stdout(output),
                self.assertRaises(SystemExit) as raised,
            ):
                build_parser().parse_args([command, "--help"])
            self.assertEqual(0, raised.exception.code)
            self.assertIn(expected, output.getvalue())
            self.assertNotIn("latest", output.getvalue().lower())

        with patch(
            "autospine_workbench.cli._compile_builtin_motion", return_value=7
        ) as command:
            status = cli_main([
                "compile-builtin-motion", "wave.left", "--state-root", "state",
            ])
        self.assertEqual(7, status)
        command.assert_called_once_with("wave.left", Path("state"))

        with patch(
            "autospine_workbench.cli._verify_motion_bundle", return_value=8
        ) as command:
            status = cli_main([
                "verify-motion-bundle", "--clip-sha256", "a" * 64,
                "--bundle-sha256", "b" * 64, "--state-root", "state",
            ])
        self.assertEqual(8, status)
        command.assert_called_once_with(
            Path("state"), clip_sha256="a" * 64, bundle_sha256="b" * 64
        )


def _tree(root: Path) -> dict[str, bytes]:
    if not root.exists():
        return {}
    return {
        item.relative_to(root).as_posix(): item.read_bytes()
        for item in root.rglob("*") if item.is_file()
    }


if __name__ == "__main__":
    unittest.main()
