"""Strict contract tests for explicit P10.7b readiness requests."""

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for item in (ROOT, SRC):
    if str(item) not in sys.path:
        sys.path.insert(0, str(item))

from autospine_workbench.seam_anchor_review_json import (  # noqa: E402
    canonical_json_bytes,
)
from autospine_workbench.spine42_v3_raster_review import (  # noqa: E402
    require_spine42_v3_raster_review_decision,
)
from autospine_workbench.spine42_v3_raster_review_values import (  # noqa: E402
    domain_sha256,
)
from autospine_workbench.spine42_v3_readiness_manifest import (  # noqa: E402
    MAX_SAMPLES,
    REQUEST_FORMAT,
    REQUEST_FORMAT_VERSION,
    REQUEST_HASH_DOMAIN,
    Spine42V3ReadinessManifestError,
    canonical_spine42_v3_readiness_request_bytes,
    parse_spine42_v3_readiness_request,
    require_spine42_v3_readiness_request,
    spine42_v3_readiness_request_sha256,
)
from tests.test_spine42_v3_raster_review import (  # noqa: E402
    _candidate,
    _decision,
)


SHA = {
    name: str(index) * 64 for index, name in enumerate((
        "manifest", "rig", "p3", "motion", "motion-bundle", "seam",
        "seam-bundle", "v3", "v3-bundle",
    ), start=1)
}
DECISION_DOMAIN = "autospine-spine42-v3-raster-review-decision/v1"


def sample(project_id="project-a"):
    return {
        "project_id": project_id,
        "layer_manifest_sha256": SHA["manifest"],
        "p3_rig_sha256": SHA["rig"],
        "p3_bundle_sha256": SHA["p3"],
        "reviewed_motion_address": None,
        "reviewed_seam_anchor_set_address": None,
        "motion_instance_v3_address": None,
        "spine42_v3_address": None,
        "runtime_capture_address": None,
        "raster_review_decision": None,
    }


def request(*samples):
    return {
        "format": REQUEST_FORMAT,
        "format_version": REQUEST_FORMAT_VERSION,
        "samples": list(samples),
    }


def with_chain(row):
    row["reviewed_motion_address"] = {
        "motion_instance_v2_sha256": SHA["motion"],
        "bundle_sha256": SHA["motion-bundle"],
    }
    row["reviewed_seam_anchor_set_address"] = {
        "reviewed_seam_anchor_set_sha256": SHA["seam"],
        "bundle_sha256": SHA["seam-bundle"],
    }
    row["motion_instance_v3_address"] = {
        "motion_instance_v3_sha256": SHA["v3"],
        "bundle_sha256": SHA["v3-bundle"],
    }
    return row


def full_request():
    _evidence, candidate = _candidate()
    decision = _decision(candidate)
    row = with_chain(sample(candidate["project_id"]))
    source = decision["source"]
    row["spine42_v3_address"] = {
        "skeleton_json_sha256": source["skeleton_json_sha256"],
        "bundle_sha256": source["spine42_v3_bundle_sha256"],
    }
    row["runtime_capture_address"] = {
        "spine42_v3_bundle_sha256": source["spine42_v3_bundle_sha256"],
        "capture_bundle_sha256": source["runtime_capture_bundle_sha256"],
    }
    row["raster_review_decision"] = decision
    return request(row), candidate


def rehash(decision):
    decision.pop("decision_sha256", None)
    decision["decision_sha256"] = domain_sha256(DECISION_DOMAIN, decision)


class Spine42V3ReadinessManifestTests(unittest.TestCase):
    def test_canonical_parse_copy_and_domain_hash_are_deterministic(self):
        value = request(sample("project-a"), sample("project-b"))
        canonical = canonical_spine42_v3_readiness_request_bytes(value)
        parsed = parse_spine42_v3_readiness_request(canonical)
        self.assertEqual(value, parsed)
        self.assertIsNot(value, parsed)
        self.assertIsNot(value["samples"][0], parsed["samples"][0])
        first = spine42_v3_readiness_request_sha256(value)
        self.assertEqual(first, spine42_v3_readiness_request_sha256(parsed))
        expected = hashlib.sha256(canonical_json_bytes({
            "domain": REQUEST_HASH_DOMAIN, "request": parsed,
        })).hexdigest()
        self.assertEqual(expected, first)
        self.assertNotEqual(hashlib.sha256(canonical).hexdigest(), first)

    def test_parser_rejects_every_noncanonical_or_non_strict_encoding(self):
        value = request(sample())
        canonical = canonical_spine42_v3_readiness_request_bytes(value)
        variants = [
            canonical + b"\n",
            json.dumps(value, ensure_ascii=False, indent=2).encode("utf-8"),
            canonical.replace(b'"format_version":1', b'"format_version":NaN'),
            b'{"format":"' + REQUEST_FORMAT.encode() + b'","format":"' \
            + REQUEST_FORMAT.encode() + b'","format_version":1,"samples":[]}',
            bytearray(canonical),
        ]
        for bad in variants:
            with self.subTest(value=repr(bad)[:100]), self.assertRaises(
                Spine42V3ReadinessManifestError
            ):
                parse_spine42_v3_readiness_request(bad)

    def test_root_sample_count_order_identity_and_fields_are_exact(self):
        variants = []
        extra_root = request(sample())
        extra_root["extra"] = True
        variants.append(extra_root)
        wrong_version = request(sample())
        wrong_version["format_version"] = True
        variants.append(wrong_version)
        variants.extend((request(), request(*(
            sample(f"project-{index}") for index in range(MAX_SAMPLES + 1)
        ))))
        variants.extend((
            request(sample("project-b"), sample("project-a")),
            request(sample(), sample()),
            request({**sample(), "extra": None}),
            request({key: value for key, value in sample().items()
                     if key != "p3_bundle_sha256"}),
            request(sample("CON")),
        ))
        for bad in variants:
            with self.subTest(value=bad), self.assertRaises(
                Spine42V3ReadinessManifestError
            ):
                require_spine42_v3_readiness_request(bad)

    def test_all_sha_and_address_shapes_are_strict(self):
        complete, _candidate_value = full_request()
        row = complete["samples"][0]
        variants = []
        for field in ("layer_manifest_sha256", "p3_rig_sha256", "p3_bundle_sha256"):
            bad = deepcopy(complete)
            bad["samples"][0][field] = "A" * 64
            variants.append(bad)
        for field in (
            "reviewed_motion_address", "reviewed_seam_anchor_set_address",
            "motion_instance_v3_address", "spine42_v3_address",
            "runtime_capture_address",
        ):
            bad = deepcopy(complete)
            bad["samples"][0][field]["extra"] = "a" * 64
            variants.append(bad)
            bad = deepcopy(complete)
            key = next(iter(row[field]))
            bad["samples"][0][field][key] = "A" * 64
            variants.append(bad)
        for bad in variants:
            with self.subTest(value=bad), self.assertRaises(
                Spine42V3ReadinessManifestError
            ):
                require_spine42_v3_readiness_request(bad)

    def test_inverted_and_cross_wired_dependencies_fail_closed(self):
        base = sample()
        motion = {
            "motion_instance_v2_sha256": SHA["motion"],
            "bundle_sha256": SHA["motion-bundle"],
        }
        seam = {
            "reviewed_seam_anchor_set_sha256": SHA["seam"],
            "bundle_sha256": SHA["seam-bundle"],
        }
        instance = {
            "motion_instance_v3_sha256": SHA["v3"],
            "bundle_sha256": SHA["v3-bundle"],
        }
        variants = []
        for patch in (
            {"motion_instance_v3_address": instance},
            {"reviewed_motion_address": motion,
             "motion_instance_v3_address": instance},
            {"spine42_v3_address": {
                "skeleton_json_sha256": "a" * 64, "bundle_sha256": "b" * 64}},
            {"runtime_capture_address": {
                "spine42_v3_bundle_sha256": "b" * 64,
                "capture_bundle_sha256": "c" * 64}},
        ):
            variants.append(request({**deepcopy(base), **patch}))
        cross, _ = full_request()
        cross["samples"][0]["runtime_capture_address"][
            "spine42_v3_bundle_sha256"
        ] = "f" * 64
        variants.append(cross)
        for bad in variants:
            with self.subTest(value=bad), self.assertRaises(
                Spine42V3ReadinessManifestError
            ):
                require_spine42_v3_readiness_request(bad)

        seam_first = deepcopy(base)
        seam_first["reviewed_seam_anchor_set_address"] = seam
        self.assertEqual(
            seam,
            require_spine42_v3_readiness_request(
                request(seam_first)
            )["samples"][0]["reviewed_seam_anchor_set_address"],
        )

    def test_full_embedded_human_decision_is_accepted_and_bound(self):
        value, candidate = full_request()
        validated = require_spine42_v3_readiness_request(value)
        decision = validated["samples"][0]["raster_review_decision"]
        require_spine42_v3_raster_review_decision(
            decision, candidate=candidate
        )
        self.assertEqual("human", decision["review"]["method"])
        self.assertEqual("blocked", decision["release_gate"]["status"])

    def test_decision_shape_hash_human_gate_and_source_fail_closed(self):
        value, _candidate_value = full_request()
        variants = []
        corrupt = deepcopy(value)
        corrupt["samples"][0]["raster_review_decision"][
            "decision_sha256"
        ] = "0" * 64
        variants.append(corrupt)
        for mutate in (
            lambda row: row["review"].update(method="automatic"),
            lambda row: row["review"].update(
                revision=2, supersedes_decision_sha256="a" * 64),
            lambda row: row["authority"].update(release_authority=True),
            lambda row: row["source"].update(
                runtime_capture_bundle_sha256="f" * 64),
            lambda row: row["case_decisions"][0].update(
                action="reject", notes="bad raster"),
        ):
            bad = deepcopy(value)
            decision = bad["samples"][0]["raster_review_decision"]
            mutate(decision)
            rehash(decision)
            variants.append(bad)
        for bad in variants:
            with self.subTest(value=bad), self.assertRaises(
                Spine42V3ReadinessManifestError
            ):
                require_spine42_v3_readiness_request(bad)

    def test_production_module_stays_within_file_budget(self):
        path = SRC / "autospine_workbench" / "spine42_v3_readiness_manifest.py"
        self.assertLessEqual(len(path.read_text(encoding="utf-8").splitlines()), 300)


if __name__ == "__main__":
    unittest.main()
