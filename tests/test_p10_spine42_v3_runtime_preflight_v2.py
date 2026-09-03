"""Read-only request preparation tests for P10.7b v2 automation."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[1]
for item in (ROOT, ROOT / "src"):
    if str(item) not in sys.path:
        sys.path.insert(0, str(item))

from autospine_workbench.p10_runtime_environment import (  # noqa: E402
    P10RuntimeEnvironment,
)
from autospine_workbench.p10_spine42_v3_runtime_preflight_v2 import (  # noqa: E402
    P10Spine42V3RuntimePreflightV2,
    P10Spine42V3RuntimePreflightV2Error,
    _require_create_ready_p10_spine42_v3_runtime_preflight_v2,
)
from autospine_workbench import (  # noqa: E402
    p10_spine42_v3_runtime_preflight_v2 as preflight_module,
)
from tests.p10_spine42_v3_runtime_preflight_v2_support import (  # noqa: E402
    BridgeFactory, PreflightV2Fixture, sha,
)


class P10Spine42V3RuntimePreflightV2Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temporary.name)
        cls.fixture = PreflightV2Fixture(cls.root)

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def _subject(self, *, candidates=None, catalogs=None, environments=None,
                 bridge=None):
        candidate = self.fixture.candidate
        revalidate = Mock(side_effect=candidates or [candidate, candidate])
        catalog = Mock(side_effect=catalogs or [self.fixture.catalog()] * 2)
        discover = Mock(side_effect=environments or [
            self.fixture.environment, self.fixture.environment,
        ])
        factory = bridge or BridgeFactory(self.fixture)
        subject = P10Spine42V3RuntimePreflightV2(
            self.root, candidate_revalidator=revalidate,
            catalog_reader=catalog, bridge_factory=factory,
            environment_discovery=discover,
        )
        return subject, revalidate, catalog, discover, factory

    def test_explicit_prepare_and_refresh_are_exact_and_path_free(self):
        subject, revalidate, catalog, discover, bridge = self._subject()
        prepared = subject.prepare(
            self.fixture.payload(), selection_source="explicit",
        )
        refreshed = subject.refresh_for_create(prepared)
        self.assertEqual(prepared.request.canonical_bytes,
                         refreshed.request.canonical_bytes)
        self.assertEqual(2, revalidate.call_count)
        self.assertEqual(0, catalog.call_count)
        self.assertEqual(2, discover.call_count)
        self.assertEqual(1, len(bridge.build_calls))
        self.assertEqual(1, len(bridge.rebuild_calls))
        request = refreshed.request.document
        bundle = self.fixture.bundle
        self.assertEqual({
            "project_id": bundle.project_id, "clip_id": bundle.clip_id,
            "skeleton_json_sha256": bundle.skeleton_json_sha256,
            "spine42_v3_bundle_sha256": bundle.bundle_sha256,
        }, request["source"])
        public = refreshed.public_document()
        self.assertFalse(public["runner_execution_authorized"])
        self.assertFalse(public["publication_authorized"])
        self.assertNotIn("path", repr(public).lower())
        self.assertNotIn(str(self.root / "private"), repr(public))
        self.assertNotIn(str(self.root / "private"), repr(refreshed))

    def test_automatic_source_must_remain_the_fresh_recommendation(self):
        subject, revalidate, catalog, _, _ = self._subject()
        prepared = subject.prepare(
            self.fixture.payload(), selection_source="automatic",
        )
        refreshed = subject.refresh_for_create(prepared)
        self.assertEqual(prepared.request.job_id, refreshed.request.job_id)
        self.assertEqual(2, catalog.call_count)
        self.assertEqual(2, revalidate.call_count)

        changed = self.fixture.catalog(mode="selection_required")
        subject, _, catalog, _, _ = self._subject(
            catalogs=[self.fixture.catalog(), changed],
        )
        prepared = subject.prepare(
            self.fixture.payload(), selection_source="automatic",
        )
        with self.assertRaises(P10Spine42V3RuntimePreflightV2Error):
            subject.refresh_for_create(prepared)
        self.assertEqual(2, catalog.call_count)

    def test_automatic_catalog_check_is_the_last_mutable_observation(self):
        calls = []
        candidate = self.fixture.candidate
        bridge = BridgeFactory(self.fixture)
        bridge.build = Mock(side_effect=lambda *_: (
            calls.append("source") or self.fixture.source))
        revalidate = Mock(side_effect=lambda *_: (
            calls.append("candidate") or candidate))
        discover = Mock(side_effect=lambda *_: (
            calls.append("environment") or self.fixture.environment))
        catalog = Mock(side_effect=lambda *_: (
            calls.append("catalog") or self.fixture.catalog()))
        subject = P10Spine42V3RuntimePreflightV2(
            self.root, candidate_revalidator=revalidate,
            catalog_reader=catalog, bridge_factory=bridge,
            environment_discovery=discover,
        )
        request = subject._request
        subject._request = lambda *args: (
            calls.append("request") or request(*args))
        subject.prepare(self.fixture.payload(), selection_source="automatic")
        self.assertEqual(
            ["candidate", "source", "environment", "request", "catalog"],
            calls,
        )

    def test_new_candidate_directory_midflight_blocks_automatic_prepare(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "candidate-a").mkdir()

            def discover(_state_root):
                (root / "candidate-b").mkdir()
                return self.fixture.environment

            def catalog(_state_root):
                mode = "automatic" if len(list(root.iterdir())) == 1 \
                    else "selection_required"
                return self.fixture.catalog(mode=mode)

            subject = P10Spine42V3RuntimePreflightV2(
                root,
                candidate_revalidator=lambda *_: self.fixture.candidate,
                catalog_reader=catalog,
                bridge_factory=BridgeFactory(self.fixture),
                environment_discovery=discover,
            )
            with self.assertRaises(P10Spine42V3RuntimePreflightV2Error):
                subject.prepare(
                    self.fixture.payload(), selection_source="automatic",
                )

    def test_issuer_secrets_are_not_module_globals(self):
        for name in ("_RECEIPT", "_ISSUED", "_ISSUED_LOCK", "_issue"):
            with self.subTest(name=name):
                self.assertFalse(hasattr(preflight_module, name))

    def test_manual_selection_ignores_recommendation_but_not_exact_entry(self):
        subject, revalidate, catalog, _, _ = self._subject(
            catalogs=[self.fixture.catalog(mode="selection_required")],
        )
        prepared = subject.prepare(
            self.fixture.payload(), selection_source="explicit",
        )
        subject.refresh_for_create(prepared)
        self.assertEqual(2, revalidate.call_count)
        catalog.assert_not_called()

        other = self.fixture.make_candidate("f")
        subject, _, _, _, _ = self._subject(
            candidates=[self.fixture.candidate, other],
        )
        prepared = subject.prepare(
            self.fixture.payload(), selection_source="explicit",
        )
        with self.assertRaises(P10Spine42V3RuntimePreflightV2Error):
            subject.refresh_for_create(prepared)

    def test_environment_or_source_drift_fails_before_create_handoff(self):
        changed_browser = replace(
            self.fixture.environment.browser, executable_sha256=sha("9"),
        )
        changed = P10RuntimeEnvironment(
            self.fixture.environment.runtime, changed_browser,
        )
        subject, _, _, _, _ = self._subject(
            environments=[self.fixture.environment, changed],
        )
        prepared = subject.prepare(
            self.fixture.payload(), selection_source="explicit",
        )
        with self.assertRaises(P10Spine42V3RuntimePreflightV2Error):
            subject.refresh_for_create(prepared)

        bridge = BridgeFactory(self.fixture)
        bridge.rebuild_and_verify = Mock(side_effect=RuntimeError("drift"))
        subject, _, _, _, _ = self._subject(bridge=bridge)
        prepared = subject.prepare(
            self.fixture.payload(), selection_source="explicit",
        )
        with self.assertRaises(P10Spine42V3RuntimePreflightV2Error):
            subject.refresh_for_create(prepared)

    def test_unavailable_environment_invalid_mode_and_errors_are_path_free(self):
        subject, _, _, _, _ = self._subject(
            environments=[P10RuntimeEnvironment(None, None)],
        )
        for mode in ("manual", "Automatic", None, 1):
            with self.subTest(mode=mode), self.assertRaises(
                P10Spine42V3RuntimePreflightV2Error
            ) as caught:
                subject.prepare(
                    self.fixture.payload(), selection_source=mode,
                )
            self.assertNotIn(str(self.root), str(caught.exception))
        with self.assertRaises(P10Spine42V3RuntimePreflightV2Error) as caught:
            subject.prepare(
                self.fixture.payload(), selection_source="explicit",
            )
        self.assertNotIn(str(self.root), str(caught.exception))

    def test_malformed_payload_fails_before_catalog_or_environment_discovery(self):
        subject, revalidate, catalog, discover, bridge = self._subject()
        invalid = self.fixture.payload()
        invalid["explicit_run_confirmation"] = False
        with self.assertRaises(P10Spine42V3RuntimePreflightV2Error):
            subject.prepare(invalid, selection_source="automatic")
        revalidate.assert_not_called()
        catalog.assert_not_called()
        discover.assert_not_called()
        self.assertEqual([], bridge.build_calls)

    def test_only_same_root_refresh_can_issue_create_ready_generation(self):
        subject, *_ = self._subject(
            candidates=[self.fixture.candidate] * 3,
            catalogs=[self.fixture.catalog()] * 3,
            environments=[self.fixture.environment] * 3,
        )
        initial = subject.prepare(
            self.fixture.payload(), selection_source="automatic",
        )
        with self.assertRaises(P10Spine42V3RuntimePreflightV2Error):
            _require_create_ready_p10_spine42_v3_runtime_preflight_v2(initial)
        other_root = self.root / "other-preflight-root"
        other_root.mkdir(exist_ok=True)
        other = P10Spine42V3RuntimePreflightV2(
            other_root,
            candidate_revalidator=lambda *_: self.fixture.candidate,
            catalog_reader=lambda *_: self.fixture.catalog(),
            bridge_factory=BridgeFactory(self.fixture),
            environment_discovery=lambda *_: self.fixture.environment,
        )
        with self.assertRaises(P10Spine42V3RuntimePreflightV2Error):
            other.refresh_for_create(initial)
        ready = subject.refresh_for_create(initial)
        recorded = _require_create_ready_p10_spine42_v3_runtime_preflight_v2(
            ready
        )
        self.assertEqual(subject.state_root, recorded[0])
        execution_ready = subject.refresh_for_execution(ready)
        self.assertEqual(ready.request.canonical_bytes,
                         execution_ready.request.canonical_bytes)
        with self.assertRaises(P10Spine42V3RuntimePreflightV2Error):
            _require_create_ready_p10_spine42_v3_runtime_preflight_v2(
                execution_ready
            )


if __name__ == "__main__":
    unittest.main()
