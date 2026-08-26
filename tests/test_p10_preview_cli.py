"""End-to-end CLI output tests for the P10.3a preview compiler."""

from __future__ import annotations

from contextlib import redirect_stdout
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from autospine_workbench.cli import main  # noqa: E402
from tests.body_sway_preview_helpers import BodySwayPreviewFixture  # noqa: E402
from tests.p10_decision_command_helpers import write_json  # noqa: E402
from tests.p9_v2_helpers import tree  # noqa: E402


class P10PreviewCliTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temporary.name)
        cls.fixture = BodySwayPreviewFixture(cls.root)
        inputs = cls.root / "cli-inputs"
        inputs.mkdir()
        cls.candidates = write_json(
            inputs / "candidates.json", cls.fixture.candidates
        )
        cls.decision = write_json(
            inputs / "decision.json", cls.fixture.decision
        )
        cls.report = write_json(
            inputs / "report.json", cls.fixture.report.document
        )

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def argv(self, *, document_only=False):
        values = [
            "compile-body-sway-preview",
            self.fixture.persisted.mesh.project_id,
            "--candidates", str(self.candidates),
            "--decision", str(self.decision),
            "--probe-report", str(self.report),
            "--state-root", str(self.fixture.persisted.state),
        ]
        for field, value in self.fixture.persisted.command_kwargs.items():
            values.extend((f"--{field.replace('_', '-')}", value))
        if document_only:
            values.append("--document-only")
        return values

    def run_cli(self, *, document_only=False):
        with redirect_stdout(io.StringIO()) as output:
            status = main(self.argv(document_only=document_only))
        return status, output.getvalue().strip()

    def test_document_only_is_deterministic_canonical_and_zero_write(self):
        before = tree(self.root)
        first = self.run_cli(document_only=True)
        second = self.run_cli(document_only=True)
        self.assertEqual((0, first[1]), first)
        self.assertEqual(first, second)
        self.assertEqual(before, tree(self.root))
        document = json.loads(first[1])
        self.assertEqual(
            "autospine-temporary-body-sway-preview", document["format"]
        )
        self.assertEqual(json.dumps(
            document, ensure_ascii=False, allow_nan=False,
            sort_keys=True, separators=(",", ":"),
        ), first[1])

    def test_default_payload_exposes_hashes_and_manifest_but_no_bytes(self):
        status, text = self.run_cli()
        payload = json.loads(text)
        self.assertEqual(0, status)
        self.assertTrue(payload["ok"])
        self.assertEqual(
            "ready_for_official_runtime_capture", payload["status"]
        )
        self.assertEqual(7, len(payload["input_paths"]))
        self.assertEqual(5, len(payload["artifact_files"]))
        self.assertEqual(
            payload["artifact_set_sha256"],
            payload["manifest"]["artifacts"]["artifact_set_sha256"],
        )
        manifest_bytes = json.dumps(
            payload["manifest"], ensure_ascii=False, allow_nan=False,
            sort_keys=True, separators=(",", ":"),
        ).encode("utf-8")
        self.assertEqual(
            hashlib.sha256(manifest_bytes).hexdigest(),
            payload["temporary_preview_sha256"],
        )
        self.assertNotIn("artifact_bytes", payload)
        self.assertNotIn("_preview", payload)

    def test_invalid_exact_address_returns_canonical_error(self):
        argv = self.argv()
        index = argv.index("--p3-rig-sha256") + 1
        argv[index] = "f" * 64
        with redirect_stdout(io.StringIO()) as output:
            status = main(argv)
        payload = json.loads(output.getvalue())
        self.assertEqual(2, status)
        self.assertFalse(payload["ok"])
        self.assertEqual("error", payload["status"])


if __name__ == "__main__":
    unittest.main()
