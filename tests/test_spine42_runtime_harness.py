from __future__ import annotations

import copy
import hashlib
import http.client
import json
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for candidate in (ROOT, SRC):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from autospine_workbench.png_rgba import RgbaImage, encode_rgba_png  # noqa: E402
from autospine_workbench.spine42_runtime_contract import (  # noqa: E402
    GOLDEN_FORMAT,
    RUNTIME_NPM_INTEGRITY,
    Spine42RuntimeContractError,
    build_runtime_session,
    require_runtime_golden,
)
from autospine_workbench.spine42_runtime_inputs import (  # noqa: E402
    Spine42RuntimeInputError,
    require_export_files,
    require_runtime_package,
)
from autospine_workbench.spine42_runtime_page import HARNESS_JS  # noqa: E402
from autospine_workbench.spine42_runtime_regression import (  # noqa: E402
    Spine42CaptureStore,
)
from autospine_workbench.spine42_runtime_server import (  # noqa: E402
    create_spine42_runtime_server,
)


def rgba_png(width: int, height: int, color: bytes = b"\x10\x20\x30\xff") -> bytes:
    return encode_rgba_png(RgbaImage(width, height, color * (width * height)))


def runtime_package(path: Path):
    with patch(
        "autospine_workbench.spine42_runtime_inputs."
        "SPINE_PLAYER_JAVASCRIPT_SHA256",
        hashlib.sha256(b"runtime-js").hexdigest(),
    ), patch(
        "autospine_workbench.spine42_runtime_inputs."
        "SPINE_PLAYER_STYLESHEET_SHA256",
        hashlib.sha256(b"runtime-css").hexdigest(),
    ):
        return require_runtime_package(path)


class RuntimeFixture:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.runtime = root / "runtime"
        (self.runtime / "dist" / "iife").mkdir(parents=True)
        (self.runtime / "package.json").write_text(json.dumps({
            "name": "@esotericsoftware/spine-player",
            "version": "4.2.119",
            "dependencies": {"@esotericsoftware/spine-webgl": "4.2.119"},
        }), encoding="utf-8")
        (self.runtime / "dist" / "iife" / "spine-player.min.js").write_bytes(b"runtime-js")
        (self.runtime / "dist" / "spine-player.min.css").write_bytes(b"runtime-css")
        (self.runtime / "LICENSE").write_bytes(b"official runtime license fixture")
        self.export = root / "export"
        self.export.mkdir()
        (self.export / "skeleton.json").write_text(json.dumps({
            "skeleton": {"spine": "4.2", "x": 0, "y": 0, "width": 2, "height": 2},
            "bones": [{"name": "root"}], "slots": [],
            "skins": [{"name": "default", "attachments": {}}], "animations": {},
        }), encoding="utf-8")
        (self.export / "skeleton.atlas").write_text(
            "skeleton.png\nsize: 2,2\nformat: RGBA8888\nfilter: Linear,Linear\nrepeat: none\n",
            encoding="utf-8",
        )
        (self.export / "skeleton.png").write_bytes(rgba_png(2, 2))


def golden_suite(session: dict, png_sha: str) -> dict:
    cases = []
    for case_id, clip, time in (
        ("setup", None, 0.0),
        ("idle.t1000", "idle", 1.0),
        ("wave-left.t0600", "wave.left", 0.6),
    ):
        cases.append({
            "id": case_id, "clip": clip, "time_seconds": time,
            "assets": {
                key: value for key, value in session["assets"].items()
                if key.endswith("_sha256")
            },
            "golden": {"path": f"{case_id}.approved.png", "png_sha256": png_sha},
            "thresholds": {
                "max_differing_pixel_ratio": 0.0,
                "max_mean_absolute_error": 0.0,
                "max_channel_delta": 0,
            },
        })
    return {
        "format": GOLDEN_FORMAT, "format_version": 1,
        "runtime": session["runtime"],
        "capture": {
            key: session["capture"][key]
            for key in ("viewport", "device_pixel_ratio", "background")
        },
        "cases": cases,
    }


class Spine42RuntimeContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.fx = RuntimeFixture(Path(self.temporary.name))

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_exact_package_and_export_are_read_once_into_session(self) -> None:
        runtime = runtime_package(self.fx.runtime)
        exports = require_export_files(self.fx.export)
        session = build_runtime_session(exports, viewport=(64, 96), case={
            "id": "idle.t1000", "clip": "idle", "time_seconds": 1,
        })
        self.assertEqual("4.2.119", session["runtime"]["version"])
        self.assertEqual(RUNTIME_NPM_INTEGRITY, session["runtime"]["npm_integrity"])
        self.assertEqual({"width": 64, "height": 96}, session["capture"]["viewport"])
        self.assertEqual("idle", session["case"]["clip"])
        self.assertEqual(b"runtime-js", runtime.javascript_bytes)
        self.assertEqual((2, 2), exports.texture_size)

    def test_browser_capture_waits_for_fixed_rgba_canvas(self) -> None:
        self.assertIn(b"alpha: true", HARNESS_JS)
        self.assertIn(b"player.canvas.style.width", HARNESS_JS)
        self.assertIn(b"canvasHasFixedViewport(player)", HARNESS_JS)

    def test_package_version_atlas_page_and_skeleton_version_fail_closed(self) -> None:
        package = self.fx.runtime / "package.json"
        value = json.loads(package.read_text(encoding="utf-8"))
        value["version"] = "4.2.118"
        package.write_text(json.dumps(value), encoding="utf-8")
        with self.assertRaisesRegex(Spine42RuntimeInputError, "4.2.119"):
            runtime_package(self.fx.runtime)
        package_value = {**value, "version": "4.2.119"}
        package.write_text(json.dumps(package_value), encoding="utf-8")
        (self.fx.export / "skeleton.atlas").write_text("other.png\n", encoding="utf-8")
        with self.assertRaisesRegex(Spine42RuntimeInputError, "first page"):
            require_export_files(self.fx.export)

    def test_runtime_dist_bytes_must_match_the_pinned_snapshot(self) -> None:
        runtime_package(self.fx.runtime)
        javascript = (
            self.fx.runtime / "dist" / "iife" / "spine-player.min.js"
        )
        javascript.write_bytes(b"forged-runtime-js")
        with self.assertRaisesRegex(Spine42RuntimeInputError, "dist bytes"):
            runtime_package(self.fx.runtime)

    def test_golden_suite_requires_exact_runtime_three_clips_sha_and_thresholds(self) -> None:
        exports = require_export_files(self.fx.export)
        session = build_runtime_session(exports, viewport=(64, 64))
        approved = rgba_png(64, 64)
        contract = golden_suite(session, hashlib.sha256(approved).hexdigest())
        self.assertEqual(contract, require_runtime_golden(contract))
        bad = copy.deepcopy(contract)
        bad["cases"] = bad["cases"][:2]
        with self.assertRaisesRegex(Spine42RuntimeContractError, "three"):
            require_runtime_golden(bad)
        bad = copy.deepcopy(contract)
        bad["runtime"]["version"] = "4.2.118"
        with self.assertRaisesRegex(Spine42RuntimeContractError, "identity"):
            require_runtime_golden(bad)
        bad = copy.deepcopy(contract)
        bad["cases"][0]["assets"]["unbound_sha256"] = "f" * 64
        with self.assertRaisesRegex(Spine42RuntimeContractError, "fields"):
            require_runtime_golden(bad)

    def test_capture_store_hashes_and_compares_without_approving(self) -> None:
        exports = require_export_files(self.fx.export)
        session = build_runtime_session(exports, viewport=(64, 64))
        approved = rgba_png(64, 64)
        approved_sha = hashlib.sha256(approved).hexdigest()
        golden = golden_suite(session, approved_sha)
        golden_root = Path(self.temporary.name) / "goldens"
        golden_root.mkdir()
        for item in golden["cases"]:
            (golden_root / item["golden"]["path"]).write_bytes(approved)
        store = Spine42CaptureStore(
            Path(self.temporary.name) / "captures", session,
            golden=golden, golden_root=golden_root,
        )
        report = store.record_capture("setup", approved, device_pixel_ratio=1)
        self.assertEqual("passed", report["comparison"]["status"])
        self.assertEqual(approved_sha, report["image"]["png_sha256"])
        self.assertTrue((store.root / "setup.actual.png").is_file())
        self.assertFalse((store.root / "setup.approved.png").exists())
        changed = rgba_png(64, 64, b"\x11\x20\x30\xff")
        report = store.record_capture("setup", changed, device_pixel_ratio=1)
        self.assertEqual("rejected", report["comparison"]["status"])


class Spine42RuntimeServerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.fx = RuntimeFixture(Path(self.temporary.name))
        self.runtime = runtime_package(self.fx.runtime)
        self.exports = require_export_files(self.fx.export)
        self.session = build_runtime_session(self.exports, viewport=(64, 64))
        self.store = Spine42CaptureStore(
            Path(self.temporary.name) / "captures", self.session
        )
        self.server = create_spine42_runtime_server(
            "127.0.0.1", 0, self.runtime, self.exports, self.session, self.store
        )
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.host, self.port = self.server.server_address[:2]

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        self.temporary.cleanup()

    def request(self, method: str, path: str, body: bytes | None = None,
                headers: dict[str, str] | None = None) -> tuple[int, dict[str, str], bytes]:
        connection = http.client.HTTPConnection(self.host, self.port, timeout=5)
        connection.request(method, path, body=body, headers=headers or {})
        response = connection.getresponse()
        raw = response.read()
        result = response.status, dict((key.lower(), value) for key, value in response.getheaders()), raw
        connection.close()
        return result

    def test_serves_snapshots_with_csp_and_records_png_protocol(self) -> None:
        (self.fx.runtime / "dist" / "iife" / "spine-player.min.js").write_bytes(b"changed")
        status, headers, raw = self.request("GET", "/runtime/spine-player.min.js")
        self.assertEqual(200, status)
        self.assertEqual(b"runtime-js", raw)
        self.assertIn("script-src 'self'", headers["content-security-policy"])
        status, _, html = self.request("GET", "/case/setup")
        self.assertEqual(200, status)
        self.assertIn(b"__AUTOSPINE", self.request("GET", "/harness.js")[2])
        self.assertIn(b'data-case-id="setup"', html)
        capture = rgba_png(64, 64)
        status, _, raw = self.request("POST", "/api/capture/setup", capture, {
            "Content-Type": "image/png",
            "Origin": f"http://{self.host}:{self.port}",
            "X-Autospine-Device-Pixel-Ratio": "1",
        })
        self.assertEqual(200, status, raw)
        result = json.loads(raw)
        self.assertEqual("not-configured", result["report"]["comparison"]["status"])
        status, _, raw = self.request("GET", "/api/status")
        self.assertTrue(json.loads(raw)["complete"])

    def test_rejects_foreign_host_origin_wrong_dpr_and_unknown_case(self) -> None:
        self.assertEqual(403, self.request("GET", "/api/session", headers={
            "Host": "attacker.example",
        })[0])
        capture = rgba_png(64, 64)
        base = {"Content-Type": "image/png", "X-Autospine-Device-Pixel-Ratio": "1"}
        self.assertEqual(403, self.request("POST", "/api/capture/setup", capture, {
            **base, "Origin": "https://attacker.example",
        })[0])
        self.assertEqual(400, self.request("POST", "/api/capture/setup", capture, {
            **base, "X-Autospine-Device-Pixel-Ratio": "2",
        })[0])
        self.assertEqual(400, self.request("POST", "/api/capture/idle", capture, base)[0])


if __name__ == "__main__":
    unittest.main()
