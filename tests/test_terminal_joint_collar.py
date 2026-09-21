import unittest
from autospine_workbench.targets.character43.terminal_joint_collar import propose,extend_proximal_ring


class CollarTests(unittest.TestCase):
    def test_extra_ring_is_proximal_only_and_not_recursive(self):
        c=dict(vertices=[0],parent='calf',child='foot');bones=[dict(name='calf'),dict(name='foot')]
        result=extend_proximal_ring(c,[[0,1,2],[1,2,3]], [[(0,1)],[(0,1)],[(1,1)],[(0,1)]],bones)
        self.assertEqual(result['vertices'],[0,1]);self.assertEqual(c['vertices'],[0])

    def test_only_adjacent_nearby_proximal_vertices_can_move(self):
        points=[[0,0],[1,0],[2,1],[2,0],[100,0]]
        triangles=[[0,1,2],[1,2,3],[1,2,4]]
        influences=[[(0,1)],[(0,.5),(1,.5)],[(0,.5),(1,.5)],[(1,1)],[(0,1)]]
        bones=[dict(name='calf'),dict(name='foot',parent='calf')]
        pose={'calf':(1,0,0,1,0,100),'foot':(1,0,0,1,0,0)}
        report=propose(points,triangles,influences,bones,pose,'calf','foot')
        self.assertEqual(report['vertices'],[0])
        self.assertLessEqual(report['radius_px'],15)
