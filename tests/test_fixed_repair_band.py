from copy import deepcopy
import unittest
from test_area_preservation_sampling import fixture
from autospine_workbench.targets.character43.fixed_repair_band import collect
from autospine_workbench.targets.character43.projected_area_sampling import inspect


class FixedBandTests(unittest.TestCase):
    def test_whole_clip_union_does_not_disappear_when_pose_recovers(self):
        good=[[0,0],[2,0],[1,1],[10,0],[12,0],[11,1]]
        bad=deepcopy(good);bad[2][1]=.1
        triangles=[[0,1,2],[3,4,5]]
        self.assertEqual(collect([{'m':bad},{'m':good}],'m',triangles,[[1,1],[1,1]],()),[0])
        self.assertEqual(collect([{'m':good}],'m',triangles,[[1,1]],()),[])

    def test_independent_verifier_rejects_unjustified_expansion(self):
        source=fixture()
        with self.assertRaisesRegex(ValueError,'source_mismatch'):
            inspect(source,'move',['mesh'],preservation_source=source,repair_support={'mesh':[]},fixed_repair_bands={'mesh':[0]})
        report=inspect(source,'move',['mesh'],preservation_source=source,
                       repair_support={'mesh':[2]},fixed_repair_bands={'mesh':[0]})
        self.assertEqual(report['failures'],[])
        self.assertEqual(report['profile'],'fixed-band-key-and-midpoint-check-v1-experiment')
