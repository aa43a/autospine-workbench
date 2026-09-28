import unittest
from copy import deepcopy
from test_motion_depth_overlap import fixture
from autospine_workbench.targets.character43.motion_depth_overlap import Probe
from autospine_workbench.targets.character43.mesh_pair_depth import compare


class AmbiguitySourceTests(unittest.TestCase):
    def run_case(self,a,b,duplicate=False,tiled=False):
        doc,files=fixture()
        if duplicate:
            mesh=deepcopy(doc['skins'][0]['attachments']['a']['a'])
            doc['skins'][0]['attachments']['a']['a']=mesh
            mesh['vertices']*=2;mesh['uvs']*=2
            mesh['triangles']+= [v+4 for v in list(mesh['triangles'])]
        return compare(Probe(doc,files,'test',tiled=tiled,sparse=tiled),'a','b',0,a,b,pixelwise=True)

    def test_exact_near_contact_is_not_attributed_to_model_width(self):
        r=self.run_case([[0,0]]*4,[[.01,.01]]*4)['ambiguity_sources']
        self.assertEqual(r['separated_within_margin'],4)
        self.assertEqual(r['overlapping_intervals'],0)
        self.assertEqual(r['a_intrinsic_interval']+r['b_intrinsic_interval'],0)

    def test_wide_model_interval_is_not_multiple_surface_span(self):
        r=self.run_case([[0,1]]*4,[[.5,.5]]*4)['ambiguity_sources']
        self.assertEqual(r['a_intrinsic_interval'],4)
        self.assertEqual(r['a_multiple_surface_span'],0)
        self.assertEqual(r['overlapping_intervals'],4)

    def test_opposing_overlaid_triangles_preserve_depth_disagreement(self):
        values=[[1,1]]*4+[[-1,-1]]*4
        r=self.run_case(values,[[0,0]]*4,duplicate=True)['ambiguity_sources']
        self.assertEqual(r['a_multiple_surface_span'],4)
        self.assertEqual(r['a_intrinsic_interval'],0)
        tiled=self.run_case(values,[[0,0]]*4,duplicate=True,tiled=True)['ambiguity_sources']
        self.assertEqual(r,tiled)
