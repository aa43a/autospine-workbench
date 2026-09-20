from types import SimpleNamespace
import unittest
from autospine_workbench.targets.character43.hand_depth_observation import observe


class HandDepthTests(unittest.TestCase):
    def test_declared_names_direct_parent_and_no_fabricated_missing_hand(self):
        for prefix in ('','mixamorig:'):
            wrist=prefix+'LeftHand'; knuckle=wrist+'Middle1'
            sampler=SimpleNamespace(mapping={'map_id':'mixamo-declared-body-v1'},
                roles={'humanoid.arm.lower.left':{'aim':{'joint_name':wrist}}},
                indices={wrist:0,knuckle:1},bvh=SimpleNamespace(joints=[None,SimpleNamespace(parent_index=0)]),
                joint_depths=lambda _: {wrist:.1,knuckle:.2})
            result=observe(sampler,0)
            self.assertEqual(result['segments'],{'hand_l':(.1,.2)})
            self.assertFalse(result['selected'])
            sampler.bvh.joints[1].parent_index=2
            self.assertEqual(observe(sampler,0)['segments'],{})
            del sampler.indices[knuckle]
            self.assertEqual(observe(sampler,0)['segments'],{})


if __name__=='__main__': unittest.main()
