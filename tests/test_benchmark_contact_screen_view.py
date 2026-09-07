"""Screen summaries add diagnosis while retaining all original raster evidence."""
from copy import deepcopy
import unittest

from tests.test_benchmark_contact_probe_view import fixture, Tags
from autospine_workbench.resolved_project import canonical_sha256
from autospine_workbench.benchmark.contact_probe_view import render_contact_probe
from autospine_workbench.benchmark.contact_screen import build_contact_screen
from autospine_workbench.benchmark.contact_screen_view import render_contact_screen


class ContactScreenViewTests(unittest.TestCase):
    def test_summary_is_before_composite_and_preserves_original_evidence(self):
        candidate, probe, composite, images = fixture()
        screen = build_contact_screen(candidate, probe)
        before = deepcopy((candidate, probe, screen))
        original = render_contact_probe(candidate, probe, composite, images)
        page = render_contact_screen(candidate, probe, screen, composite, images)
        self.assertEqual(before, (candidate, probe, screen))
        prefix, _, suffix = original.partition("</h1>")
        self.assertTrue(page.startswith(prefix + "</h1>"))
        self.assertTrue(page.endswith(suffix))
        self.assertLess(page.index('id="contact-screen"'), page.index('<img class="composite'))
        self.assertIn("需复核", page)
        self.assertIn("肩部与踝部不适用髋部阈值", page)
        self.assertIn("局部接触候选不代表批准", page)
        self.assertEqual(page.count('class="contact-point"'), original.count('class="contact-point"'))
        self.assertFalse(any(tag in ("script", "input", "form") for tag, _ in Tags(page).tags))

    def test_no_contact_remains_empty(self):
        candidate, probe, composite, images = fixture(gap=True)
        screen = build_contact_screen(candidate, probe)
        page = render_contact_screen(candidate, probe, screen, composite, images)
        self.assertIn("接触证据总数 0", page)
        self.assertNotIn('class="contact-point"', page)

    def test_source_binding_and_screen_tampering_rejected(self):
        candidate, probe, composite, images = fixture()
        screen = build_contact_screen(candidate, probe)
        for field, value in (("authority", "human"), ("candidate_sha256", "0"*64),
                             ("probe_sha256", "0"*64), ("diagnostic_only", False),
                             ("summary", {"total": 99})):
            changed = deepcopy(screen); changed[field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                render_contact_screen(candidate, probe, changed, composite, images)
        with self.assertRaises(ValueError):
            render_contact_screen(candidate, probe, screen, composite+b"tamper", images)

    def test_untrusted_layer_name_is_escaped_in_summary_and_evidence(self):
        candidate, probe, composite, images = fixture()
        candidate["layers"][0]["name"] = '</summary><img src=x onerror="oops">'
        probe["candidate_sha256"] = canonical_sha256(candidate)
        screen = build_contact_screen(candidate, probe)
        page = render_contact_screen(candidate, probe, screen, composite, images)
        self.assertIn("&lt;/summary&gt;", page)
        self.assertFalse(any("onerror" in attrs for _, attrs in Tags(page).tags))


if __name__ == "__main__":
    unittest.main()
