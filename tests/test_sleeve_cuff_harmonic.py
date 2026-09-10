from copy import deepcopy
import math
import unittest
from autospine_workbench.asset.planning.sleeve_cuff_harmonic import reweight
from autospine_workbench.asset.joints.mesh_weights import _deform


class CuffHarmonicTests(unittest.TestCase):
    def fixture(self):
        points=[[0.,0.],[1.,0.],[0.,1.],[1.,1.],[2.,0.],[2.,1.]]
        triangles=[[0,1,2],[1,3,2],[1,4,3],[4,5,3]]
        roles=[{'role':r} for r in ('unknown','cuff','hand','hand')]
        bones=[dict(id=b,head_xy=[0.,0.],world_rotation_degrees=0.) for b in ('forearm','hand')]
        weights=[[dict(bone_id='forearm' if i<3 else 'hand',weight=1.,local_xy=p[:])] for i,p in enumerate(points)]
        return points,weights,triangles,roles,bones

    def test_only_shared_cuff_hand_changes_unknown_and_hand_interiors_pinned(self):
        args=self.fixture();before=deepcopy(args)
        weights,evidence=reweight(*args)
        self.assertEqual(evidence['vertices'],[3])
        self.assertEqual(args,before)
        for i in (0,1,2,4,5):self.assertEqual(weights[i],args[1][i])
        self.assertEqual({w['bone_id'] for w in weights[3]},{'forearm','hand'})
        self.assertAlmostEqual(sum(w['weight'] for w in weights[3]),1.)
        actual=_deform(weights,{b['id']:([0.,0.],0.) for b in args[4]})
        self.assertLess(max(math.dist(a,b) for a,b in zip(actual,args[0])),1e-12)
        self.assertEqual(reweight(*args),(weights,evidence))

    def test_uniform_scale_and_translation_keep_weight_values(self):
        args=self.fixture();weights,_=reweight(*args)
        points,_,triangles,roles,bones=deepcopy(args)
        points=[[x*7+53,y*7-21] for x,y in points]
        updated,_=reweight(points,args[1],triangles,roles,bones)
        for a,b in zip(weights[3],updated[3]):
            self.assertEqual(a['bone_id'],b['bone_id']);self.assertAlmostEqual(a['weight'],b['weight'],places=14)

    def test_missing_assignments_and_unknown_bone_fail(self):
        args=list(self.fixture());args[3]=args[3][:-1]
        with self.assertRaisesRegex(ValueError,'inventory'):reweight(*args)
        args=list(self.fixture());args[4]=args[4][:-1]
        with self.assertRaisesRegex(ValueError,'bone'):reweight(*args)

    def test_unlabeled_hand_cloth_boundary_is_not_changed_by_default(self):
        args=list(self.fixture());args[3][1]={'role':'hanging_cloth'}
        result,evidence=reweight(*args)
        self.assertEqual(result,args[1]);self.assertEqual(evidence['vertices'],[])
        _,trial=reweight(*args,include_uncuffed=True)
        self.assertEqual(trial['vertices'],[3])
