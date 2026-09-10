import math
import unittest
from autospine_workbench.asset.planning.sleeve_support_mesh import refine
from autospine_workbench.asset.joints.mesh_weights import _deform,_area


class SleeveSupportTests(unittest.TestCase):
    def fixture(self):
        p=[[0.,0.],[2.,0.],[0.,2.],[2.,2.]]
        w=[[dict(bone_id='a',weight=.25,local_xy=v[:]),dict(bone_id='b',weight=.75,local_xy=[v[0]-2,v[1]])] for v in p]
        return dict(setup_vertices=p,triangles=[[0,1,2],[1,3,2]],weights=w)

    def test_conforming_shared_midpoints_and_exact_lbs(self):
        row=self.fixture();uvs=[[x/2,y/2] for x,y in row['setup_vertices']]
        result=refine(row,uvs,[dict(role='cuff'),dict(role='hand')])
        transforms={'a':([10.,20.],34.),'b':([15.,21.],-23.)}
        old=_deform(row['weights'],transforms);new=_deform(result['weights'],transforms)
        for actual,parents in zip(new,result['vertex_source_indices']):
            expected=[sum(old[i][k] for i in parents)/len(parents) for k in (0,1)]
            self.assertLess(math.dist(actual,expected),1e-10)
        self.assertEqual(result['vertex_source_indices'].count([1,2]),1)
        for i in range(2):
            area=sum(_area(result['vertices_xy'],t) for t,j in zip(result['triangles'],result['source_triangle_indices']) if j==i)
            self.assertAlmostEqual(area,_area(row['setup_vertices'],row['triangles'][i]))
        for v,uv in zip(result['vertices_xy'],result['uvs']):self.assertEqual(uv,[x/2 for x in v])

    def test_unrelated_geometry_stays_identical(self):
        row=self.fixture();uvs=[[0.,0.]]*4
        out=refine(row,uvs,[dict(role='hand'),dict(role='unknown')])
        self.assertEqual(out['vertices_xy'],row['setup_vertices']);self.assertEqual(out['triangles'],row['triangles'])
        with self.assertRaises(ValueError):refine(row,uvs,[])
