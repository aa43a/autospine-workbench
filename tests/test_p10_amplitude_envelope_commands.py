"""Exact-command and concurrency tests for P10.4b1 gain candidates."""

from __future__ import annotations

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

from autospine_workbench.body_sway_amplitude_envelope import (  # noqa: E402
    compile_body_sway_amplitude_envelope_candidate,
)
from autospine_workbench.p10_amplitude_envelope_commands import (  # noqa: E402
    P10AmplitudeEnvelopeCommandError,
    compile_body_sway_amplitude_envelope_command,
)
from tests.body_sway_runtime_capture_helpers import (  # noqa: E402
    fake_runtime_profile,
)
from tests.p10_review_admission_helpers import (  # noqa: E402
    P10ReviewAdmissionFixture,
)
from tests.p9_v2_helpers import tree  # noqa: E402


class P10AmplitudeEnvelopeCommandTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temporary = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temporary.name)
        cls.fixture = P10ReviewAdmissionFixture(cls.root)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temporary.cleanup()

    def compile(self, fixture=None, **changes):
        current = fixture or self.fixture
        kwargs = {**current.command_kwargs, **changes}
        with fake_runtime_profile():
            return compile_body_sway_amplitude_envelope_command(
                *current.command_args, **kwargs
            )

    def test_command_is_deterministic_zero_write_and_path_free(self):
        before = tree(self.root)
        first = self.compile()
        second = self.compile()
        self.assertEqual(before, tree(self.root))
        self.assertEqual(first.amplitude_envelope_sha256,
                         second.amplitude_envelope_sha256)
        self.assertEqual(first.document, second.document)
        self.assertEqual(8, len(first.input_paths))
        self.assertNotIn("path", _recursive_keys(first.document))
        self.assertEqual(
            first.review_admission_sha256,
            first.document["source"]["review_admission_sha256"],
        )
        report = first.document["source"]["reviewed_probe_report"]
        self.assertEqual(
            first.document["source"]["review_admission"]["source"][
                "p10_chain"
            ]["body_sway_probe_report_sha256"],
            _sha(report),
        )

    def test_head_change_during_analysis_fails_closed_without_extra_writes(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = P10ReviewAdmissionFixture(Path(temporary))
            real_compile = compile_body_sway_amplitude_envelope_candidate

            def compile_then_advance(inputs):
                value = real_compile(inputs)
                fixture.append("reject")
                return value

            with patch(
                "autospine_workbench.p10_amplitude_envelope_commands."
                "compile_body_sway_amplitude_envelope_candidate",
                side_effect=compile_then_advance,
            ), self.assertRaises(P10AmplitudeEnvelopeCommandError):
                self.compile(fixture)
            with fake_runtime_profile():
                self.assertEqual(2, fixture.application.prepare(
                    fixture.address
                ).history.current_revision)

    def test_head_change_during_final_recheck_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = P10ReviewAdmissionFixture(Path(temporary))
            service = fixture.application
            real_exact = service.exact_decision

            def exact_then_advance(*args, **kwargs):
                value = real_exact(*args, **kwargs)
                fixture.append("reject")
                return value

            with patch(
                "autospine_workbench.p10_amplitude_envelope_commands."
                "BodySwayVisualReviewApplication",
                return_value=service,
            ), patch.object(
                service, "exact_decision", side_effect=exact_then_advance
            ), self.assertRaises(P10AmplitudeEnvelopeCommandError):
                self.compile(fixture)

    def test_old_or_crosswired_addresses_fail_closed(self):
        cases = {
            "p3_rig_sha256": self.fixture.command_kwargs["p3_bundle_sha256"],
            "temporary_preview_sha256": "a" * 64,
            "visual_candidate_sha256": "b" * 64,
            "visual_revision": 2,
            "visual_decision_sha256": "c" * 64,
        }
        for field, value in cases.items():
            before = tree(self.root)
            with self.subTest(field=field), self.assertRaises(
                P10AmplitudeEnvelopeCommandError
            ):
                self.compile(**{field: value})
            self.assertEqual(before, tree(self.root))

    def test_command_source_has_no_discovery_or_mutation_boundary(self):
        source = (
            SRC / "autospine_workbench" /
            "p10_amplitude_envelope_commands.py"
        ).read_text(encoding="utf-8")
        for forbidden in (".glob(", ".rglob(", "publish_", "write_"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, source)


def _recursive_keys(value) -> set[str]:
    if type(value) is dict:
        return set(value).union(*(
            _recursive_keys(item) for item in value.values()
        ))
    if type(value) is list:
        return set().union(*(_recursive_keys(item) for item in value))
    return set()


def _sha(value) -> str:
    import hashlib
    import json

    raw = json.dumps(
        value, ensure_ascii=False, allow_nan=False,
        sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


if __name__ == "__main__":
    unittest.main()
