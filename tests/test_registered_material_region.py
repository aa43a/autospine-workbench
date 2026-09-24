from copy import deepcopy
import unittest
from test_material_region_candidate import fixture
from autospine_workbench.targets.character43.registered_material_region import build


class RegisteredMaterialTests(unittest.TestCase):
    def test_only_selected_replacement_uvs_change(self):
        doc, plan = fixture(); before = deepcopy(doc)
        result, report = build(doc, plan, 'alternate', [.5, 0, 0, .5, .25, .25])
        key = report['replacement_slot']
        replacement = result['skins'][0]['attachments'][key][key]
        self.assertEqual(replacement['uvs'][:6], [.25, .25, .75, .25, .25, .75])
        self.assertEqual(replacement['vertices'], before['skins'][0]['attachments']['arm']['arm']['vertices'])
        original = report['original_region_slot']
        self.assertEqual(result['skins'][0]['attachments'][original][original]['uvs'],
                         before['skins'][0]['attachments']['arm']['arm']['uvs'])
        self.assertEqual(doc, before)
        self.assertFalse(report['production_authorized'])

    def test_rejects_reflection_and_out_of_texture_registration(self):
        doc, plan = fixture()
        for transform in ([-1, 0, 0, 1, 1, 0], [0, 0, 0, 1, 0, 0], [1, 0, 0, 1, 2, 0]):
            with self.assertRaises(ValueError):
                build(doc, plan, 'alternate', transform)
