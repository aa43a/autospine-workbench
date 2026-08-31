"""Official runtime execution compilation, store, and exact-reader tests."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for candidate in (ROOT, SRC):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from autospine_workbench.body_sway_runtime_capture_collector import (  # noqa: E402
    BodySwayRuntimeCaptureCollector,
)
from autospine_workbench.body_sway_runtime_capture_session_v2 import (  # noqa: E402
    build_body_sway_runtime_capture_sessions_v2,
)
from autospine_workbench.body_sway_runtime_capture_v2_compiler import (  # noqa: E402
    compile_body_sway_runtime_capture_v2,
)
from autospine_workbench.body_sway_runtime_capture_v2_profile import (  # noqa: E402
    MAX_CAPTURE_ARTIFACTS,
)
from autospine_workbench.body_sway_runtime_execution import (  # noqa: E402
    BodySwayRuntimeExecution,
    BodySwayRuntimeExecutionError,
    compile_body_sway_runtime_execution,
)
from autospine_workbench.body_sway_runtime_execution_bundle import (  # noqa: E402
    BodySwayRuntimeExecutionBundleError,
    body_sway_runtime_execution_bundle_sha256,
    build_body_sway_runtime_execution_bundle,
    replay_body_sway_runtime_execution,
)
from autospine_workbench.body_sway_runtime_execution_profile import (  # noqa: E402
    MANIFEST_NAME,
    NAMESPACE,
    PAYLOAD_NAME,
)
from autospine_workbench.body_sway_runtime_execution_reader import (  # noqa: E402
    VerifiedBodySwayRuntimeExecutionNotFound,
    VerifiedBodySwayRuntimeExecutionReader,
    VerifiedBodySwayRuntimeExecutionReaderError,
)
from autospine_workbench.body_sway_runtime_execution_store import (  # noqa: E402
    BodySwayRuntimeExecutionStore,
    BodySwayRuntimeExecutionStoreError,
)
from autospine_workbench.browser_executable_snapshot import (  # noqa: E402
    BrowserExecutableSnapshot,
)
from autospine_workbench.browser_version_identity import (  # noqa: E402
    browser_version_identity_sha256,
)
from autospine_workbench.temporary_body_sway_preview_v2 import (  # noqa: E402
    compile_temporary_body_sway_preview_v2,
)
from tests.body_sway_preview_v2_helpers import PreviewV2Fixture  # noqa: E402
from tests.body_sway_runtime_capture_helpers import (  # noqa: E402
    RUNTIME_CSS_SHA,
    RUNTIME_JS_SHA,
    capture_png,
    fake_runtime,
)
from tests.test_temporary_body_sway_preview_v2 import (  # noqa: E402
    _patched_source,
    _source_images,
)


@contextmanager
def _fake_runtime_profile():
    modules = (
        "autospine_workbench.body_sway_runtime_capture_session_v2",
        "autospine_workbench.body_sway_runtime_capture_session_v2_validation",
        "autospine_workbench.body_sway_runtime_capture_v2_fields",
    )
    patches = []
    for module in modules:
        patches.extend((
            patch(module + ".SPINE_PLAYER_JAVASCRIPT_SHA256", RUNTIME_JS_SHA),
            patch(module + ".SPINE_PLAYER_STYLESHEET_SHA256", RUNTIME_CSS_SHA),
        ))
    with patches[0], patches[1], patches[2], patches[3], \
            patches[4], patches[5]:
        yield


class BodySwayRuntimeExecutionStoreTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.inputs_root = tempfile.TemporaryDirectory()
        root = Path(cls.inputs_root.name)
        fixture = PreviewV2Fixture(root / "preview")
        inputs = fixture.admit()
        images = _source_images(fixture.fixture.mesh.rig)
        with _patched_source(images):
            cls.preview = compile_temporary_body_sway_preview_v2(
                inputs, fixture.fixture.mesh,
            )
        cls.runtime = replace(
            fake_runtime(root / "runtime"),
            package_json_sha256="a" * 64,
            license_sha256="b" * 64,
        )
        with _fake_runtime_profile():
            cls.sessions = build_body_sway_runtime_capture_sessions_v2(
                cls.preview, cls.runtime,
            )
            collector = BodySwayRuntimeCaptureCollector(cls.sessions)
        png = capture_png()
        for case_id in collector.case_ids:
            collector.record_capture(case_id, png, device_pixel_ratio=1)
        cls.snapshot = collector.snapshot()
        version = "128.0.6613.0"
        cls.browser = BrowserExecutableSnapshot(
            path="C:\\fake\\chrome.exe", family="chromium",
            reported_version=version,
            version_output_sha256=browser_version_identity_sha256(
                "chromium", version,
            ),
            executable_sha256="c" * 64, size_bytes=4096,
        )
        with _fake_runtime_profile():
            cls.capture = compile_body_sway_runtime_capture_v2(
                cls.preview, cls.runtime, cls.sessions,
                cls.snapshot, cls.browser,
            )
            cls.execution = compile_body_sway_runtime_execution(
                cls.preview, cls.runtime, cls.sessions, cls.snapshot,
                cls.browser, cls.capture, license_acknowledged=True,
            )

    @classmethod
    def tearDownClass(cls):
        cls.inputs_root.cleanup()

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.state = self.root / "state"

    def tearDown(self):
        self.temporary.cleanup()

    def publish(self):
        with _fake_runtime_profile():
            return BodySwayRuntimeExecutionStore(self.state).publish(
                self.execution,
            )

    def test_exact_pipeline_bundle_replay_and_license_gate(self):
        with _fake_runtime_profile():
            bundle = build_body_sway_runtime_execution_bundle(self.execution)
            replayed = replay_body_sway_runtime_execution(
                self.execution.canonical_bytes,
                self.capture.canonical_bytes,
                tuple(self.capture.capture_bytes.items()),
            )
        self.assertEqual(self.execution.canonical_bytes,
                         replayed.canonical_bytes)
        self.assertEqual(bundle.bundle_sha256,
                         body_sway_runtime_execution_bundle_sha256(
                             bundle.file_items,
                         ))
        with _fake_runtime_profile(), self.assertRaisesRegex(
            BodySwayRuntimeExecutionError, "license acknowledgement",
        ):
            compile_body_sway_runtime_execution(
                self.preview, self.runtime, self.sessions, self.snapshot,
                self.browser, self.capture, license_acknowledged=False,
            )

    def test_detached_execution_rejects_crosswired_report_fields(self):
        fields = ("runtime", "source", "assets", "capture")
        for field in fields:
            changed = self.execution.document
            changed["reports"][0][field] = {}
            with self.subTest(field=field), self.assertRaises(
                BodySwayRuntimeExecutionError,
            ):
                BodySwayRuntimeExecution.from_detached(
                    changed, self.capture,
                )

    def test_publish_is_content_addressed_and_exactly_reused(self):
        first, second = self.publish(), self.publish()
        expected = (
            self.state / "builds" / self.execution.document["project_id"]
            / NAMESPACE
            / self.execution.document["source"]
            ["temporary_preview_v2_sha256"] / first.bundle_sha256
        )
        self.assertEqual(expected, first.path)
        self.assertFalse(first.reused)
        self.assertTrue(second.reused)
        self.assertEqual(
            {MANIFEST_NAME, PAYLOAD_NAME, "captures"},
            {item.name for item in expected.iterdir()},
        )
        self.assertFalse((expected.parent / "latest").exists())

    def test_exact_reader_round_trips_without_writing(self):
        published = self.publish()
        before = sorted(
            path.relative_to(self.state) for path in self.state.rglob("*")
        )
        with _fake_runtime_profile():
            loaded = VerifiedBodySwayRuntimeExecutionReader(self.state).load(
                published.project_id,
                published.temporary_preview_v2_sha256,
                published.bundle_sha256,
                published.artifact_set_sha256,
            )
        after = sorted(
            path.relative_to(self.state) for path in self.state.rglob("*")
        )
        self.assertEqual(before, after)
        self.assertEqual(self.execution.canonical_bytes,
                         loaded.execution.canonical_bytes)
        self.assertEqual(self.capture.canonical_bytes,
                         loaded.execution.capture.canonical_bytes)
        self.assertEqual(self.capture.capture_bytes,
                         loaded.execution.capture.capture_bytes)

    def test_reader_requires_all_four_exact_address_components(self):
        published = self.publish()
        address = [
            published.project_id,
            published.temporary_preview_v2_sha256,
            published.bundle_sha256,
            published.artifact_set_sha256,
        ]
        replacements = ("wrong-project", "1" * 64, "2" * 64, "3" * 64)
        with _fake_runtime_profile():
            for index, replacement in enumerate(replacements):
                changed = list(address)
                changed[index] = replacement
                with self.subTest(index=index), self.assertRaises(
                    VerifiedBodySwayRuntimeExecutionReaderError,
                ):
                    VerifiedBodySwayRuntimeExecutionReader(self.state).load(
                        *changed,
                    )
        with self.assertRaises(VerifiedBodySwayRuntimeExecutionReaderError):
            VerifiedBodySwayRuntimeExecutionReader(self.state).load(
                address[0], "latest", address[2], address[3],
            )

    def test_missing_reader_is_typed_and_never_creates_state(self):
        absent = self.root / "absent"
        with self.assertRaises(VerifiedBodySwayRuntimeExecutionNotFound):
            VerifiedBodySwayRuntimeExecutionReader(absent).load(
                self.execution.document["project_id"],
                self.execution.document["source"]
                ["temporary_preview_v2_sha256"],
                "4" * 64, self.execution.artifact_set_sha256,
            )
        self.assertFalse(absent.exists())

    def test_concurrent_publications_converge(self):
        store = BodySwayRuntimeExecutionStore(self.state)
        with _fake_runtime_profile():
            with ThreadPoolExecutor(max_workers=8) as pool:
                results = list(pool.map(
                    lambda _index: store.publish(self.execution), range(12),
                ))
        self.assertEqual(1, len({result.path for result in results}))
        self.assertEqual(1, sum(not result.reused for result in results))

    def test_existing_or_extra_tamper_is_never_overwritten(self):
        published = self.publish()
        manifest = published.path / MANIFEST_NAME
        manifest.write_bytes(manifest.read_bytes() + b" ")
        with self.assertRaises(BodySwayRuntimeExecutionStoreError):
            self.publish()
        self.assertTrue(manifest.read_bytes().endswith(b" "))
        (published.path / "captures" / "foreign.png").write_bytes(b"x")
        with _fake_runtime_profile(), self.assertRaises(
            VerifiedBodySwayRuntimeExecutionReaderError,
        ):
            VerifiedBodySwayRuntimeExecutionReader(self.state).load(
                published.project_id,
                published.temporary_preview_v2_sha256,
                published.bundle_sha256,
                published.artifact_set_sha256,
            )

    def test_bundle_hash_rejects_more_than_bounded_artifact_count(self):
        items = (
            (MANIFEST_NAME, b"{}"), (PAYLOAD_NAME, b"{}"),
        ) + tuple(
            (f"captures/case-{index}.png", b"x")
            for index in range(MAX_CAPTURE_ARTIFACTS + 1)
        )
        with self.assertRaises(BodySwayRuntimeExecutionBundleError):
            body_sway_runtime_execution_bundle_sha256(items)


if __name__ == "__main__":
    unittest.main()
