"""P10.7b canonical evidence, immutable store, and exact reader tests."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for item in (ROOT, SRC):
    if str(item) not in sys.path:
        sys.path.insert(0, str(item))

import autospine_workbench.spine42_v3_runtime_store as store_module  # noqa: E402
from autospine_workbench.browser_executable_snapshot import (  # noqa: E402
    BrowserExecutableSnapshot,
)
from autospine_workbench.browser_version_identity import (  # noqa: E402
    browser_version_identity_sha256,
)
from autospine_workbench.png_rgba import RgbaImage, encode_rgba_png  # noqa: E402
from autospine_workbench.resolved_project import canonical_sha256  # noqa: E402
from autospine_workbench.spine42_runtime_inputs import (  # noqa: E402
    Spine42RuntimePackage,
)
from autospine_workbench.spine42_v3_bundle_integrity import (  # noqa: E402
    VerifiedSpine42V3Bundle,
)
from autospine_workbench.spine42_v3_raster_metrics import (  # noqa: E402
    compute_spine42_v3_raster_metrics,
)
from autospine_workbench.spine42_v3_runtime_bundle import (  # noqa: E402
    BUNDLE_ADDRESS_DOMAIN,
    NAMESPACE,
    build_spine42_v3_runtime_bundle,
    replay_runtime_evidence,
    spine42_v3_runtime_bundle_sha256,
)
from autospine_workbench.spine42_v3_runtime_capture_collector import (  # noqa: E402
    Spine42V3RuntimeCaptureSnapshot,
)
from autospine_workbench.spine42_v3_runtime_evidence import (  # noqa: E402
    AUTHORITY,
    MANIFEST_NAME,
    METRICS_NAME,
    RELEASE_GATE,
    Spine42V3RuntimeEvidenceError,
    artifact_inventory,
    build_spine42_v3_runtime_evidence,
    canonical_json_bytes,
)
from autospine_workbench.spine42_v3_runtime_plan import (  # noqa: E402
    PLAN_HASH_DOMAIN,
)
from autospine_workbench.spine42_v3_runtime_profile import (  # noqa: E402
    spine42_v3_runtime_profile,
    spine42_v3_runtime_profile_sha256,
)
from autospine_workbench.spine42_v3_runtime_reader import (  # noqa: E402
    Spine42V3RuntimeNotFound,
    Spine42V3RuntimeReaderError,
    VerifiedSpine42V3RuntimeReader,
)
from autospine_workbench.spine42_v3_runtime_store import (  # noqa: E402
    Spine42V3RuntimeStore,
    Spine42V3RuntimeStoreError,
)


PROJECT, CLIP = "runtime-fixture", "idle"
SKELETON_SHA, UPSTREAM_SHA, RUN_SHA = "1" * 64, "2" * 64, "3" * 64
SESSION_SHA = "4" * 64


def _plan():
    profile = spine42_v3_runtime_profile()
    artifacts = [
        _artifact("case-000.opaque", "opaque_composite", None, None, "#20242aff"),
        _artifact("case-000.alpha", "transparent_composite", None, None, "#00000000"),
        _artifact("case-000.isolate-00", "attachment_isolate", "slot", "piece", "#00000000"),
    ]
    case = {
        "case_id": "setup", "ordinal": 0, "animation": None, "tick": 0,
        "time_seconds": 0.0, "selection_reasons": ["setup"],
        "artifact_ids": [row["artifact_id"] for row in artifacts],
    }
    body = {
        "format": "autospine-spine42-v3-runtime-raster-plan",
        "format_version": 1,
        "profile_sha256": spine42_v3_runtime_profile_sha256(),
        "source": {
            "project_id": PROJECT, "clip_id": CLIP,
            "skeleton_json_sha256": SKELETON_SHA,
            "bundle_sha256": UPSTREAM_SHA,
        },
        "runtime": profile["runtime"],
        "capture": {
            **profile["capture"],
            "world_viewport": {"x": 0.0, "y": 0.0, "width": 10.0, "height": 10.0},
        },
        "sampled_scope": {
            "kind": "bounded-discrete-samples-only", "animation": CLIP,
            "duration_ticks": 0, "sampled_ticks": [0],
            "sampled_tick_ranges": [[0, 0]],
            "continuous_time_safety_claimed": False,
            "unsampled_ticks_covered": False,
        },
        "attachments": [{
            "ordinal": 0, "slot_id": "slot", "attachment_id": "piece",
        }],
        "cases": [case], "artifacts": artifacts,
    }
    return {
        **body,
        "capture_plan_sha256": canonical_sha256({
            "domain": PLAN_HASH_DOMAIN, **body,
        }),
    }


def _artifact(identifier, kind, slot, attachment, background):
    return {
        "artifact_id": identifier, "path": f"{identifier}.png",
        "kind": kind, "case_id": "setup", "slot_id": slot,
        "attachment_id": attachment, "background": background,
    }


def _captures(plan):
    size = 640 * 640
    opaque = encode_rgba_png(RgbaImage(640, 640, bytes((20, 30, 40, 255)) * size))
    pixels = bytearray(size * 4)
    center = (320 * 640 + 320) * 4
    pixels[center:center + 4] = b"\xff\xff\xff\xff"
    alpha = encode_rgba_png(RgbaImage(640, 640, bytes(pixels)))
    return {
        plan["artifacts"][0]["artifact_id"]: opaque,
        plan["artifacts"][1]["artifact_id"]: alpha,
        plan["artifacts"][2]["artifact_id"]: alpha,
    }


def _reports(plan, captures):
    assets = {
        "skeleton_sha256": SKELETON_SHA,
        "atlas_sha256": "5" * 64, "texture_sha256": "6" * 64,
    }
    rows = []
    for artifact in plan["artifacts"]:
        raw = captures[artifact["artifact_id"]]
        rows.append({
            "status": "captured", "session_set_sha256": SESSION_SHA,
            "plan_sha256": plan["capture_plan_sha256"],
            "source": plan["source"], "runtime": plan["runtime"],
            "assets": assets, "capture": plan["capture"],
            "case": plan["cases"][0], "artifact": artifact,
            "observables": {
                "official_runtime_loaded": True, "clip_ids": [CLIP],
                "slot_ids": ["slot"],
                "attachments": [{"slot_id": "slot", "attachment_id": "piece"}],
                "isolation": {
                    "artifact_kind": artifact["kind"],
                    "visible_slot_ids": ["slot"], "hidden_slot_ids": [],
                },
            },
            "image": {
                "path": artifact["path"],
                "png_sha256": hashlib.sha256(raw).hexdigest(),
                "width": 640, "height": 640, "size_bytes": len(raw),
            },
        })
    return rows


def _evidence():
    plan = _plan()
    captures = _captures(plan)
    metrics = compute_spine42_v3_raster_metrics(plan, captures)
    source = {
        "skeleton_json_sha256": SKELETON_SHA,
        "spine42_v3_bundle_sha256": UPSTREAM_SHA,
        "run_document_sha256": RUN_SHA,
        "capture_plan_sha256": plan["capture_plan_sha256"],
        "runtime_session_set_sha256": SESSION_SHA,
        "raster_metrics_sha256": metrics["raster_metrics_sha256"],
    }
    browser = {
        "family": "chromium", "reported_version": "128.0.6613.0",
        "version_output_sha256": browser_version_identity_sha256(
            "chromium", "128.0.6613.0"
        ),
        "executable_sha256": "7" * 64, "size_bytes": 4096,
    }
    manifest = {
        "format": "autospine-spine42-v3-runtime-capture",
        "format_version": 1, "project_id": PROJECT, "clip_id": CLIP,
        "source": source,
        "runtime": {
            **plan["runtime"], "package_json_sha256": "8" * 64,
            "license_sha256": "9" * 64, "license_acknowledged": True,
            "license_file_presence_is_authorization": False,
        },
        "browser": browser, "plan": plan,
        "reports": _reports(plan, captures),
        "artifacts": artifact_inventory(plan, captures),
        "authority": AUTHORITY, "status": "captured_unreviewed",
        "release_gate": RELEASE_GATE,
    }
    return replay_runtime_evidence(
        canonical_json_bytes(manifest, 16 * 1024 * 1024, "manifest"),
        canonical_json_bytes(metrics, 16 * 1024 * 1024, "metrics"),
        tuple(captures.items()),
    )


class Spine42V3RuntimeEvidenceStoreTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temporary.name)
        cls.evidence = _evidence()
        cls.bundle = build_spine42_v3_runtime_bundle(cls.evidence)

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def test_builder_binds_exact_inputs_and_license_acknowledgement(self):
        plan, captures = _plan(), self.evidence.capture_bytes
        reports_json = json.dumps(_reports(plan, captures), separators=(",", ":"))
        snapshot = Spine42V3RuntimeCaptureSnapshot(
            reports_json, tuple(captures.items())
        )
        verified = VerifiedSpine42V3Bundle(
            path=Path("unused"), project_id=PROJECT, clip_id=CLIP,
            adapter_profile_sha256="a" * 64, p3_rig_sha256="a" * 64,
            p3_bundle_sha256="a" * 64, motion_instance_v3_sha256="a" * 64,
            motion_instance_v3_bundle_sha256="a" * 64,
            admission_sha256="a" * 64,
            motion_instance_v3_profile_sha256="a" * 64,
            target_profile_sha256="a" * 64,
            skeleton_json_sha256=SKELETON_SHA, atlas_sha256="5" * 64,
            png_sha256="6" * 64, run_identity_sha256="a" * 64,
            run_document_sha256=RUN_SHA, report_sha256="a" * 64,
            bundle_sha256=UPSTREAM_SHA, _source_images=(), _document_items=(),
        )
        runtime = Spine42RuntimePackage(
            Path("runtime"), Path("js"), Path("css"), Path("license"),
            b"js", b"css", "8" * 64, "9" * 64, "8" * 64, "9" * 64,
        )
        browser = BrowserExecutableSnapshot(
            "chrome.exe", "chromium", "128.0.6613.0",
            browser_version_identity_sha256("chromium", "128.0.6613.0"),
            "7" * 64, 4096,
        )
        sessions = SimpleNamespace(plan=plan, sha256=SESSION_SHA)
        metrics = compute_spine42_v3_raster_metrics(plan, captures)
        with patch(
            "autospine_workbench.spine42_v3_runtime_evidence."
            "build_spine42_v3_runtime_plan", return_value=plan,
        ), patch(
            "autospine_workbench.spine42_v3_runtime_evidence."
            "build_spine42_v3_runtime_sessions", return_value=sessions,
        ):
            built = build_spine42_v3_runtime_evidence(
                verified, runtime, browser, plan, snapshot, metrics,
                license_acknowledged=True,
            )
            self.assertEqual(self.evidence.manifest_bytes, built.manifest_bytes)
            with self.assertRaises(Spine42V3RuntimeEvidenceError):
                build_spine42_v3_runtime_evidence(
                    verified, runtime, browser, plan, snapshot, metrics,
                    license_acknowledged=False,
                )

    def test_bundle_hash_frames_all_names_lengths_and_bytes(self):
        self.assertIsInstance(BUNDLE_ADDRESS_DOMAIN, bytes)
        files = self.bundle.file_items
        self.assertEqual(
            self.bundle.bundle_sha256,
            spine42_v3_runtime_bundle_sha256(files),
        )
        changed = list(files)
        changed[-1] = (changed[-1][0], changed[-1][1] + b"x")
        self.assertNotEqual(
            self.bundle.bundle_sha256,
            spine42_v3_runtime_bundle_sha256(tuple(changed)),
        )

    def test_publish_reuse_fixed_inventory_and_exact_reader(self):
        state = self.root / "state"
        store = Spine42V3RuntimeStore(state)
        first, second = store.publish(self.evidence), store.publish(self.evidence)
        expected = (
            state / "builds" / PROJECT / NAMESPACE / UPSTREAM_SHA /
            self.bundle.bundle_sha256
        )
        self.assertEqual(expected, first.path)
        self.assertFalse(first.reused)
        self.assertTrue(second.reused)
        self.assertEqual(
            {MANIFEST_NAME, METRICS_NAME, "captures"},
            {item.name for item in expected.iterdir()},
        )
        loaded = VerifiedSpine42V3RuntimeReader(state).load(
            PROJECT, UPSTREAM_SHA, self.bundle.bundle_sha256
        )
        self.assertEqual(self.evidence, loaded.evidence)
        self.assertEqual(self.bundle, loaded.bundle)

    def test_concurrent_publishers_converge_without_overwrite(self):
        store = Spine42V3RuntimeStore(self.root / "concurrent")
        with ThreadPoolExecutor(max_workers=6) as pool:
            rows = list(pool.map(lambda _index: store.publish(self.evidence), range(12)))
        self.assertEqual(1, len({row.path for row in rows}))
        self.assertEqual(1, sum(not row.reused for row in rows))

    def test_tamper_extra_and_wrong_case_fail_closed(self):
        mutations = (
            lambda root: (root / METRICS_NAME).write_bytes(
                (root / METRICS_NAME).read_bytes() + b" "
            ),
            lambda root: (root / "foreign.txt").write_bytes(b"x"),
            lambda root: (root / "captures" / "foreign.png").write_bytes(b"x"),
        )
        for index, mutate in enumerate(mutations):
            with self.subTest(index=index):
                state = self.root / f"tamper-{index}"
                published = Spine42V3RuntimeStore(state).publish(self.evidence)
                mutate(published.path)
                with self.assertRaises(Spine42V3RuntimeReaderError):
                    VerifiedSpine42V3RuntimeReader(state).load(
                        PROJECT, UPSTREAM_SHA, self.bundle.bundle_sha256
                    )
        state = self.root / "wrong-case"
        published = Spine42V3RuntimeStore(state).publish(self.evidence)
        source = published.path / MANIFEST_NAME
        source.rename(published.path / MANIFEST_NAME.upper())
        with self.assertRaises(Spine42V3RuntimeReaderError):
            VerifiedSpine42V3RuntimeReader(state).load(
                PROJECT, UPSTREAM_SHA, self.bundle.bundle_sha256
            )

    def test_invalid_input_creates_no_state_and_missing_reader_is_read_only(self):
        state = self.root / "invalid"
        with self.assertRaises(Spine42V3RuntimeStoreError):
            Spine42V3RuntimeStore(state).publish({})  # type: ignore[arg-type]
        self.assertFalse(state.exists())
        missing = self.root / "missing"
        with self.assertRaises(Spine42V3RuntimeNotFound):
            VerifiedSpine42V3RuntimeReader(missing).load(
                PROJECT, UPSTREAM_SHA, self.bundle.bundle_sha256
            )
        self.assertFalse(missing.exists())

    def test_parent_sync_failure_never_returns_false_success(self):
        state = self.root / "sync-failure"
        with patch.object(
            store_module, "sync_directory",
            side_effect=(None, None, OSError("injected parent sync failure")),
        ) as sync, self.assertRaises(Spine42V3RuntimeStoreError):
            Spine42V3RuntimeStore(state).publish(self.evidence)
        self.assertEqual(3, sync.call_count)
        destination = (
            state / "builds" / PROJECT / NAMESPACE / UPSTREAM_SHA /
            self.bundle.bundle_sha256
        )
        self.assertTrue(destination.is_dir())
        manifest = json.loads((destination / MANIFEST_NAME).read_bytes())
        self.assertFalse(manifest["authority"]["release_authority"])
        self.assertEqual("blocked", manifest["release_gate"]["status"])


if __name__ == "__main__":
    unittest.main()
