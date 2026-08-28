"""Keep the P10.7c operator draft bound to current approved P6 evidence."""

from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from autospine_workbench.safe_input_files import strict_json_object  # noqa: E402
from autospine_workbench.spine42_v3_setup_regression_manifest import (  # noqa: E402
    canonical_request_bytes,
    parse_spine42_v3_setup_regression_request,
    require_spine42_v3_setup_regression_request,
)


TEMPLATE = (
    ROOT / "examples" / "p10-spine42-v3-setup-regression" /
    "real-see-through.template.request.json"
)
P6_ROOT = ROOT / "tests" / "goldens" / "p6-spine42"


class Spine42V3SetupRegressionTemplateTests(unittest.TestCase):
    def test_draft_is_semantic_and_approval_hashes_are_current(self):
        draft = require_spine42_v3_setup_regression_request(
            strict_json_object(TEMPLATE.read_bytes(), "P10.7c draft")
        )
        self.assertEqual(
            hashlib.sha256((P6_ROOT / "real-exports.approved.json").read_bytes()).hexdigest(),
            draft["approved_p6_export_contract_sha256"],
        )
        self.assertEqual(
            hashlib.sha256((P6_ROOT / "runtime.approved.json").read_bytes()).hexdigest(),
            draft["approved_runtime_golden_sha256"],
        )
        self.assertEqual(
            draft,
            parse_spine42_v3_setup_regression_request(
                canonical_request_bytes(draft)
            ),
        )

    def test_only_future_p10_addresses_are_placeholders(self):
        draft = strict_json_object(TEMPLATE.read_bytes(), "P10.7c draft")
        zero = "0" * 64
        for sample in draft["samples"]:
            self.assertEqual(zero, sample["spine42_v3_address"]["skeleton_json_sha256"])
            self.assertEqual(zero, sample["spine42_v3_address"]["bundle_sha256"])
            self.assertEqual(zero, sample["runtime_capture_address"]["capture_bundle_sha256"])
            self.assertEqual(
                sample["spine42_v3_address"]["bundle_sha256"],
                sample["runtime_capture_address"]["spine42_v3_bundle_sha256"],
            )

    def test_canonicalizer_publishes_atomically_without_overwrite(self):
        tool = ROOT / "tools" / \
            "canonicalize_spine42_v3_setup_regression_request.py"
        spec = importlib.util.spec_from_file_location("p10_canonicalizer", tool)
        self.assertIsNotNone(spec)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "request.json"
            module._write_new_atomic(output, b"first")
            with self.assertRaises(FileExistsError):
                module._write_new_atomic(output, b"second")
            self.assertEqual(b"first", output.read_bytes())
            self.assertEqual([output], list(Path(temporary).iterdir()))


if __name__ == "__main__":
    unittest.main()
