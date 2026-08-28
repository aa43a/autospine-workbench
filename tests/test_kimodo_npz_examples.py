"""Keep the operator-facing Kimodo NPZ templates inside the formal contract."""

from __future__ import annotations

import json
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from autospine_workbench.kimodo_npz_map_validation import (  # noqa: E402
    require_kimodo_npz_map,
)
from autospine_workbench.camera_model_validation import (  # noqa: E402
    require_camera_matches_kimodo_map,
)
from autospine_workbench.kimodo_npz_source import (  # noqa: E402
    require_kimodo_npz_source,
)


EXAMPLES = ROOT / "examples" / "kimodo"


class KimodoNpzExampleTests(unittest.TestCase):
    def test_operator_templates_remain_semantically_compatible(self) -> None:
        source = json.loads(
            (EXAMPLES / "soma77-source.template.json").read_text("utf-8")
        )
        mapping = json.loads(
            (EXAMPLES / "soma77-front.map.example.json").read_text("utf-8")
        )
        camera = json.loads(
            (EXAMPLES / "soma77-front.camera.example.json").read_text("utf-8")
        )

        require_kimodo_npz_source(source)
        require_kimodo_npz_map(mapping, source=source)
        require_camera_matches_kimodo_map(camera, mapping)
        self.assertEqual("0" * 64, source["raw_npz"]["sha256"])
        self.assertIn("replace", source["source_id"])
        self.assertIn("replace", mapping["clip"]["clip_id"])


if __name__ == "__main__":
    unittest.main()
