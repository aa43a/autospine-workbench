import unittest
from copy import deepcopy
from autospine_workbench.asset.planning.sleeve_unknown_coupling import analyze


class UnknownCouplingTests(unittest.TestCase):
    def test_shared_unknown_hand_influence_is_localized_without_reassigning(self):
        labels=[dict(triangle_id=0,role='unknown'),dict(triangle_id=1,role='hanging_cloth')]
        weights=[[dict(bone_id='h',weight=1)] for _ in range(4)]
        original=deepcopy(labels)
        result=analyze([[0,1,2],[1,3,2]],labels,weights,'h',[1])
        self.assertEqual([v['vertex_id'] for v in result['vertices']],[1,2])
        self.assertEqual(result['unknown_triangles'],[0])
        self.assertEqual(result['failed_triangle_roles'],{'hanging_cloth':1})
        self.assertEqual(labels,original)
        self.assertFalse(result['production_authorized'])
        self.assertFalse(analyze([[0,1,2],[1,3,2]],labels,weights,'other',[1])['vertices'])

    def test_inventory_and_nonfinite_influence_fail(self):
        labels=[dict(triangle_id=1,role='unknown')]
        with self.assertRaisesRegex(ValueError,'order'): analyze([[0,1,2]],labels,[[],[],[]],'h',[])
        labels=[dict(triangle_id=0,role='unknown'),dict(triangle_id=1,role='cuff')]
        with self.assertRaisesRegex(ValueError,'weight'):
            analyze([[0,1,2],[1,3,2]],labels,[[],[dict(bone_id='h',weight=float('nan'))],[],[]],'h',[])
