from copy import deepcopy
import unittest

import test_torso_warp_depth_plane as fixture_module
from autospine_workbench.targets.character43.affine_pose import sample
from autospine_workbench.targets.character43.torso_baked_depth_plane import BakedWarpPlane
from autospine_workbench.targets.character43.torso_projection_candidate import build


class BakedPlaneTests(unittest.TestCase):
    def setUp(self):
        fixture=fixture_module.WarpedPlaneTests();fixture.setUp()
        self.doc,self.receipt,self.source=fixture.doc,fixture.receipt,fixture.source

    def test_midpoints_match_actual_baked_marker_vertices(self):
        plane=BakedWarpPlane(self.doc,'move',self.receipt,self.source)
        for t in (.125,.25,.499,.75,.875):
            result=plane(self.doc,'move',t,fixture_module.Sampler(),t*1e6)
            rendered=sample(self.doc,'move',t)[0]
            for name,anchor in result['anchors'].items():
                for a,b in zip(anchor['xy'],rendered[name][0]): self.assertAlmostEqual(a,b)

    def test_schedule_and_candidate_mismatch_fail(self):
        plane=BakedWarpPlane(self.doc,'move',self.receipt,self.source)
        with self.assertRaisesRegex(ValueError,'candidate_mismatch'):
            plane(deepcopy(self.doc),'move',.5,fixture_module.Sampler(),500000)
        slot=self.receipt['changed_slots'][0]
        self.doc['animations']['move']['attachments']['default'][slot][slot]['deform'][0]['curve']='stepped'
        with self.assertRaisesRegex(ValueError,'schedule_unsupported'):
            BakedWarpPlane(self.doc,'move',self.receipt,self.source)

    def test_rotating_parent_uses_local_offsets_not_world_lerp(self):
        doc=deepcopy(self.doc)
        doc['animations']['move'].pop('attachments')
        doc['animations']['move']['bones']['root']['rotate']=[dict(time=0,value=0),dict(time=1,value=110)]
        candidate,receipt=build(doc,'move',self.source,samples=3);receipt['applied']=True
        plane=BakedWarpPlane(candidate,'move',receipt,self.source)
        for t in (.25,.75):
            result=plane(candidate,'move',t,fixture_module.Sampler(),t*1e6)
            rendered=sample(candidate,'move',t)[0]
            for name,anchor in result['anchors'].items():
                for a,b in zip(anchor['xy'],rendered[name][0]): self.assertAlmostEqual(a,b)


if __name__=='__main__':unittest.main()
