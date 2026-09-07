"""Offline contact overlays embed verified PNGs and never invent joint marks."""
from copy import deepcopy
import hashlib
from html.parser import HTMLParser
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from autospine_workbench.png_rgba import RgbaImage, encode_rgba_png
from autospine_workbench.resolved_project import canonical_sha256
from autospine_workbench.benchmark.contact_probe import build_contact_probe
from autospine_workbench.benchmark.contact_probe_view import render_contact_probe


def fixture(gap=False):
    raw = encode_rgba_png(RgbaImage(8, 8, bytes([10, 100, 200, 255]) * 64))
    composite = encode_rgba_png(RgbaImage(40, 40, bytes([255, 255, 255, 0]) * 1600))
    digest = hashlib.sha256(raw).hexdigest()
    layers = []
    for index, (name, x) in enumerate((("topwear", 2), ("handwear-l", 30 if gap else 4))):
        layers.append({"layer_id": f"layer-{index}", "name": name, "bbox": [x, 2, x+8, 10],
                       "image_sha256": digest, "image": {"sha256": digest, "byte_size": len(raw)},
                       "observed": {"empty": False}})
    candidate = {"schema": "autospine.benchmark-semantic-candidates/v1", "authority": "none",
                 "canvas": [40, 40], "coordinate_system": "psd_canvas", "layers": layers,
                 "composite_sha256": hashlib.sha256(composite).hexdigest()}
    images = {row["layer_id"]: raw for row in layers}
    return candidate, build_contact_probe(candidate, images), composite, images


class Tags(HTMLParser):
    def __init__(self, page):
        super().__init__(); self.tags = []; self.feed(page)

    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, dict(attrs)))


class ContactProbeViewTests(unittest.TestCase):
    def test_real_png_overlay_uses_canvas_offsets_and_contact_marker(self):
        args = fixture(); original = deepcopy(args[:2])
        page = render_contact_probe(*args); tags = Tags(page).tags
        self.assertEqual(args[:2], original)
        self.assertIn('viewBox="0 0 40 40"', page)
        self.assertIn('x="2" y="2" width="8" height="8"', page)
        self.assertIn('class="contact-point"', page)
        self.assertIn('class="contact-bbox"', page)
        self.assertIn("面积 48 px²", page)
        self.assertIn("左右未知", page)
        self.assertTrue(all(attrs.get("href", attrs.get("src", "")).startswith("data:image/png;base64,")
                            for tag, attrs in tags if tag in ("image", "img")))
        self.assertFalse(any(tag in ("script", "input", "form") for tag, _ in tags))

    def test_no_contact_does_not_fabricate_point(self):
        page = render_contact_probe(*fixture(gap=True))
        self.assertNotIn('class="contact-point"', page)
        self.assertNotIn('class="contact-bbox"', page)
        self.assertIn("未检测到接触", page)
        self.assertIn("间隙超过探测范围", page)

    def test_untrusted_name_and_reason_are_escaped(self):
        candidate, probe, composite, images = fixture()
        candidate["layers"][0]["name"] = '</summary><img src=x onerror="boom">'
        probe["candidate_sha256"] = canonical_sha256(candidate)
        probe["relations"][0]["reason_codes"].append("</p><script>boom</script>")
        page = render_contact_probe(candidate, probe, composite, images)
        self.assertIn("&lt;/summary&gt;", page)
        self.assertFalse(any(tag == "script" or "onerror" in attrs for tag, attrs in Tags(page).tags))

    def test_changed_images_or_probe_identity_fail(self):
        candidate, probe, composite, images = fixture()
        with self.assertRaises(ValueError): render_contact_probe(candidate, probe, composite+b"x", images)
        altered = dict(images); altered["layer-0"] = images["layer-0"][:-1] + b"x"
        with self.assertRaises(ValueError): render_contact_probe(candidate, probe, composite, altered)
        altered["layer-0"] += b"x"
        with self.assertRaises(ValueError): render_contact_probe(candidate, probe, composite, altered)
        probe["candidate_sha256"] = "0" * 64
        with self.assertRaises(ValueError): render_contact_probe(candidate, probe, composite, images)


if __name__ == "__main__":
    unittest.main()
