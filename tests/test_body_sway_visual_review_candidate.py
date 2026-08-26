"""P10.3c candidate-only visual review contract tests."""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for candidate in (ROOT, SRC):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

try:
    from jsonschema import Draft202012Validator
except ImportError:  # pragma: no cover - optional test dependency
    Draft202012Validator = None

from autospine_workbench.body_sway_runtime_capture_reader import (  # noqa: E402
    VerifiedBodySwayRuntimeCapture,
    VerifiedBodySwayRuntimeCaptureReader,
)
from autospine_workbench.body_sway_runtime_capture import (  # noqa: E402
    BodySwayRuntimeCapture,
)
from autospine_workbench.body_sway_visual_review_candidate import (  # noqa: E402
    BodySwayVisualReviewCandidateError,
    compile_body_sway_visual_review_candidate,
)
from autospine_workbench.body_sway_visual_review_candidate_validation import (  # noqa: E402
    BodySwayVisualReviewCandidateValidationError,
    require_body_sway_visual_review_candidate,
)
from tests.body_sway_runtime_capture_helpers import (  # noqa: E402
    fake_runtime_profile,
)
from tests.body_sway_visual_review_helpers import (  # noqa: E402
    BodySwayVisualReviewFixture,
)


class BodySwayVisualReviewCandidateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.fixture = BodySwayVisualReviewFixture(self.root)
        with fake_runtime_profile():
            self.capture = VerifiedBodySwayRuntimeCaptureReader(
                self.fixture.state_root
            ).load(*self.fixture.address)
            self.candidate = compile_body_sway_visual_review_candidate(
                self.capture
            )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_is_deterministic_candidate_only_and_binds_every_png(self) -> None:
        with fake_runtime_profile():
            again = compile_body_sway_visual_review_candidate(self.capture)
        self.assertEqual(self.candidate.sha256, again.sha256)
        self.assertEqual(self.candidate.canonical_bytes, again.canonical_bytes)

        document = self.candidate.document
        capture = self.capture.capture.document
        self.assertEqual("candidate_only", document["status"])
        self.assertEqual("blocked", document["release_gate"]["status"])
        self.assertFalse(document["semantics"]["human_review_claimed"])
        self.assertEqual(
            "shape-and-internal-compiler-seals-only",
            document["semantics"]["detached_validation_scope"],
        )
        self.assertTrue(
            document["semantics"]["content_digests_are_compiler_seals"]
        )
        self.assertTrue(document["semantics"]["exact_source_replay_required"])
        self.assertEqual([row["case_id"] for row in capture["cases"]],
                         [row["case_id"] for row in document["cases"]])
        artifacts = {
            row["case_id"]: row for row in capture["artifacts"]["files"]
        }
        for row in document["cases"]:
            self.assertEqual(artifacts[row["case_id"]]["sha256"],
                             row["image"]["png_sha256"])

    def test_pure_compiler_rebuilds_bundle_and_rejects_forged_verified(self) -> None:
        captures = list(self.capture.capture.capture_bytes.items())
        path, payload = captures[0]
        captures[0] = (path, payload[:-1] + bytes([payload[-1] ^ 1]))
        inconsistent_capture = BodySwayRuntimeCapture(
            self.capture.capture.canonical_bytes.decode("utf-8"),
            tuple(captures),
        )
        forged_values = (
            VerifiedBodySwayRuntimeCapture(
                self.capture.path,
                inconsistent_capture,
                self.capture.bundle_sha256,
            ),
            VerifiedBodySwayRuntimeCapture(
                self.capture.path,
                self.capture.capture,
                "a" * 64,
            ),
        )
        for forged in forged_values:
            with self.subTest(forged=forged), fake_runtime_profile(), \
                    self.assertRaises(BodySwayVisualReviewCandidateError):
                compile_body_sway_visual_review_candidate(forged)

    def test_source_binds_all_required_capture_and_browser_identities(self) -> None:
        source = self.candidate.document["source"]
        self.assertEqual(
            {
                "browser_profile_sha256",
                "capture_artifact_set_sha256",
                "capture_case_stream_sha256",
                "runtime_capture_bundle_sha256",
                "runtime_capture_manifest_sha256",
                "temporary_preview_sha256",
            },
            set(source),
        )
        self.assertEqual(self.capture.bundle_sha256,
                         source["runtime_capture_bundle_sha256"])
        self.assertEqual(self.capture.capture.artifact_set_sha256,
                         source["capture_artifact_set_sha256"])

    def test_standalone_and_exact_capture_validation_reject_resealing(self) -> None:
        original = self.candidate.document
        mutations = []
        source = deepcopy(original)
        source["source"]["browser_profile_sha256"] = "a" * 64
        mutations.append(source)
        case = deepcopy(original)
        case["cases"][0]["image"]["png_sha256"] = "a" * 64
        mutations.append(case)
        evidence = deepcopy(original)
        evidence["cases"][0]["evidence_sha256"] = "a" * 64
        mutations.append(evidence)
        omitted = deepcopy(original)
        omitted["cases"].pop()
        omitted["summary"]["case_count"] -= 1
        omitted["summary"]["pending_count"] -= 1
        mutations.append(omitted)

        for document in mutations:
            with self.subTest(document=document):
                with fake_runtime_profile(), self.assertRaises(
                    BodySwayVisualReviewCandidateValidationError
                ):
                    require_body_sway_visual_review_candidate(
                        document, capture=self.capture
                    )

    @unittest.skipIf(Draft202012Validator is None, "jsonschema is optional")
    def test_json_schema_accepts_compiled_candidate(self) -> None:
        schema = json.loads((
            ROOT / "schemas" / "body-sway-visual-review-candidate-v1.schema.json"
        ).read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        validator = Draft202012Validator(schema)
        validator.validate(self.candidate.document)
        invalid = self.candidate.document
        invalid["cases"][0]["time_seconds"] = 600.01
        self.assertFalse(validator.is_valid(invalid))


if __name__ == "__main__":
    unittest.main()
