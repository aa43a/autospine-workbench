"""Fixture-only contract and CLI tests for the setup visual golden gate."""

from __future__ import annotations

from contextlib import redirect_stdout
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest

try:
    from jsonschema import Draft202012Validator
except ImportError:  # pragma: no cover - optional test dependency
    Draft202012Validator = None


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from autospine_workbench.cli import main as cli_main  # noqa: E402
from autospine_workbench.manifest_artifacts import (  # noqa: E402
    LayerManifestError,
    require_safe_token,
)
from autospine_workbench.png_rgba import (  # noqa: E402
    RgbaImage,
    encode_rgba_png,
    read_rgba_png,
)
from autospine_workbench.resolved_project import canonical_sha256  # noqa: E402
from autospine_workbench.rig_setup_artifact import (  # noqa: E402
    encoder_identity,
    renderer_identity,
)
from tests.test_rig_bundle import BundleFixture  # noqa: E402


class SetupGoldenCliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        fixture_root = self.root / "fixture"
        fixture_root.mkdir()
        self.fixture = BundleFixture(fixture_root)
        self.bundle, self.rig_sha = self.fixture.publish()
        self.golden_root = self.root / "golden"
        self.golden_root.mkdir()

    def _approve(self, *, change_pixel: bool = False) -> Path:
        setup = json.loads(
            (self.bundle / "setup-render.json").read_text(encoding="utf-8")
        )
        image = read_rgba_png(self.bundle / "setup.png")
        pixels = bytearray(image.pixels)
        if change_pixel:
            pixels[0] ^= 1
        png = encode_rgba_png(RgbaImage(image.width, image.height, bytes(pixels)))
        golden_png = self.golden_root / "approved-setup.png"
        golden_png.write_bytes(png)
        contract = {
            "format": "autospine-setup-golden",
            "format_version": 1,
            "project_id": setup["project_id"],
            "source": {
                "rig_sha256": self.rig_sha,
                "bundle_sha256": self.bundle.name,
                "setup_render_sha256": canonical_sha256(setup),
            },
            "renderer": renderer_identity(),
            "encoder": encoder_identity(),
            "image": {
                "path": golden_png.name,
                "width": image.width,
                "height": image.height,
                "rgba_sha256": hashlib.sha256(bytes(pixels)).hexdigest(),
                "png_sha256": hashlib.sha256(png).hexdigest(),
            },
        }
        path = self.golden_root / "approved.json"
        path.write_text(json.dumps(contract, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return path

    def _run(self, contract: Path) -> tuple[int, str, dict]:
        output = io.StringIO()
        with redirect_stdout(output):
            status = cli_main(
                ["verify-setup-golden", str(self.bundle), str(contract)]
            )
        text = output.getvalue()
        return status, text, json.loads(text)

    def test_bundle_publishes_canonical_setup_with_bound_identities(self) -> None:
        setup = json.loads(
            (self.bundle / "setup-render.json").read_text(encoding="utf-8")
        )
        raw = (self.bundle / "setup.png").read_bytes()
        image = read_rgba_png(self.bundle / "setup.png")
        self.assertEqual(renderer_identity(), setup["renderer"])
        self.assertEqual(encoder_identity(), setup["encoder"])
        self.assertEqual(hashlib.sha256(raw).hexdigest(), setup["image"]["png_sha256"])
        self.assertEqual(
            hashlib.sha256(image.pixels).hexdigest(), setup["image"]["rgba_sha256"]
        )
        self.assertEqual(
            raw,
            encode_rgba_png(RgbaImage(image.width, image.height, image.pixels)),
        )

    def test_pass_is_stable_and_does_not_mutate_bundle_or_golden(self) -> None:
        contract = self._approve()
        protected = {
            path: path.read_bytes()
            for path in (contract, self.golden_root / "approved-setup.png", self.bundle / "setup.png")
        }
        names_before = sorted(path.relative_to(self.root).as_posix() for path in self.root.rglob("*"))
        first_status, first_text, first = self._run(contract)
        second_status, second_text, second = self._run(contract)
        self.assertEqual((0, 0), (first_status, second_status))
        self.assertEqual(first_text, second_text)
        self.assertEqual(first, second)
        self.assertEqual("passed", first["status"])
        self.assertTrue(first["ok"])
        self.assertTrue(all(check["status"] == "passed" for check in first["checks"]))
        self.assertEqual(protected, {path: path.read_bytes() for path in protected})
        self.assertEqual(
            names_before,
            sorted(path.relative_to(self.root).as_posix() for path in self.root.rglob("*")),
        )

    def test_valid_different_golden_is_visual_rejection_exit_one(self) -> None:
        status, _, report = self._run(self._approve(change_pixel=True))
        self.assertEqual(1, status)
        self.assertFalse(report["ok"])
        self.assertEqual("rejected", report["status"])
        rejected = {item["id"] for item in report["checks"] if item["status"] == "rejected"}
        self.assertEqual({"image.rgba_sha256", "image.png_sha256"}, rejected)

    def test_project_mismatch_is_an_explicit_rejection(self) -> None:
        contract_path = self._approve()
        contract = json.loads(contract_path.read_text(encoding="utf-8"))
        contract["project_id"] = "another-project"
        contract_path.write_text(
            json.dumps(contract, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        status, _, report = self._run(contract_path)
        self.assertEqual(1, status)
        rejected = [item["id"] for item in report["checks"] if item["status"] == "rejected"]
        self.assertEqual(["project.identity"], rejected)

    def test_tampered_golden_or_bundle_is_input_error_exit_two(self) -> None:
        contract = self._approve()
        golden = self.golden_root / "approved-setup.png"
        golden.write_bytes(b"not a PNG")
        status, _, report = self._run(contract)
        self.assertEqual(2, status)
        self.assertEqual(("error", "invalid_golden"), (report["status"], report["code"]))

        tampered_root = self.root / "tampered"
        tampered_root.mkdir()
        other = BundleFixture(tampered_root)
        bundle, _ = other.publish()
        (bundle / "setup.png").write_bytes(b"not a PNG")
        output = io.StringIO()
        with redirect_stdout(output):
            status = cli_main(["verify-setup-golden", str(bundle), str(contract)])
        report = json.loads(output.getvalue())
        self.assertEqual(2, status)
        self.assertEqual("invalid_bundle", report["code"])

    @unittest.skipUnless(Draft202012Validator, "jsonschema is not installed")
    def test_published_and_golden_documents_match_their_schemas(self) -> None:
        contract_path = self._approve()
        cases = (
            (
                "rig-setup-render-v1.schema.json",
                json.loads((self.bundle / "setup-render.json").read_text(encoding="utf-8")),
            ),
            (
                "setup-golden-v1.schema.json",
                json.loads(contract_path.read_text(encoding="utf-8")),
            ),
        )
        for name, document in cases:
            with self.subTest(name):
                schema = json.loads((ROOT / "schemas" / name).read_text(encoding="utf-8"))
                Draft202012Validator.check_schema(schema)
                Draft202012Validator(schema).validate(document)

    @unittest.skipUnless(Draft202012Validator, "jsonschema is not installed")
    def test_schema_and_runtime_reject_portable_path_aliases(self) -> None:
        contract_path = self._approve()
        setup = json.loads(
            (self.bundle / "setup-render.json").read_text(encoding="utf-8")
        )
        contract = json.loads(contract_path.read_text(encoding="utf-8"))
        cases = (
            ("rig-setup-render-v1.schema.json", setup, "project_id", "CON"),
            ("setup-golden-v1.schema.json", contract, "project_id", "nul.txt"),
            ("setup-golden-v1.schema.json", contract, "project_id", "trailing."),
        )
        for schema_name, document, field, token in cases:
            with self.subTest(token):
                changed = dict(document)
                changed[field] = token
                schema = json.loads(
                    (ROOT / "schemas" / schema_name).read_text(encoding="utf-8")
                )
                self.assertFalse(Draft202012Validator(schema).is_valid(changed))
                with self.assertRaises(LayerManifestError):
                    require_safe_token(token, field)


if __name__ == "__main__":
    unittest.main()
