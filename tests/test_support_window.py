from copy import deepcopy
import math
import unittest
import numpy as np

from test_support_timeline import fixture
from autospine_workbench.targets.character43.affine_pose import matrices
from autospine_workbench.targets.character43.support_window_model import prepare, evaluate
from autospine_workbench.targets.character43.support_window_optimizer import optimize


class SupportWindowTests(unittest.TestCase):
    def test_model_matches_affine_fk_for_offsets_and_anisotropic_scale(self):
        doc, _ = fixture(); doc['bones'][1]['scaleX'] = .4
        doc['bones'][1]['scaleY'] = 1.1
        t = .5; values = np.asarray([[.01, -.02, .1, -.2, -.15, .05]])
        endpoints, axes = evaluate(prepare(doc, 'walk', [t]), values, 20)
        changed = deepcopy(doc); tracks = changed['animations']['walk']['bones']
        tracks['root']['translate'] = [dict(time=0, x=2*t/1.2+.2, y=-.4)]
        for name, angle in zip(('thigh_l','calf_l','thigh_r','calf_r'), values[0, 2:]):
            tracks[name] = {'rotate': [dict(time=0, value=math.degrees(angle))]}
        pose = matrices(changed, 'walk', t)
        for i, s in enumerate(('l', 'r')):
            np.testing.assert_allclose(endpoints[0, i], pose['foot_'+s][4:6], atol=1e-10)
            for j, n in enumerate(('thigh_', 'calf_')):
                m = pose[n+s]
                self.assertAlmostEqual(axes[0, i, j], math.atan2(m[2], m[0]))

    def test_zero_loss_window_keeps_original_and_fixed_endpoints(self):
        doc, _ = fixture(); doc['animations']['walk']['bones']['root']['translate'] = [dict(time=0,x=0,y=0)]
        pose = matrices(doc, 'walk', 0)
        anchors = [dict(limb='leg.'+side, start=0, end=2, target=pose['foot_'+s][4:6])
                   for side,s in (('left','l'),('right','r'))]
        rows = [dict(time=i/10, root_shift=[0,0], angles={n:0 for n in ('thigh_l','calf_l','thigh_r','calf_r')}) for i in range(5)]
        original = deepcopy(rows)
        output, report = optimize(doc, 'walk', rows, anchors, 20)
        self.assertEqual(rows, original)
        self.assertEqual(output, rows)
        self.assertEqual(report['status'], 'no_improving_window_found')

    def test_contact_transition_window_is_rejected(self):
        doc, _ = fixture()
        rows = [dict(time=i/10) for i in range(5)]
        with self.assertRaisesRegex(ValueError, 'constant_double_support'):
            optimize(doc, 'walk', rows, [], 20)
