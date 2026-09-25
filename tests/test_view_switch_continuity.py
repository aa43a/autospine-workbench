from copy import deepcopy
import unittest

from test_view_pose_variant import ViewPoseVariantTests
from autospine_workbench.targets.character43.view_pose_variant import build
from autospine_workbench.targets.character43.view_switch_continuity import inspect


class ViewSwitchContinuityTests(unittest.TestCase):
    def candidate(self):
        document, request = ViewPoseVariantTests().fixture()
        result, report = build(document, request)
        return result, report['variant']

    def test_original_movement_does_not_become_switch_jump(self):
        doc, variant = self.candidate(); before = deepcopy(doc)
        report = inspect(doc, variant)
        self.assertEqual(doc, before)
        self.assertTrue(all(r['maximum_vertex_jump_px']<1e-6 for r in report['records']))
        self.assertGreater(report['maximum_uv_change'],0)
        self.assertEqual(report['material_status'],'requires_rendered_boundary_review')
        self.assertFalse(report['selected'])

    def test_same_time_variant_displacement_is_detected(self):
        doc, variant = self.candidate()
        keys=doc['animations']['move']['attachments']['default']['leg'][variant['variant_attachment']]['deform']
        for key in keys:
            key['vertices']=[v+3 if i%2==0 else v for i,v in enumerate(key['vertices'])]
        report=inspect(doc,variant)
        self.assertTrue(all(r['geometry_status']=='discontinuous' for r in report['records']))
        self.assertTrue(all(r['maximum_vertex_jump_px']>2 for r in report['records']))

    def test_different_topology_requires_correspondence(self):
        doc, variant = self.candidate()
        doc['skins'][0]['attachments']['leg'][variant['variant_attachment']]['triangles']=[0,2,1,0,3,2]
        report=inspect(doc,variant)
        self.assertTrue(all(r['geometry_status']=='correspondence_required' for r in report['records']))
        self.assertIsNone(report['records'][0]['maximum_vertex_jump_px'])
