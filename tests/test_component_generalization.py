from copy import deepcopy
import math
import unittest
from autospine_workbench.asset.planning.component_collar_solver import solve
from autospine_workbench.asset.planning.component_collar_keys import admission
from autospine_workbench.asset.planning.component_candidate_draft import prefill
from tests.test_component_weight_transition import limb_fixture


class ComponentGeneralizationTests(unittest.TestCase):
    def fixture(self,width=10,length=20):
        mesh=dict(vertices_xy=[[0.,0.],[width,0.],[width,10.],[0.,10.]],triangles=[[0,1,2],[0,2,3]])
        original=[[0.,0.],[width,0.],[width,1.],[0.,1.]]
        bones=[dict(head_xy=[width/2,5-length],tail_xy=[width/2,5]),dict(head_xy=[width/2,5],tail_xy=[width/2,5+length])]
        return mesh,original,bones

    def test_translation_rotation_mirror_scale_equivariance(self):
        mesh,original,bones=self.fixture();expected,info=solve(mesh,original,original,bones,1)
        for scale in (.25,1,4):
            for angle,mirror in [(0,1),(37,1),(91,-1)]:
                a=math.radians(angle)
                def transform(p):
                    x,y=p[0]*mirror,p[1]
                    return [300+scale*(x*math.cos(a)-y*math.sin(a)),-170+scale*(x*math.sin(a)+y*math.cos(a))]
                changed=deepcopy(mesh);changed['vertices_xy']=[transform(p) for p in mesh['vertices_xy']]
                points=[transform(p) for p in original]
                chain=[dict(head_xy=transform(b['head_xy']),tail_xy=transform(b['tail_xy'])) for b in bones]
                result,evidence=solve(changed,points,points,chain,1)
                self.assertEqual(evidence['free_vertices'],info['free_vertices'])
                for actual,target in zip(result,map(transform,expected)):
                    self.assertLess(math.dist(actual,target),1e-7)

    def test_proportions_never_escape_locality_or_budget(self):
        for width in (4,10,30):
            for length in (10,20,80):
                mesh,points,bones=self.fixture(width,length)
                moved,info=solve(mesh,points,points,bones,1)
                for i in range(4):
                    if i not in info['free_vertices']:self.assertEqual(moved[i],points[i])
                    else:self.assertLessEqual(math.dist(moved[i],points[i]),info['budget']+1e-9)

    def test_admission_rejects_regression_even_with_better_totals(self):
        def qa(inv=0,bad=()):return dict(inversions=inv,min_area_ratio=-1 if inv else (.4 if bad else 1),max_area_ratio=1,max_edge_stretch=1,bad_triangles=list(bad))
        before=[qa(2,[1,2]),qa()];after=[qa(),qa(1,[1])]
        ok,failures,inversions=admission(before,after)
        self.assertFalse(ok);self.assertEqual(failures,[.25]);self.assertEqual(inversions,[.25])

    def test_suggestion_draft_is_not_human_authority_and_preserves_existing(self):
        draft=limb_fixture()[2]
        suggestions=dict(sources=draft['sources'],authority='none',production_authorized=False,records=[])
        self.assertEqual(prefill(draft,suggestions),draft)
        suggestions['sources']={}
        with self.assertRaises(ValueError):prefill(draft,suggestions)
