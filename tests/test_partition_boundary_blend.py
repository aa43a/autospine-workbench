from copy import deepcopy
import unittest
from test_partition_rebind import fixture
from autospine_workbench.targets.character43.partition_rebind import apply
from autospine_workbench.targets.character43.partition_boundary_blend import blend
from autospine_workbench.targets.character43.affine_pose import sample


class BoundaryTests(unittest.TestCase):
    def test_boundary_coincidence_without_changing_unselected_vertices(self):
        doc,plan=fixture();setup=sample(doc,'walk',0)[0]['mesh']
        rigid,rest,partition=apply(doc,plan,setup);before=deepcopy(rigid)
        result,report=blend(rigid,'walk','mesh',partition,rest,[0,1])
        self.assertEqual(rigid,before);self.assertEqual(result['skins'],rigid['skins'])
        self.assertEqual(result['animations']['walk']['bones'],rigid['animations']['walk']['bones'])
        for time in (0,1):
            old=sample(rigid,'walk',time)[0]['mesh'];new=sample(result,'walk',time)[0]['mesh']
            for a,b in zip(old[:4],new[:4]):
                for x,y in zip(a,b):self.assertAlmostEqual(x,y)
            for a,b in partition['boundary_pairs']:
                for x,y in zip(new[a],new[b]):self.assertAlmostEqual(x,y)
        self.assertFalse(report['selected'])

    def test_missing_boundary_rejected(self):
        doc,plan=fixture();setup=sample(doc,'walk',0)[0]['mesh']
        rigid,rest,partition=apply(doc,plan,setup);partition['boundary_pairs']=[]
        with self.assertRaisesRegex(ValueError,'missing'):blend(rigid,'walk','mesh',partition,rest,[0,1])
