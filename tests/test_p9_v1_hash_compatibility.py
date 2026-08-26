"""Sentinels that keep P9 overlays outside the established P5/P6 trust domain."""

from __future__ import annotations

from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from autospine_workbench.motion_instance_validation import (  # noqa: E402
    instance_sha256,
)
from autospine_workbench.spine42_contract import (  # noqa: E402
    spine42_json_sha256,
)
from autospine_workbench.spine42_json_adapter import (  # noqa: E402
    build_spine42_json,
)
from tests.test_spine42_json_adapter import (  # noqa: E402
    motion_pair,
    rig_fixture,
)


class P9V1HashCompatibilityTests(unittest.TestCase):
    def test_p5_instance_and_p6_adapter_hashes_remain_pinned(self):
        rig = rig_fixture()
        target, instance = motion_pair(rig)
        self.assertEqual(
            "f406c5920a308a748b6de4153779d1905cbf43d12b57ccc124f2191d85d3e1fa",
            instance_sha256(instance),
        )
        self.assertEqual(
            "06bbbb1ffa5633890b1a95d09a2f24a25611e03e78b7ffafeba6b65aac657d6b",
            spine42_json_sha256(build_spine42_json(rig)),
        )
        self.assertEqual(
            "7d481c8a7ff893343057e69064c3731d8a9cd97efd849fc5846254ce09299dad",
            spine42_json_sha256(build_spine42_json(
                rig, motion_instance=instance, target_profile=target,
            )),
        )


if __name__ == "__main__":
    unittest.main()
