from copy import deepcopy
import unittest
from autospine_workbench.targets.character43.sleeve_depth_intervals import mix


class SleeveDepthIntervalTests(unittest.TestCase):
    def setUp(self):
        self.doc=dict(bones=[dict(name='forearm_r',length=1),dict(name='cloth',parent='forearm_r')])
        self.mesh=dict(type='mesh',uvs=[0,0],triangles=[],vertices=[2,0,.5,0,.5,1,2,3,.5])
        self.helpers={'cloth':'forearm_r'}
        self.planes={'cloth':dict(coefficients=[.1,.2,0])}
        self.transforms={'cloth':(1,0,0,1,0,0)}
        self.segments={'forearm_r':(0,.2)}

    def build(self,**kw):
        return mix(self.doc,self.mesh,self.segments,self.helpers,self.planes,self.transforms,**kw)

    def test_every_influence_contributes_and_deform_is_applied_in_helper_local_space(self):
        before=deepcopy((self.mesh,self.doc))
        self.assertAlmostEqual(self.build()['intervals'][0][0],.45)
        # Body offsets retain the existing body model; helper offset changes its plane point.
        result=self.build(offsets=[0,0,1,-1])
        self.assertAlmostEqual(result['intervals'][0][0],.4)
        self.assertEqual(result['modeled_vertices'],[0])
        self.assertEqual((self.mesh,self.doc),before)

    def test_unknown_helper_or_body_remains_unknown(self):
        self.planes={};self.assertEqual(self.build()['intervals'],[None])
        self.planes={'cloth':dict(coefficients=[.1,.2,0])};self.segments={}
        self.assertEqual(self.build()['intervals'],[None])

    def test_all_helper_and_all_body_vertices(self):
        self.mesh['vertices']=[1,1,2,3,1]
        self.assertAlmostEqual(self.build()['intervals'][0][0],.8)
        self.mesh['vertices']=[1,0,.5,0,1]
        result=self.build();self.assertEqual(result['intervals'],[[.1,.1]])
        self.assertEqual(result['modeled_vertices'],[])

    def test_invalid_normalization_and_deform_do_not_get_repaired(self):
        self.mesh['vertices'][-1]=.4
        self.assertEqual(self.build()['intervals'],[None])
        self.mesh['vertices'][-1]=.5
        with self.assertRaisesRegex(ValueError,'deform_length'):self.build(offsets=[0,0])
        with self.assertRaisesRegex(ValueError,'nonfinite'):self.build(offsets=[0,0,float('nan'),0])

    def test_world_transform_is_used_before_plane_evaluation(self):
        self.transforms['cloth']=(0,-1,1,0,10,20)
        self.assertAlmostEqual(self.build()['intervals'][0][0],2.6)


if __name__=='__main__':unittest.main()
