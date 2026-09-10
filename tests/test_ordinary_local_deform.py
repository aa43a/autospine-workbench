"""Local corrections preserve hand/unknown pins and source bind data."""
from copy import deepcopy
import math
import unittest
from autospine_workbench.asset.planning.ordinary_local_deform import solve


def fixture(role='cuff'):
    setup=[[0.,0.],[10.,0.],[0.,10.],[30.,0.],[40.,0.],[30.,10.],[60.,0.]]
    mesh=dict(vertices_xy=setup,triangles=[[0,1,2],[3,4,5]],uvs=[[0.,0.]]*7,weights=['unchanged']*7)
    points=deepcopy(setup);points[2]=[0.,-1.]
    labels=[dict(triangle_id=0,role=role),dict(triangle_id=1,role='sleeve')]
    return mesh,points,labels


class OrdinaryLocalDeformTests(unittest.TestCase):
    def test_bounded_local_improvement_and_exact_source(self):
        args=fixture();before=deepcopy(args);result=solve(*args,5.)
        self.assertEqual(args,before);self.assertEqual(result,solve(*args,5.))
        self.assertTrue(result['selected']);self.assertEqual(result['selected_qa']['inversions'],0)
        self.assertLessEqual(result['max_trial_offset'],5.+1e-9)
        self.assertEqual(result['free_vertices'],[0,1,2])
        self.assertEqual(result['points'][3:],args[1][3:])

    def test_hand_unknown_and_shared_hand_are_pinned(self):
        for role in ('hand','unknown','hanging_cloth'):
            args=fixture(role);r=solve(*args,5.)
            self.assertFalse(r['selected']);self.assertEqual(r['points'],args[1]);self.assertEqual(r['free_vertices'],[])
        mesh,points,labels=fixture()
        mesh['triangles'].append([1,3,4]);labels.append(dict(triangle_id=2,role='hand'))
        # Avoid collinear bind triangle for the shared-pin test.
        mesh['vertices_xy'][4][1]=5.;points[4][1]=5.
        r=solve(mesh,points,labels,5.)
        self.assertNotIn(1,r['free_vertices']);self.assertEqual(r['points'][1],points[1])

    def test_tiny_budget_rejection_preserves_failed_pose(self):
        args=fixture();r=solve(*args,.0001)
        self.assertFalse(r['selected']);self.assertEqual(r['points'],args[1])
        self.assertEqual(r['selected_qa'],r['before_qa'])
        self.assertLessEqual(r['max_trial_offset'],.0001+1e-12)

    def test_scale_with_budget_and_invalid_budget(self):
        mesh,p,labels=fixture();a=solve(mesh,p,labels,5.)
        mesh2=deepcopy(mesh);mesh2['vertices_xy']=[[x*3+100,y*3-40] for x,y in mesh['vertices_xy']]
        b=solve(mesh2,[[x*3+100,y*3-40] for x,y in p],labels,15.)
        self.assertEqual(a['selected'],b['selected'])
        for x,y in zip(a['points'],b['points']):
            self.assertLess(math.dist([x[0]*3+100,x[1]*3-40],y),1e-9)
        for budget in (0,-1,float('nan'),True):
            with self.assertRaises(ValueError):solve(mesh,p,labels,budget)


if __name__=='__main__':unittest.main()
