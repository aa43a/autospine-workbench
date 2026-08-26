"""Adversarial resource-bound tests for shared Spine export validation."""

from __future__ import annotations

from pathlib import Path
import sys
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from autospine_workbench.spine42_atlas import ATLAS_MAX_REGIONS  # noqa: E402
from autospine_workbench.spine42_export_validation import (  # noqa: E402
    Spine42ExportValidationError,
    require_spine42_atlas_inventory,
)
from autospine_workbench.spine42_contract import Spine42ContractError  # noqa: E402
from autospine_workbench.spine42_json_adapter import (  # noqa: E402
    require_projected_spine42_document,
)


class Spine42ExportValidationTests(unittest.TestCase):
    def test_public_projected_document_validator_wraps_malformed_rows(self):
        with self.assertRaises(Spine42ContractError):
            require_projected_spine42_document({
                "bones": [7], "slots": [], "skins": [],
            })

    def test_oversized_region_inventory_is_rejected_before_parsing_rows(self):
        header = [
            "skeleton.png", "size: 1,1", "format: RGBA8888",
            "filter: Linear,Linear", "repeat: none",
        ]
        block = [
            "x", "  rotate: false", "  xy: 0, 0", "  size: 1, 1",
            "  orig: 1, 1", "  offset: 0, 0", "  index: -1",
        ]
        raw = ("\n".join(
            [*header, *(block * (ATLAS_MAX_REGIONS + 1))]
        ) + "\n").encode("utf-8")
        with patch(
            "autospine_workbench.spine42_export_validation.require_safe_token"
        ) as safe, self.assertRaisesRegex(
            Spine42ExportValidationError, "region count"
        ):
            require_spine42_atlas_inventory(raw)
        safe.assert_not_called()


if __name__ == "__main__":
    unittest.main()
