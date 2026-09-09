from copy import deepcopy
import math
import unittest
from autospine_workbench.asset.planning.component_axial_solver import solve


class AxialSolverTests(unittest.TestCase):
    def test_candidate_source_binding_replay_and_no_weight_mutation(self):
        from tests.test_component_weight_transition import limb_fixture
        from autospine_workbench.asset.planning.component_mesh import build as mesh_build
        from autospine_workbench.asset.planning.component_weight_transition import build as transition
        from autospine_workbench.asset.planning.component_local_correction import build as correction
        from autospine_workbench.asset.planning.component_axial_correction import build
        from autospine_workbench.asset.planning.component_distal_guard import gate
        from autospine_workbench.resolved_project import canonical_sha256
        args=limb_fixture(); weights=transition(mesh_build(*args),args[1],args[0]); poses=correction(weights,args[1])
        source=dict(schema='autospine.component-distal-guard/v1', project_id=weights['project_id'],
                    skeleton_sha256=canonical_sha256(args[1]), records=weights['records'], rows=poses['rows'],
                    authority='none', production_authorized=False)
        original=deepcopy(source);result=build(source,args[1])
        self.assertEqual(result,build(source,args[1]));self.assertEqual(source,original)
        self.assertEqual(result['records'],source['records'])
        for row in result['evidence']:self.assertEqual(gate(row['before'],row['after'])[0],[])
        source['skeleton_sha256']='0'*64
        with self.assertRaises(ValueError):build(source,args[1])

    def fixture(self):
        mesh = dict(vertices_xy=[[-2.,-12.],[2.,-12.],[2.,12.],[-2.,12.]], triangles=[[0,1,2],[0,2,3]])
        points = [[x*.1,y] for x,y in mesh['vertices_xy']]
        bones = [dict(head_xy=[-20.,0.],tail_xy=[-10.,0.]), dict(head_xy=[-10.,0.],tail_xy=[0.,0.]), dict(head_xy=[0.,0.],tail_xy=[1.,0.])]
        return mesh,points,bones

    def test_wide_support_budget_and_transform_equivariance(self):
        mesh,points,bones = self.fixture(); original = deepcopy((mesh,points,bones))
        result,info = solve(mesh,points,points,bones,2)
        self.assertEqual(info['added_transverse_vertices'],4)
        self.assertNotEqual(result,points)
        self.assertEqual(original,(mesh,points,bones))
        for actual,start in zip(result,points): self.assertLessEqual(math.dist(actual,start),info['budget']+1e-9)
        for scale,angle,mirror in [(.25,37,1),(4,91,-1)]:
            a = math.radians(angle)
            def transform(p):
                x,y=p[0]*mirror,p[1]
                return [300+scale*(x*math.cos(a)-y*math.sin(a)),100+scale*(x*math.sin(a)+y*math.cos(a))]
            changed=deepcopy(mesh);changed['vertices_xy']=list(map(transform,mesh['vertices_xy']))
            chain=[dict(head_xy=transform(b['head_xy']),tail_xy=transform(b['tail_xy'])) for b in bones]
            p=list(map(transform,points)); got,evidence=solve(changed,p,p,chain,2)
            self.assertEqual(evidence['free_vertices'],info['free_vertices'])
            for actual,expected in zip(got,map(transform,result)): self.assertLess(math.dist(actual,expected),1e-7)

    def test_outside_axial_band_stays_fixed_and_non_distal_noop(self):
        mesh,points,bones=self.fixture()
        mesh['vertices_xy']=[[x+30,y] for x,y in mesh['vertices_xy']]
        moved,evidence=solve(mesh,points,points,bones,2)
        self.assertEqual(evidence['free_vertices'],[]);self.assertEqual(moved,points)
        self.assertEqual(solve(mesh,points,points,bones,1)[0],points)
