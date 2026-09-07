"""Editor images come from exact P2 PNGs, never from atlas reconstruction."""
from copy import deepcopy
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import unittest

from tests import test_rig_commands as rig_commands
from autospine_workbench.automation.editor_import import EditorImportError, build_editor_files
from autospine_workbench.automation.region_preview import build_region_preview, verify_region_preview
from autospine_workbench.png_rgba import decode_rgba_png
from autospine_workbench.rig_bundle_integrity import verify_rig_bundle_directory


class EditorImportTests(unittest.TestCase):
    def setUp(self):
        fixture = rig_commands.RigCommandIntegrationTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.fixture = fixture
        self.state = fixture.fixture.state
        status, result = fixture._run(
            "compile-rig", "fixture-project", "--layer-manifest-sha256", fixture.manifest_sha,
            "--workspace", str(fixture.fixture.workspace), "--state-root", str(self.state),
        )
        self.assertEqual(status, 0, result)
        self.result = result
        self.rig_path = self.state / "builds/fixture-project/rig-ir" / result["rig_sha256"] / result["bundle_sha256"]

    def preview(self, version="4.3.26"):
        address = build_region_preview(
            self.state, "fixture-project", self.fixture.manifest_sha,
            self.result["rig_sha256"], self.result["bundle_sha256"], target_version=version,
        )
        return verify_region_preview(self.state, "fixture-project", address["bundle_sha256"],
                                     target_version=version)

    def changed_skeleton(self, bundle, mutate):
        files = bundle.files
        skeleton = json.loads(files["skeleton.json"])
        mutate(skeleton)
        files["skeleton.json"] = json.dumps(skeleton).encode()
        addresses = bundle.addresses
        addresses["skeleton_json_sha256"] = hashlib.sha256(files["skeleton.json"]).hexdigest()
        return replace(bundle, _items=tuple(sorted(files.items())), _addresses_json=json.dumps(addresses))

    def test_both_targets_include_exact_original_pngs_and_relative_editor_paths(self):
        verified_rig = verify_rig_bundle_directory(self.rig_path, expected_project_id="fixture-project")
        for version in ("4.2", "4.3.26"):
            with self.subTest(version=version):
                bundle = self.preview(version)
                original_files = bundle.files
                original_disk = {name: (bundle.path / name).read_bytes() for name in original_files}
                extras = build_editor_files(self.state, "fixture-project", bundle)
                self.assertEqual(extras, build_editor_files(self.state, "fixture-project", bundle))
                editor = json.loads(extras["editor/skeleton.json"])
                runtime = json.loads(original_files["skeleton.json"])
                expected = deepcopy(runtime)
                expected["skeleton"]["images"] = "./images/"
                self.assertEqual(editor, expected)
                self.assertEqual(editor["skeleton"]["spine"], version)
                expected_names = {"editor/skeleton.json", "editor/README.txt"}
                for attachment in verified_rig.rig["attachments"]:
                    name = f"editor/images/{attachment['id']}.png"
                    expected_names.add(name)
                    original = verified_rig.region_pngs[attachment["image_path"]]
                    self.assertEqual(extras[name], original)
                    self.assertEqual(decode_rgba_png(extras[name]).pixels, decode_rgba_png(original).pixels)
                    for skin in editor["skins"]:
                        image = skin["attachments"][attachment["slot"]][attachment["id"]]
                        self.assertEqual(image["path"], attachment["id"])
                        self.assertIn("editor/" + editor["skeleton"]["images"].removeprefix("./") + image["path"] + ".png", extras)
                self.assertEqual(set(extras), expected_names)
                self.assertEqual(bundle.files, original_files)
                self.assertEqual({name: (bundle.path / name).read_bytes() for name in original_files}, original_disk)
                self.assertIn("导入数据", extras["editor/README.txt"].decode("utf-8"))
                self.assertNotIn(str(self.state), extras["editor/README.txt"].decode("utf-8"))

    def test_missing_original_png_fails_instead_of_cropping_runtime_atlas(self):
        bundle = self.preview()
        verified = verify_rig_bundle_directory(self.rig_path)
        attachment = verified.rig["attachments"][0]
        path = self.rig_path / attachment["image_path"]
        path.unlink()
        self.assertTrue((bundle.path / "skeleton.png").exists())
        with self.assertRaises(EditorImportError):
            build_editor_files(self.state, "fixture-project", bundle)

    def test_changed_original_png_is_rejected_even_when_still_valid_png(self):
        bundle = self.preview()
        verified = verify_rig_bundle_directory(self.rig_path)
        path = self.rig_path / verified.rig["attachments"][0]["image_path"]
        from tests.png_helpers import write_rgba
        write_rgba(path, [[(255, 0, 0, 255)] * 20 for _ in range(20)])
        with self.assertRaises(EditorImportError):
            build_editor_files(self.state, "fixture-project", bundle)

    def test_mismatched_missing_and_unsafe_skeleton_paths_fail(self):
        bundle = self.preview()

        def first(document):
            return next(iter(next(iter(document["skins"][0]["attachments"].values())).values()))

        for key, value in (("path", "wrong-image"), ("path", "../escape"),
                           ("path", "CON"), ("type", "mesh"), ("width", 999)):
            invalid = self.changed_skeleton(bundle, lambda doc: first(doc).update({key: value}))
            with self.subTest(key=key, value=value), self.assertRaises(EditorImportError):
                build_editor_files(self.state, "fixture-project", invalid)
        invalid = self.changed_skeleton(bundle, lambda doc: doc.update(skins=[]))
        with self.assertRaises(EditorImportError):
            build_editor_files(self.state, "fixture-project", invalid)

    def test_source_binding_and_project_mismatch_are_rejected(self):
        bundle = self.preview()
        for project_id in ("other-project", "../escape"):
            with self.subTest(project_id=project_id), self.assertRaises(EditorImportError):
                build_editor_files(self.state, project_id, bundle)
        addresses = bundle.addresses
        addresses["source_addresses"]["layer_manifest_sha256"] = "f" * 64
        invalid = replace(bundle, _addresses_json=json.dumps(addresses))
        with self.assertRaises(EditorImportError):
            build_editor_files(self.state, "fixture-project", invalid)

    def test_changed_runtime_bytes_without_matching_address_fail_closed(self):
        bundle = self.preview()
        files = bundle.files
        files["skeleton.json"] += b" "
        invalid = replace(bundle, _items=tuple(sorted(files.items())))
        with self.assertRaises(EditorImportError) as caught:
            build_editor_files(self.state, "fixture-project", invalid)
        self.assertEqual(caught.exception.reason_code, "editor_import_preview_identity_mismatch")


if __name__ == "__main__":
    unittest.main()
