from copy import deepcopy
import unittest

from test_torso_projection import fixture, observations
from autospine_workbench.targets.character43.affine_pose import sample
from autospine_workbench.targets.character43.torso_projection_candidate import build
from autospine_workbench.targets.character43.torso_projection_source import shapes
from autospine_workbench.targets.character43.torso_warp_depth_plane import WarpedPlane


class Sampler:
    def torso_anchors(self, tick):
        return dict(upperarm_l=.2, upperarm_r=-.2, pelvis=0.)


class WarpedPlaneTests(unittest.TestCase):
    def setUp(self):
        doc=fixture()
        doc['bones'].append(dict(name='pelvis', parent='root', x=0, y=-2, rotation=0))
        for name in ('upperarm_l','upperarm_r','pelvis'):
            index=next(i for i,b in enumerate(doc['bones']) if b['name']==name)
            doc['skins'][0]['attachments'][name]={name:dict(
                vertices=[1,index,0,0,1,1,index,.1,0,1,1,index,0,.1,1],triangles=[0,1,2])}
        self.source=shapes([observations(0),observations(50)],[0,1])
        self.doc,self.receipt=build(doc,'move',self.source,samples=3)
        self.receipt['applied']=True

    def test_virtual_anchors_match_independently_sampled_baked_marker_vertices(self):
        plane=WarpedPlane(self.receipt,self.source)
        for time in (0,1):
            result=plane(self.doc,'move',time,Sampler(),time*1000000)
            rendered=sample(self.doc,'move',time)[0]
            for name,anchor in result['anchors'].items():
                for actual,expected in zip(anchor['xy'],rendered[name][0]):
                    self.assertAlmostEqual(actual,expected)
                a,b,c=result['coefficients'];x,y=rendered[name][0]
                self.assertAlmostEqual(a*x+b*y+c,anchor['depth'])
        self.assertFalse(result['selected'])

    def test_midpoint_and_mismatched_receipt_do_not_use_ideal_warp(self):
        with self.assertRaisesRegex(ValueError,'between_bake_source_keys'):
            WarpedPlane(self.receipt,self.source)(self.doc,'move',.5,Sampler(),500000)
        altered=deepcopy(self.source);altered['records'][1]['shear']=.1
        with self.assertRaisesRegex(ValueError,'source_mismatch'):
            WarpedPlane(self.receipt,altered)


if __name__=='__main__':unittest.main()
