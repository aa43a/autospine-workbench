"""Current-head observation tests for the P10.5d exact source."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import FrozenInstanceError
from pathlib import Path
import tempfile
from unittest.mock import patch
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for item in (ROOT, SRC):
    if str(item) not in sys.path:
        sys.path.insert(0, str(item))

from autospine_workbench.body_sway_dynamic_seam_head_checks import (  # noqa: E402
    BodySwayDynamicSeamHeadCheckError,
    extract_body_sway_dynamic_seam_head_identity,
    require_current_body_sway_dynamic_seam_heads,
)
from autospine_workbench.body_sway_dynamic_seam_source import (  # noqa: E402
    BodySwayDynamicSeamSourceError,
    build_body_sway_dynamic_seam_source,
)
from autospine_workbench.reviewed_seam_anchor_set_inputs import (  # noqa: E402
    PreparedReviewedSeamAnchorSet,
    ReviewedSeamAnchorSetInputsError,
)
from autospine_workbench.seam_anchor_review_json import (  # noqa: E402
    canonical_json_bytes,
)
from tests.body_sway_dynamic_seam_source_helpers import build_kwargs  # noqa: E402


MODULE = "autospine_workbench.body_sway_dynamic_seam_head_checks"
SOURCE_VALIDATOR = f"{MODULE}.require_body_sway_dynamic_seam_source"
VISUAL_HELPER = f"{MODULE}.require_unchanged_visual_review_head"
SEAM_HELPER = f"{MODULE}.prepare_current_head_reviewed_seam_anchor_set"
SHAS = tuple(character * 64 for character in "abcdef")


def exact_source():
    values = build_kwargs()
    proof = values["continuous_proof"]
    proof["source"]["amplitude_envelope_candidate"]["source"][
        "review_admission"
    ] = {
        "project_id": proof["project_id"],
        "source": {
            "capture": {
                "project_id": proof["project_id"],
                "temporary_preview_sha256": SHAS[0],
                "runtime_capture_bundle_sha256": SHAS[1],
                "capture_artifact_set_sha256": SHAS[2],
            },
            "visual_review": {
                "candidate_sha256": SHAS[3],
                "revision": 3,
                "decision_sha256": SHAS[4],
                "head_decision_sha256": SHAS[4],
            },
        },
    }
    proof_hash = (
        "autospine_workbench.body_sway_dynamic_seam_source."
        "body_sway_continuous_proof_sha256"
    )
    with patch(proof_hash, return_value=SHAS[5]):
        return build_body_sway_dynamic_seam_source(**values)


def admitted(value):
    return deepcopy(value)


def prepared(source, *, sha=None, document=None):
    reviewed = source["reviewed_seam_anchor_set"] \
        if document is None else document
    return PreparedReviewedSeamAnchorSet(
        None,  # type: ignore[arg-type]
        source["reviewed_seam_anchor_set_sha256"] if sha is None else sha,
        canonical_json_bytes(reviewed).decode("utf-8"),
    )


class BodySwayDynamicSeamHeadCheckTests(unittest.TestCase):
    def test_extracts_frozen_visual_and_seam_exact_identities(self):
        source = exact_source()
        with patch(SOURCE_VALIDATOR, side_effect=admitted) as validator:
            identity = extract_body_sway_dynamic_seam_head_identity(source)
        validator.assert_called_once_with(source)
        admission = source["body_sway_continuous_preview_proof"]["source"] \
            ["amplitude_envelope_candidate"]["source"]["review_admission"]
        visual = admission["source"]["visual_review"]
        seam = source["reviewed_seam_anchor_set"]["source"]
        self.assertEqual(
            admission["source"]["capture"]["temporary_preview_sha256"],
            identity.visual_address.temporary_preview_sha256,
        )
        self.assertEqual(visual["candidate_sha256"],
                         identity.visual_candidate_sha256)
        self.assertEqual(seam["p3_rig_sha256"],
                         identity.seam_address.p3_rig_sha256)
        self.assertEqual(seam["review_revision"], identity.seam_revision)
        with self.assertRaises(FrozenInstanceError):
            identity.project_id = "mutated"  # type: ignore[misc]

    def test_calls_both_upstream_double_checks_with_exact_arguments(self):
        source = exact_source()
        expected = prepared(source)
        with tempfile.TemporaryDirectory() as root, \
                patch(SOURCE_VALIDATOR, side_effect=admitted), \
                patch(VISUAL_HELPER) as visual, \
                patch(SEAM_HELPER, return_value=expected) as seam:
            result = require_current_body_sway_dynamic_seam_heads(
                Path(root), source
            )
            state = Path(root)
        identity = result.identity
        visual.assert_called_once_with(
            state, *identity.visual_address.reader_arguments,
            identity.visual_candidate_sha256, identity.visual_revision,
            identity.visual_decision_sha256,
        )
        seam.assert_called_once_with(
            state, identity.seam_address,
            candidate_sha256=identity.seam_candidate_sha256,
            revision=identity.seam_revision,
            decision_sha256=identity.seam_decision_sha256,
        )
        self.assertEqual("compile_time", result.document["scope"])
        self.assertFalse(result.document["permanent_authority_claimed"])
        copied = result.document
        copied["scope"] = "permanent"
        self.assertEqual("compile_time", result.document["scope"])
        with self.assertRaises(FrozenInstanceError):
            result._canonical_json = "{}"  # type: ignore[misc]

    def test_compiled_set_sha_and_canonical_bytes_must_both_match(self):
        source = exact_source()
        different = deepcopy(source["reviewed_seam_anchor_set"])
        different["summary"]["anchor_pair_count"] += 1
        attacks = (
            prepared(source, sha="0" * 64),
            prepared(source, document=different),
            object(),
        )
        for result in attacks:
            with self.subTest(result=type(result).__name__), \
                    patch(SOURCE_VALIDATOR, side_effect=admitted), \
                    patch(VISUAL_HELPER), \
                    patch(SEAM_HELPER, return_value=result), \
                    self.assertRaisesRegex(
                        BodySwayDynamicSeamHeadCheckError,
                        "different reviewed anchor set",
                    ):
                require_current_body_sway_dynamic_seam_heads(Path("state"), source)

    def test_head_change_and_source_validation_fail_closed(self):
        source = exact_source()
        head_failures = (
            (VISUAL_HELPER, RuntimeError("visual head changed")),
            (SEAM_HELPER, ReviewedSeamAnchorSetInputsError(
                "seam head changed"
            )),
        )
        for target, failure in head_failures:
            with self.subTest(target=target), \
                    patch(SOURCE_VALIDATOR, side_effect=admitted), \
                    patch(VISUAL_HELPER), \
                    patch(SEAM_HELPER, return_value=prepared(source)), \
                    patch(target, side_effect=failure), \
                    self.assertRaises(BodySwayDynamicSeamHeadCheckError):
                require_current_body_sway_dynamic_seam_heads(Path("state"), source)
        with patch(
            SOURCE_VALIDATOR,
            side_effect=BodySwayDynamicSeamSourceError("source replay failed"),
        ), patch(VISUAL_HELPER) as visual, patch(SEAM_HELPER) as seam, \
                self.assertRaisesRegex(
                    BodySwayDynamicSeamHeadCheckError, "source replay failed"
                ):
            require_current_body_sway_dynamic_seam_heads(Path("state"), source)
        visual.assert_not_called()
        seam.assert_not_called()

    def test_crosswired_embedded_visual_identity_is_rejected(self):
        source = exact_source()
        admission = source["body_sway_continuous_preview_proof"]["source"] \
            ["amplitude_envelope_candidate"]["source"]["review_admission"]
        admission["source"]["capture"]["project_id"] = "cross-project"
        with patch(SOURCE_VALIDATOR, side_effect=admitted), \
                patch(VISUAL_HELPER) as visual, patch(SEAM_HELPER) as seam, \
                self.assertRaisesRegex(
                    BodySwayDynamicSeamHeadCheckError, "cross-wired"
                ):
            require_current_body_sway_dynamic_seam_heads(Path("state"), source)
        visual.assert_not_called()
        seam.assert_not_called()

    def test_observation_layer_performs_no_writes(self):
        source = exact_source()
        with patch(SOURCE_VALIDATOR, side_effect=admitted), \
                patch(VISUAL_HELPER), \
                patch(SEAM_HELPER, return_value=prepared(source)), \
                patch("builtins.open", side_effect=AssertionError("write")):
            observation = require_current_body_sway_dynamic_seam_heads(
                Path("state"), source
            )
        self.assertEqual(
            "canonical_replay_matched",
            observation.document["checks"]["reviewed_seam_anchor_set"],
        )
        self.assertNotIn("state_root", observation.document)
        self.assertNotIn("path", str(observation.document).lower())


if __name__ == "__main__":
    unittest.main()
