"""P10.7b v2 captured-unreviewed evidence and bundle tests."""

from __future__ import annotations

from dataclasses import asdict, replace
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
for item in (ROOT, ROOT / "src"):
    if str(item) not in sys.path:
        sys.path.insert(0, str(item))

from autospine_workbench.browser_executable_snapshot import (  # noqa: E402
    BrowserExecutableSnapshot,
)
from autospine_workbench.browser_version_identity import (  # noqa: E402
    browser_version_identity_sha256,
)
from autospine_workbench.spine42_v3_runtime_bundle_v2 import (  # noqa: E402
    BUNDLE_ADDRESS_DOMAIN, NAMESPACE, Spine42V3RuntimeBundleV2Error,
    build_spine42_v3_runtime_bundle_v2,
    replay_spine42_v3_runtime_bundle_v2,
    spine42_v3_runtime_bundle_sha256_v2,
)
from autospine_workbench.spine42_v3_runtime_evidence_v2 import (  # noqa: E402
    AUTHORITY, FIXED_NAMES, MANIFEST_NAME, RELEASE_GATE,
    Spine42V3RuntimeEvidenceV2Error, build_spine42_v3_runtime_evidence_v2,
    replay_spine42_v3_runtime_evidence_v2,
)
from autospine_workbench.spine42_v3_runtime_runner_v2 import (  # noqa: E402
    Spine42V3RuntimeRunV2,
)
from tests.spine42_v3_runtime_issued_run_v2_helpers import (  # noqa: E402
    issued_runtime_run_v2,
)
from tests.test_spine42_v3_runtime_capture_harness import _png  # noqa: E402
from tests.test_spine42_v3_runtime_capture_harness_v2 import (  # noqa: E402
    V2HarnessFixture, _fake_runtime_profile_v2,
)


class Spine42V3RuntimeEvidenceV2Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        cls.fixture = V2HarnessFixture(Path(cls.temporary.name) / "fixture")
        runtime = replace(
            cls.fixture.runtime,
            package_json_sha256="a" * 64, license_sha256="b" * 64,
        )
        version = "128.0.6613.0"
        browser = BrowserExecutableSnapshot(
            str(Path(cls.temporary.name) / "chrome.exe"), "chromium", version,
            browser_version_identity_sha256("chromium", version),
            "c" * 64, 4096,
        )
        png = _png()
        with _fake_runtime_profile_v2():
            cls.captured_run = issued_runtime_run_v2(
                cls.fixture, runtime, browser, png,
            )
        with _fake_runtime_profile_v2():
            cls.evidence = build_spine42_v3_runtime_evidence_v2(
                cls.captured_run
            )

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def test_deterministic_path_free_captured_unreviewed_contract(self):
        with _fake_runtime_profile_v2():
            second = build_spine42_v3_runtime_evidence_v2(self.captured_run)
        self.assertEqual(self.evidence.file_items, second.file_items)
        self.assertEqual(self.evidence.evidence_sha256, second.evidence_sha256)
        manifest = self.evidence.manifest
        self.assertEqual("captured_unreviewed", manifest["status"])
        self.assertEqual(dict(AUTHORITY), manifest["authority"])
        self.assertEqual(
            {"status": RELEASE_GATE["status"],
             "reason_codes": list(RELEASE_GATE["reason_codes"])},
            manifest["release_gate"],
        )
        self.assertFalse(AUTHORITY["raster_metrics_computed"])
        self.assertNotIn("metrics.json", dict(self.evidence.file_items))
        serialized = repr(asdict(self.evidence)) + json.dumps(manifest)
        self.assertNotIn(str(Path(self.temporary.name)), serialized)

    def test_bundle_has_independent_namespace_domain_and_framing(self):
        with _fake_runtime_profile_v2():
            bundle = build_spine42_v3_runtime_bundle_v2(self.evidence)
        self.assertEqual("spine42-v3-runtime-v2", NAMESPACE)
        self.assertEqual(
            b"autospine.spine42-v3-runtime-bundle/v2\x00",
            BUNDLE_ADDRESS_DOMAIN,
        )
        self.assertEqual(
            bundle.bundle_sha256,
            spine42_v3_runtime_bundle_sha256_v2(bundle.file_items),
        )
        self.assertNotEqual(bundle.bundle_sha256, bundle.evidence_sha256)

    def test_forged_and_replaced_runs_are_rejected(self):
        forged = object.__new__(Spine42V3RuntimeRunV2)
        with self.assertRaises(Spine42V3RuntimeEvidenceV2Error):
            build_spine42_v3_runtime_evidence_v2(forged)
        changed = replace(
            self.captured_run,
            artifact_count=self.captured_run.artifact_count + 1,
        )
        with self.assertRaises(Spine42V3RuntimeEvidenceV2Error):
            build_spine42_v3_runtime_evidence_v2(changed)

    def test_extra_wrong_order_wrong_case_and_payload_tamper_fail(self):
        items = self.evidence.file_items
        mutations = (
            items + (("captures/extra.png", items[-1][1]),),
            (items[1], items[0], *items[2:]),
            ((MANIFEST_NAME.upper(), items[0][1]), *items[1:]),
            (*items[:-1], (items[-1][0], items[-1][1] + b"x")),
        )
        for mutation in mutations:
            with self.subTest(name=mutation[0][0]), \
                    _fake_runtime_profile_v2(), self.assertRaises(
                        Spine42V3RuntimeEvidenceV2Error
                    ):
                replay_spine42_v3_runtime_evidence_v2(
                    self.fixture.bundle, tuple(mutation),
                )

    def test_publicly_constructed_evidence_cannot_form_bundle(self):
        forged = replace(self.evidence)
        with self.assertRaises(Spine42V3RuntimeBundleV2Error):
            build_spine42_v3_runtime_bundle_v2(forged)

    def test_detached_replay_does_not_mint_live_evidence(self):
        with _fake_runtime_profile_v2():
            replayed = replay_spine42_v3_runtime_evidence_v2(
                self.fixture.bundle, self.evidence.file_items,
            )
            detached = replay_spine42_v3_runtime_bundle_v2(
                self.fixture.bundle, self.evidence.file_items,
            )
        self.assertEqual(self.evidence.evidence_sha256,
                         replayed.evidence_sha256)
        self.assertEqual(detached.evidence_sha256, replayed.evidence_sha256)
        with self.assertRaises(Spine42V3RuntimeBundleV2Error):
            build_spine42_v3_runtime_bundle_v2(replayed)

    def test_exported_authority_and_gate_cannot_change_new_manifests(self):
        with self.assertRaises(TypeError):
            AUTHORITY["release_authority"] = True
        with self.assertRaises(TypeError):
            RELEASE_GATE["status"] = "passed"
        with _fake_runtime_profile_v2():
            replayed = replay_spine42_v3_runtime_evidence_v2(
                self.fixture.bundle, self.evidence.file_items,
            )
        self.assertFalse(replayed.manifest["authority"]["release_authority"])
        self.assertEqual("blocked", replayed.manifest["release_gate"]["status"])
        items = list(self.evidence.file_items)
        manifest = json.loads(items[0][1])
        manifest["authority"]["release_authority"] = True
        manifest["release_gate"] = {"status": "passed", "reason_codes": []}
        items[0] = (MANIFEST_NAME, _canonical(manifest))
        with _fake_runtime_profile_v2(), self.assertRaises(
            Spine42V3RuntimeEvidenceV2Error
        ):
            replay_spine42_v3_runtime_evidence_v2(
                self.fixture.bundle, tuple(items),
            )

    def test_truncated_png_with_recomputed_digests_is_rejected(self):
        items = list(self.evidence.file_items)
        capture_index = len(items) - 1
        capture_name, raw = items[capture_index]
        truncated = raw[:24]
        items[capture_index] = (capture_name, truncated)
        files = dict(items)
        reports = json.loads(files[FIXED_NAMES[4]])
        reports[-1]["image"]["png_sha256"] = hashlib.sha256(
            truncated
        ).hexdigest()
        reports[-1]["image"]["size_bytes"] = len(truncated)
        report_bytes = _canonical(reports)
        items[4] = (FIXED_NAMES[4], report_bytes)
        manifest = json.loads(items[0][1])
        manifest["artifacts"][-1]["sha256"] = hashlib.sha256(
            truncated
        ).hexdigest()
        manifest["artifacts"][-1]["size_bytes"] = len(truncated)
        report_document = next(
            row for row in manifest["documents"]
            if row["name"] == FIXED_NAMES[4]
        )
        report_document["sha256"] = hashlib.sha256(report_bytes).hexdigest()
        report_document["size_bytes"] = len(report_bytes)
        manifest["source"]["runtime_reports_sha256"] = hashlib.sha256(
            report_bytes
        ).hexdigest()
        items[0] = (MANIFEST_NAME, _canonical(manifest))
        with _fake_runtime_profile_v2(), self.assertRaisesRegex(
            Spine42V3RuntimeEvidenceV2Error,
            "Capture PNG cannot be decoded exactly",
        ):
            replay_spine42_v3_runtime_evidence_v2(
                self.fixture.bundle, tuple(items),
            )

    def test_issued_evidence_mutation_cannot_cross_wire_bundle(self):
        mutations = (
            ("project_id", "evil"),
            ("spine42_v3_bundle_sha256", "d" * 64),
            ("evidence_sha256", "e" * 64),
            ("_file_items", self.evidence.file_items[:-1]),
        )
        for field, value in mutations:
            with self.subTest(field=field), _fake_runtime_profile_v2():
                evidence = build_spine42_v3_runtime_evidence_v2(
                    self.captured_run
                )
            object.__setattr__(evidence, field, value)
            with self.assertRaises(Spine42V3RuntimeBundleV2Error):
                build_spine42_v3_runtime_bundle_v2(evidence)

    def test_public_bundle_has_strict_fixed_and_capture_inventory(self):
        items = self.evidence.file_items
        invalid = (
            items[1:],
            (*items[:5], ("../unsafe.png", b"x")),
            (*items[:5], ("captures/X.PNG", b"x")),
            (*items[:5], ("captures/large.png", b"x" * (4 * 1024 * 1024 + 1))),
        )
        for candidate in invalid:
            with self.subTest(name=candidate[-1][0]), self.assertRaises(
                Spine42V3RuntimeBundleV2Error
            ):
                spine42_v3_runtime_bundle_sha256_v2(tuple(candidate))
        over_count = self.evidence.file_items[:5] + tuple(
            (f"captures/extra-{index}.png", b"x")
            for index in range(1871)
        )
        with self.assertRaises(Spine42V3RuntimeBundleV2Error):
            spine42_v3_runtime_bundle_sha256_v2(over_count)

    def test_oversized_fixed_document_is_rejected_before_json_parse(self):
        items = list(self.evidence.file_items)
        items[4] = (FIXED_NAMES[4], b"x" * (32 * 1024 * 1024 + 1))
        with self.assertRaisesRegex(
            Spine42V3RuntimeEvidenceV2Error, "inventory"
        ):
            replay_spine42_v3_runtime_evidence_v2(
                self.fixture.bundle, tuple(items),
            )

    def test_manifest_schema_when_jsonschema_is_available(self):
        try:
            import jsonschema
        except ImportError:
            self.skipTest("jsonschema is optional")
        schema = json.loads((
            ROOT / "schemas" /
            "spine42-v3-runtime-capture-manifest-v2.schema.json"
        ).read_text(encoding="utf-8"))
        jsonschema.Draft202012Validator(schema).validate(
            self.evidence.manifest
        )
        changed = json.loads(json.dumps(self.evidence.manifest))
        changed["authority"]["raster_visual_quality_approved"] = True
        with self.assertRaises(jsonschema.ValidationError):
            jsonschema.Draft202012Validator(schema).validate(changed)

    def test_session_and_report_schemas_are_strict_when_available(self):
        try:
            import jsonschema
        except ImportError:
            self.skipTest("jsonschema is optional")
        schema_root = ROOT / "schemas"
        store = {}
        for path in schema_root.glob("spine42-v3-runtime-*-v2.schema.json"):
            loaded = json.loads(path.read_text(encoding="utf-8"))
            store[loaded["$id"]] = loaded
        files = dict(self.evidence.file_items)
        for schema_name, document_name in (
            ("spine42-v3-runtime-session-set-v2.schema.json", FIXED_NAMES[3]),
            ("spine42-v3-runtime-reports-v2.schema.json", FIXED_NAMES[4]),
        ):
            schema = json.loads(
                (schema_root / schema_name).read_text(encoding="utf-8")
            )
            resolver = jsonschema.RefResolver.from_schema(
                schema, store=store,
            )
            validator = jsonschema.Draft202012Validator(
                schema, resolver=resolver,
            )
            document = json.loads(files[document_name])
            changed = json.loads(json.dumps(document))
            target = changed[0] if type(changed) is list else changed
            target["unexpected"] = True
            self.assertTrue(any(
                error.validator == "additionalProperties"
                for error in validator.iter_errors(changed)
            ))


if __name__ == "__main__":
    unittest.main()


def _canonical(value):
    return json.dumps(
        value, ensure_ascii=False, allow_nan=False, sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
