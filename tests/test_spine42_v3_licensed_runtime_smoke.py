"""Opt-in official Spine 4.2.119 smoke for the P10.7b browser boundary."""

from __future__ import annotations

import os
from pathlib import Path
import sys
import tempfile
import unittest
from urllib.parse import quote


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for candidate in (ROOT, SRC):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from autospine_workbench.body_sway_browser_profile_lease import (  # noqa: E402
    BodySwayBrowserProfileLease,
)
from autospine_workbench.body_sway_capture_server_lease import (  # noqa: E402
    BodySwayCaptureServerLease,
)
from autospine_workbench.locked_browser_executable_lease import (  # noqa: E402
    LockedBrowserExecutableLease,
)
from autospine_workbench.p10_spine42_v3_commands import (  # noqa: E402
    compile_body_sway_spine42_v3_command,
)
from autospine_workbench.png_rgba import decode_rgba_png  # noqa: E402
from autospine_workbench.spine42_runtime_inputs import (  # noqa: E402
    require_runtime_package,
)
from autospine_workbench.spine42_v3_bundle_reader import (  # noqa: E402
    VerifiedSpine42V3BundleReader,
)
from autospine_workbench.spine42_v3_headless_browser import (  # noqa: E402
    run_spine42_v3_headless_capture,
)
from autospine_workbench.spine42_v3_runtime_capture_collector import (  # noqa: E402
    Spine42V3RuntimeCaptureCollector,
)
from autospine_workbench.spine42_v3_runtime_capture_server import (  # noqa: E402
    create_spine42_v3_runtime_capture_server,
)
from autospine_workbench.spine42_v3_runtime_plan import (  # noqa: E402
    build_spine42_v3_runtime_plan,
)
from autospine_workbench.spine42_v3_runtime_session import (  # noqa: E402
    build_spine42_v3_runtime_sessions,
)
from tests.spine42_v3_storage_helpers import (  # noqa: E402
    Spine42V3StorageFixture,
)


CHROME_ENV = "AUTOSPINE_REAL_CHROME"
RUNTIME_ENV = "AUTOSPINE_SPINE42_RUNTIME_ROOT"
ACK_ENV = "AUTOSPINE_SPINE42_RUNTIME_LICENSE_ACKNOWLEDGED"
REQUIRED_ENV = (
    os.environ.get(CHROME_ENV)
    and os.environ.get(RUNTIME_ENV)
    and os.environ.get(ACK_ENV) == "1"
)


@unittest.skipUnless(
    REQUIRED_ENV,
    f"set {CHROME_ENV}, {RUNTIME_ENV}, and {ACK_ENV}=1",
)
class Spine42V3LicensedRuntimeSmokeTests(unittest.TestCase):
    def test_opaque_alpha_and_isolate_artifacts_use_the_official_runtime(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = Spine42V3StorageFixture(Path(temporary))
            source = fixture.published_v3
            with fixture.compile_gate():
                compiled = compile_body_sway_spine42_v3_command(
                    fixture.state_root,
                    fixture.project_id,
                    motion_instance_v3_sha256=
                        source.motion_instance_v3_sha256,
                    motion_instance_v3_bundle_sha256=source.bundle_sha256,
                )
            with fixture.replay_gate():
                bundle = VerifiedSpine42V3BundleReader(
                    fixture.state_root
                ).load(
                    fixture.project_id,
                    compiled.skeleton_json_sha256,
                    compiled.bundle_sha256,
                )
            runtime = require_runtime_package(Path(os.environ[RUNTIME_ENV]))
            plan = build_spine42_v3_runtime_plan(bundle)
            sessions = build_spine42_v3_runtime_sessions(
                bundle, runtime, plan
            )
            collector = Spine42V3RuntimeCaptureCollector(sessions)
            server = create_spine42_v3_runtime_capture_server(
                "127.0.0.1", 0, runtime, bundle, sessions, collector
            )
            artifacts = (
                "case-000.opaque", "case-000.alpha",
                "case-000.isolate-00",
            )
            lease = LockedBrowserExecutableLease(
                Path(os.environ[CHROME_ENV])
            )
            with lease as browser, BodySwayCaptureServerLease(server):
                host, port = server.server_address[:2]
                for artifact_id in artifacts:
                    with BodySwayBrowserProfileLease() as profile:
                        run_spine42_v3_headless_capture(
                            browser,
                            f"http://{host}:{port}/capture/"
                            f"{quote(artifact_id, safe='')}",
                            profile, collector, artifact_id,
                        )
                    self.assertFalse(profile.exists())
            self.assertTrue(lease.closed)
            self.assertEqual(list(artifacts), collector.status()[
                "captured_artifact_ids"
            ])
            for artifact_id in artifacts:
                image = decode_rgba_png(
                    collector._captures[artifact_id],
                    source_name=f"{artifact_id}.png",
                )
                self.assertEqual((640, 640), (image.width, image.height))
                self.assertTrue(any(image.pixels[index + 3] for index in range(
                    0, len(image.pixels), 4
                )))


if __name__ == "__main__":
    unittest.main()
