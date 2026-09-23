import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from autospine_workbench.kimodo_soma77 import SOMA77_INDEX_BY_NAME as INDEX
from autospine_workbench.targets.character43.source_hand_axis import extract


class HandAxisTests(unittest.TestCase):
    def run_observation(self,degenerate=False,wrong_wrist=False):
        with tempfile.TemporaryDirectory() as folder:
            mapping=dict(basis=dict(screen_x='+X',screen_y='-Y',depth='+Z'),bones=[
                dict(role='humanoid.arm.lower.'+s,aim_joint_name=s.title()+'Hand') for s in ('left','right')])
            if wrong_wrist:mapping['bones'][0]['aim_joint_name']='RightHand'
            Path(folder,'map.json').write_text(json.dumps(mapping))
            points=[[0.,0.,0.] for _ in range(77)]
            for side in ('Left','Right'):points[INDEX[side+'HandMiddle1']]=[3.,4.,12.]
            if degenerate:points[INDEX['LeftHandMiddle1']]=[0.,0.,0.]
            decoded=SimpleNamespace(positions=[points,points],raw_npz_sha256='raw',source_sha256='source',array_inventory_sha256='arrays')
            prefix='autospine_workbench.targets.character43.kimodo_hand_axis.'
            with patch(prefix+'require_kimodo_npz_map'),patch(prefix+'decode_kimodo_npz',return_value=decoded), \
                 patch(prefix+'validate_kimodo_consistency',return_value=decoded),patch(prefix+'kimodo_frame_ticks',return_value=[0,100000]):
                return extract(SimpleNamespace(source_kind='kimodo_npz',path=Path(folder),kimodo_source={},raw_npz=b'raw'))

    def test_basis_time_and_source_identity_preserved(self):
        r=self.run_observation()
        self.assertEqual(r['vectors']['humanoid.arm.hand.left'],[(3.,-4.,12.)]*2)
        self.assertEqual(r['times'],[0,.1])
        self.assertEqual(r['identity']['raw_npz_sha256'],'raw')
        self.assertFalse(r['selected'])

    def test_degenerate_or_wrong_wrist_not_inferred(self):
        with self.assertRaisesRegex(ValueError,'degenerate'):self.run_observation(degenerate=True)
        with self.assertRaisesRegex(ValueError,'undeclared'):self.run_observation(wrong_wrist=True)
