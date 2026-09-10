import copy
import unittest

from autospine_workbench.targets.spine43.inspection_pose import freeze
from autospine_workbench.targets.spine43.continuous_pose import world


class InspectionPoseTests(unittest.TestCase):
    def doc(self):
        return dict(bones=[dict(name='root', x=0, y=0, rotation=0)],
                    skins=[dict(attachments={'part': {'part': dict(vertices=[1, 0, 10, 0, 1])}})],
                    animations={'motion': dict(bones={'root': dict(rotate=[dict(time=0, value=0), dict(time=2, value=90)])},
                        attachments={'default': {'part': {'part': dict(deform=[dict(time=0, vertices=[0, 0]), dict(time=2, vertices=[2, 4])])}}})})

    def test_fractional_pose_held_and_source_unchanged(self):
        doc = self.doc(); original = copy.deepcopy(doc)
        result, error = freeze(doc, 'motion', .4765625)
        self.assertEqual(doc, original)
        self.assertEqual(error, 0)
        self.assertEqual(world(result, 0), world(result, 1))
        self.assertEqual(world(result, 0), world(doc, .4765625))

    def test_curved_and_unsupported_timeline_rejected(self):
        doc = self.doc(); doc['animations']['motion']['bones']['root']['rotate'][0]['curve'] = 'stepped'
        with self.assertRaisesRegex(ValueError, 'unsupported_keys'):
            freeze(doc, 'motion', .5)
        doc = self.doc(); doc['animations']['motion']['slots'] = {}
        with self.assertRaisesRegex(ValueError, 'unsupported_timeline'):
            freeze(doc, 'motion', .5)

    def test_outside_keys_rejected(self):
        with self.assertRaisesRegex(ValueError, 'unsupported_keys'):
            freeze(self.doc(), 'motion', 3)
