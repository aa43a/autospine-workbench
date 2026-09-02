"""P10.5d v2 source-closure isolation and cross-binding tests."""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for item in (ROOT, SRC):
    if str(item) not in sys.path:
        sys.path.insert(0, str(item))

try:
    from jsonschema import Draft202012Validator
    from referencing import Registry, Resource
except ImportError:  # pragma: no cover - optional dependency
    Draft202012Validator = None
    Registry = Resource = None

from autospine_workbench.body_sway_continuous_proof_validation_v2 import (  # noqa: E402
    BodySwayContinuousProofValidationV2Error,
)
from autospine_workbench.body_sway_dynamic_seam_profile_v2 import (  # noqa: E402
    FORMAT,
    FORMAT_VERSION,
    SOURCE_FIELDS,
    SOURCE_HASH_DOMAIN,
    body_sway_dynamic_seam_source_sha256_v2,
)
from autospine_workbench.body_sway_dynamic_seam_source import (  # noqa: E402
    BodySwayDynamicSeamSourceError,
    build_body_sway_dynamic_seam_source,
    require_body_sway_dynamic_seam_source,
)
from autospine_workbench.body_sway_dynamic_seam_source_v2 import (  # noqa: E402
    BodySwayDynamicSeamSourceV2Error,
    build_body_sway_dynamic_seam_source_v2,
)
from autospine_workbench.body_sway_dynamic_seam_validation_v2 import (  # noqa: E402
    BodySwayDynamicSeamSourceV2ValidationError,
    body_sway_dynamic_seam_source_canonical_bytes_v2,
    body_sway_dynamic_seam_source_document_sha256_v2,
    require_body_sway_dynamic_seam_source_v2,
)
from autospine_workbench.resolved_project import canonical_sha256  # noqa: E402
from tests.body_sway_dynamic_seam_source_helpers import (  # noqa: E402
    dynamic_seam_values,
)


V2_PROOF_READER = (
    "autospine_workbench.body_sway_dynamic_seam_source_v2."
    "body_sway_continuous_preview_proof_sha256_v2"
)
V1_PROOF_READER = (
    "autospine_workbench.body_sway_dynamic_seam_source."
    "body_sway_continuous_proof_sha256"
)


def _fake_proof_sha(document):
    return canonical_sha256(document)


def _values():
    _old_proof, candidate, decision, reviewed_set, contract = (
        dynamic_seam_values()
    )
    rig = deepcopy(_old_proof["source"]["rig_ir"])
    p3 = deepcopy(
        _old_proof["source"]["amplitude_envelope_candidate"]["source"]
        ["reviewed_probe_report"]["source"]["p3"]
    )
    proof = {
        "format": "autospine-body-sway-continuous-preview-proof",
        "format_version": 2,
        "project_id": candidate["project_id"],
        "clip_id": "idle",
        "source": {
            "rig_ir_sha256": canonical_sha256(rig),
            "rig_ir": rig,
            "amplitude_envelope_candidate_v2": {
                "source": {
                    "reviewed_probe_report": {"source": {"p3": p3}}
                }
            },
        },
    }
    return {
        "continuous_proof_v2": proof,
        "seam_anchor_candidates_v1": candidate,
        "seam_anchor_review_decision_v1": decision,
        "reviewed_seam_anchor_set_v1": reviewed_set,
        "reviewed_set_v1_bundle_sha256": contract.bundle_sha256,
    }


class BodySwayDynamicSeamSourceV2Tests(unittest.TestCase):
    def _build(self):
        values = _values()
        with patch(V2_PROOF_READER, side_effect=_fake_proof_sha) as reader:
            source = build_body_sway_dynamic_seam_source_v2(**values)
        reader.assert_called_once_with(values["continuous_proof_v2"])
        return values, source

    def test_exact_mixed_version_source_is_deterministic_and_path_free(self):
        values, first = self._build()
        with patch(V2_PROOF_READER, side_effect=_fake_proof_sha):
            second = build_body_sway_dynamic_seam_source_v2(**values)
            replayed = require_body_sway_dynamic_seam_source_v2(first)
            canonical = body_sway_dynamic_seam_source_canonical_bytes_v2(first)
            digest = body_sway_dynamic_seam_source_document_sha256_v2(first)
        self.assertEqual(first, second)
        self.assertEqual(first, replayed)
        self.assertEqual(SOURCE_FIELDS, set(first))
        self.assertEqual(FORMAT, first["format"])
        self.assertEqual(FORMAT_VERSION, first["format_version"])
        self.assertEqual(
            first["source_set_sha256"],
            body_sway_dynamic_seam_source_sha256_v2(first),
        )
        self.assertEqual(hashlib.sha256(canonical).hexdigest(), digest)
        self.assertIn("/v2", SOURCE_HASH_DOMAIN)
        self.assertFalse(any(
            token in key for key in first
            for token in ("run_id", "job_id", "path", "latest")
        ))

    def test_explicit_project_manifest_p3_rig_and_bundle_are_bound(self):
        _values_raw, source = self._build()
        proof = source["body_sway_continuous_preview_proof_v2"]
        p3 = proof["source"]["amplitude_envelope_candidate_v2"]["source"] \
            ["reviewed_probe_report"]["source"]["p3"]
        self.assertEqual(proof["project_id"], source["project_id"])
        self.assertEqual(proof["clip_id"], source["clip_id"])
        self.assertEqual(p3["layer_manifest_sha256"], source[
            "layer_manifest_sha256"
        ])
        self.assertEqual(p3["rig_sha256"], source["p3_rig_sha256"])
        self.assertEqual(p3["bundle_sha256"], source["p3_bundle_sha256"])
        self.assertEqual(proof["source"]["rig_ir_sha256"], source[
            "p3_rig_sha256"
        ])

    def test_full_v2_proof_reader_is_mandatory_and_failure_is_closed(self):
        values = _values()
        failure = BodySwayContinuousProofValidationV2Error("forged v2 proof")
        with patch(V2_PROOF_READER, side_effect=failure) as reader, \
                self.assertRaisesRegex(
                    BodySwayDynamicSeamSourceV2Error, "forged v2 proof"
                ):
            build_body_sway_dynamic_seam_source_v2(**values)
        reader.assert_called_once_with(values["continuous_proof_v2"])

    def test_project_manifest_p3_rig_and_review_crosswires_fail(self):
        attacks = []
        project = _values()
        project["continuous_proof_v2"]["project_id"] = "cross-project"
        attacks.append(project)
        manifest = _values()
        _p3(manifest)["layer_manifest_sha256"] = "a" * 64
        attacks.append(manifest)
        p3_rig = _values()
        _p3(p3_rig)["rig_sha256"] = "b" * 64
        attacks.append(p3_rig)
        rig = _values()
        rig["continuous_proof_v2"]["source"]["rig_ir_sha256"] = "c" * 64
        attacks.append(rig)
        reviewed = _values()
        reviewed["reviewed_seam_anchor_set_v1"]["source"][
            "review_revision"
        ] += 1
        attacks.append(reviewed)
        for index, values in enumerate(attacks):
            with self.subTest(attack=index), patch(
                V2_PROOF_READER, side_effect=_fake_proof_sha
            ), self.assertRaises(BodySwayDynamicSeamSourceV2Error):
                build_body_sway_dynamic_seam_source_v2(**values)

    def test_v1_and_v2_consumers_reject_each_others_source_contract(self):
        values, source_v2 = self._build()
        with self.assertRaises(BodySwayDynamicSeamSourceError):
            require_body_sway_dynamic_seam_source(source_v2)
        old_proof, candidate, decision, reviewed_set, contract = (
            dynamic_seam_values()
        )
        with patch(V1_PROOF_READER, side_effect=_fake_proof_sha):
            source_v1 = build_body_sway_dynamic_seam_source(
                continuous_proof=old_proof,
                seam_anchor_candidates=candidate,
                seam_anchor_review_decision=decision,
                reviewed_seam_anchor_set=reviewed_set,
                reviewed_set_bundle_sha256=contract.bundle_sha256,
            )
        with self.assertRaises(BodySwayDynamicSeamSourceV2ValidationError):
            require_body_sway_dynamic_seam_source_v2(source_v1)
        v1_proof = deepcopy(values)
        v1_proof["continuous_proof_v2"]["format_version"] = 1
        with self.assertRaises(BodySwayDynamicSeamSourceV2Error):
            build_body_sway_dynamic_seam_source_v2(**v1_proof)

    def test_outer_reseal_extra_execution_identity_and_wrong_bundle_fail(self):
        _values_raw, source = self._build()
        attacks = []
        identity = deepcopy(source)
        identity["p3_bundle_sha256"] = "d" * 64
        identity["source_set_sha256"] = (
            body_sway_dynamic_seam_source_sha256_v2(identity)
        )
        attacks.append(identity)
        execution = deepcopy(source)
        execution["run_id"] = "execution-only"
        execution["source_set_sha256"] = (
            body_sway_dynamic_seam_source_sha256_v2(execution)
        )
        attacks.append(execution)
        for attack in attacks:
            with patch(V2_PROOF_READER, side_effect=_fake_proof_sha), \
                    self.assertRaises(
                        BodySwayDynamicSeamSourceV2ValidationError
                    ):
                require_body_sway_dynamic_seam_source_v2(attack)
        wrong_bundle = _values()
        wrong_bundle["reviewed_set_v1_bundle_sha256"] = "e" * 64
        with patch(V2_PROOF_READER, side_effect=_fake_proof_sha), \
                self.assertRaisesRegex(
                    BodySwayDynamicSeamSourceV2Error, "bundle differs"
                ):
            build_body_sway_dynamic_seam_source_v2(**wrong_bundle)

    @unittest.skipIf(Draft202012Validator is None, "jsonschema is optional")
    def test_source_schema_is_strict_versioned_and_excludes_run_identity(self):
        schema = json.loads((
            ROOT / "schemas" /
            "body-sway-dynamic-seam-source-v2.schema.json"
        ).read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        resources = []
        for name in (
            "body-sway-continuous-preview-proof-v2.schema.json",
            "seam-anchor-candidates-v1.schema.json",
            "seam-anchor-review-decision-v1.schema.json",
            "reviewed-seam-anchor-set-v1.schema.json",
        ):
            uri = f"https://autospine.local/schemas/{name}"
            resources.append((uri, Resource.from_contents({
                "$schema": "https://json-schema.org/draft/2020-12/schema",
                "$id": uri,
            })))
        validator = Draft202012Validator(
            schema, registry=Registry().with_resources(resources)
        )
        _values_raw, source = self._build()
        validator.validate(source)
        version = deepcopy(source)
        version["format_version"] = 1
        self.assertFalse(validator.is_valid(version))
        run = deepcopy(source)
        run["run_id"] = "not-canonical"
        self.assertFalse(validator.is_valid(run))


def _p3(values):
    return values["continuous_proof_v2"]["source"] \
        ["amplitude_envelope_candidate_v2"]["source"] \
        ["reviewed_probe_report"]["source"]["p3"]


if __name__ == "__main__":
    unittest.main()
