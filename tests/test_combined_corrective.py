"""Sequential projection is bounded and local offsets reconstruct each pose."""
from copy import deepcopy
import unittest
from tests.test_partition_mesh import fixture
from autospine_workbench.asset.joints.partition_mesh import build_region
from autospine_workbench.asset.joints.combined_corrective import sample,analyze,POSES
from autospine_workbench.asset.joints.distal_corrective import prepare,sample as distal_sample


class CombinedCorrectiveTests(unittest.TestCase):
    def test_setup_distal_equivalence_and_all_pose_reconstruction(self):
        args=fixture();row=build_region(*args);context=prepare(row,args[-1]['bones']);before=deepcopy(context)
        for a,b in POSES:
            result=sample(context,a,b)
            self.assertLess(result['qa']['offset_reconstruction_error'],1e-7)
            self.assertLess(result['qa']['main_fixed_vertex_error'],1e-7)
            if a==0:self.assertEqual(result['offsets'],distal_sample(context,b)['offsets'])
        self.assertEqual(context,before)
        result=analyze(row,args[-1]['bones'])
        self.assertEqual(result['poses'][0],result['poses'][-1])
        self.assertEqual(result,analyze(row,args[-1]['bones']))

    def test_invalid_pose(self):
        args=fixture();context=prepare(build_region(*args),args[-1]['bones'])
        with self.assertRaisesRegex(ValueError,'pose_invalid'):sample(context,17,25)
