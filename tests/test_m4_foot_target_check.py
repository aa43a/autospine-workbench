import unittest

from m4_foot_target_check import temporal_check
from autospine_workbench.targets.character43.foot_orientation_fit import fit


class TemporalFootEvidenceTests(unittest.TestCase):
    def test_distinguishes_exact_keys_from_interpolation_failure(self):
        bones = [dict(name='root', x=0, y=0, rotation=0)]
        tracks = {}
        for side in ('l', 'r'):
            bones.extend([dict(name='calf_'+side, parent='root', x=0, y=0, rotation=0),
                          dict(name='foot_'+side, parent='calf_'+side, x=10, y=0, rotation=0)])
            tracks['calf_'+side] = {
                'rotate': [dict(time=0,value=0), dict(time=1,value=70)],
                'scale': [dict(time=0,x=1,y=1), dict(time=1,x=.4,y=1.2)]}
        doc = dict(bones=bones, animations={'external-motion': {'bones': tracks}})
        observed = dict(times=[0,1], tracks={'foot_l':[0,0], 'foot_r':[0,0]})
        old, report = fit(doc, 'external-motion', observed, temporal=False)
        self.assertLess(report['maximum_matrix_error'], 1e-10)
        old_check = temporal_check(old, observed)
        self.assertFalse(old_check['within_v2_tolerance'])
        self.assertGreater(old_check['worst']['time'], 0)
        self.assertLess(old_check['worst']['time'], 1)
        new, _ = fit(doc, 'external-motion', observed, temporal=True)
        new_check = temporal_check(new, observed)
        self.assertTrue(new_check['within_v2_tolerance'])
        self.assertGreater(new_check['samples'], 6)


if __name__ == '__main__':
    unittest.main()
