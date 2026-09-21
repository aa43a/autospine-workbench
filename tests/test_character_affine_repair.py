from copy import deepcopy
from unittest.mock import patch
import unittest
from autospine_workbench.targets.character43.affine_area_repair import repair
from autospine_workbench.targets.character43.affine_pose import sample


def fixture():
    return dict(bones=[dict(name='a', x=0, y=0, rotation=30),
                       dict(name='b', parent='a', x=10, y=0, rotation=0)],
                animations={'walk': {'bones': {'a': {'scale': [dict(time=0, x=1, y=1),
                                                               dict(time=1, x=.4, y=1)]}}}},
                skins=[dict(attachments={'mesh': {'mesh': dict(triangles=[0, 1, 2],
                    vertices=[1, 0, 0, 0, 1, 2, 0, 1, 0, .5, 1, -9, 0, .5,
                              2, 0, 0, 1, .5, 1, -10, 1, .5])}})])


class AffineRepairTests(unittest.TestCase):
    def test_progress_does_not_change_candidate_or_report(self):
        events=[]
        with patch('autospine_workbench.targets.character43.affine_area_repair.project',side_effect=lambda c,p:p):
            expected=repair(fixture(),'walk',samples=3)
            actual=repair(fixture(),'walk',samples=3,progress=events.append)
        self.assertEqual(expected,actual)
        self.assertEqual(events[0],dict(stage='sample_geometry',sample_count=3))
        self.assertEqual(events[-1]['stage'],'attachment_complete')
        self.assertEqual(events[-1]['unresolved_samples'],1)

    def test_inverse_affine_offsets_reconstruct_world_correction(self):
        source = fixture(); before = deepcopy(source)
        def translated(context, points):
            return [[p[0]+(.1 if free else 0), p[1]+(.2 if free else 0)]
                    for p, free in zip(points, context['free'])]
        with patch('autospine_workbench.targets.character43.affine_area_repair.project', translated):
            result, report = repair(source, 'walk', samples=3)
        self.assertEqual(source, before)
        old = sample(source, 'walk', 1)[0]['mesh']; new = sample(result, 'walk', 1)[0]['mesh']
        self.assertEqual(old[0], new[0])
        for i in (1, 2):
            self.assertAlmostEqual(new[i][0]-old[i][0], .1)
            self.assertAlmostEqual(new[i][1]-old[i][1], .2)
        self.assertFalse(report['selected'])

    def test_moving_fixed_vertex_is_rejected(self):
        def bad(context, points):
            return [[p[0]+.1, p[1]] for p in points]
        with patch('autospine_workbench.targets.character43.affine_area_repair.project', bad):
            with self.assertRaisesRegex(ValueError, 'budget'):
                repair(fixture(), 'walk', samples=3)

    def test_existing_deform_is_not_overwritten(self):
        doc = fixture(); doc['animations']['walk']['attachments'] = {'default': {}}
        with self.assertRaisesRegex(ValueError, 'existing_deform'):
            repair(doc, 'walk')

    def test_unconverged_projection_is_reported_without_approval(self):
        with patch('autospine_workbench.targets.character43.affine_area_repair.project',
                   side_effect=lambda context, points: points):
            _, report = repair(fixture(), 'walk', samples=3)
        row = report['records'][0]
        self.assertEqual(row['area_status'], 'needs_review')
        self.assertEqual(row['unresolved_area_samples'][0]['time'], 1)
        self.assertAlmostEqual(row['unresolved_area_samples'][0]['min_area_ratio'], .4)
        self.assertFalse(report['selected'])
