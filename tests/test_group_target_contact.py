from copy import deepcopy
import unittest
from test_affine_leg_ik import fixture
from autospine_workbench.targets.character43.group_target_contact import constrain


class TargetContactTests(unittest.TestCase):
    def test_target_endpoint_preserved_under_scaled_parent(self):
        base = fixture()
        bones = [base['bones'][0]]
        for side in ('l', 'r'):
            names = {'upper': 'thigh_'+side, 'lower': 'calf_'+side, 'tip': 'foot_'+side}
            for bone in base['bones'][1:]:
                row = deepcopy(bone)
                row['name'] = names[row['name']]
                row['parent'] = names.get(row['parent'], row['parent'])
                bones.append(row)
        tracks = {name: dict(rotate=[dict(time=t, value=0) for t in (0, 1)])
                  for name in ('thigh_l', 'calf_l', 'thigh_r', 'calf_r')}
        source = dict(bones=bones, animations={'external-motion': dict(bones=tracks)})
        target = deepcopy(source)
        target['animations']['external-motion']['bones']['thigh_l']['rotate'][1]['value'] = 13
        before = deepcopy(source)
        result, report = constrain(source, target, [0, 1])
        self.assertEqual(source, before)
        self.assertEqual(report['failures'], 0)
        self.assertLess(report['maximum_endpoint_error_px'], 1e-7)
        self.assertFalse(report['selected'])
