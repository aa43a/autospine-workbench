"""Pinned byte-level regression checks for the two approved P2 setup images."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from autospine_workbench.png_rgba import (  # noqa: E402
    RgbaImage,
    encode_rgba_png,
    read_rgba_png,
)
from autospine_workbench.rig_setup_artifact import (  # noqa: E402
    encoder_identity,
    renderer_identity,
)


GOLDEN_ROOT = ROOT / "tests" / "goldens" / "p2-setup"


class ApprovedP2SetupGoldenTests(unittest.TestCase):
    def test_real_setup_goldens_are_canonical_and_match_contracts(self) -> None:
        contracts = sorted(GOLDEN_ROOT.glob("*.approved.json"))
        self.assertEqual(2, len(contracts))

        for contract_path in contracts:
            with self.subTest(contract=contract_path.name):
                document = json.loads(contract_path.read_text(encoding="utf-8"))
                image_contract = document["image"]
                image_path = contract_path.parent / image_contract["path"]
                raw = image_path.read_bytes()
                decoded = read_rgba_png(image_path)

                self.assertEqual("autospine-setup-golden", document["format"])
                self.assertEqual(1, document["format_version"])
                self.assertEqual(renderer_identity(), document["renderer"])
                self.assertEqual(encoder_identity(), document["encoder"])
                self.assertEqual(
                    [image_contract["width"], image_contract["height"]],
                    [decoded.width, decoded.height],
                )
                self.assertEqual(
                    image_contract["rgba_sha256"],
                    hashlib.sha256(decoded.pixels).hexdigest(),
                )
                self.assertEqual(
                    image_contract["png_sha256"], hashlib.sha256(raw).hexdigest()
                )
                self.assertEqual(
                    raw,
                    encode_rgba_png(
                        RgbaImage(decoded.width, decoded.height, decoded.pixels)
                    ),
                )


if __name__ == "__main__":
    unittest.main()
