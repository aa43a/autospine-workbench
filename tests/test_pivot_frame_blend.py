import math
import unittest
from autospine_workbench.targets.character43.pivot_frame_blend import blend, weighted_points


def rotation(degrees, x=0, y=0):
    a=math.radians(degrees);c,s=math.cos(a),math.sin(a)
    return (c,-s,s,c,x,y)


class PivotBlendTests(unittest.TestCase):
    def test_opposite_bends_do_not_collapse_width(self):
        actual=blend([0,2],[0,0],[rotation(-70),rotation(70)],[.5,.5])
        self.assertAlmostEqual(actual[0],0)
        self.assertAlmostEqual(actual[1],2)

    def test_shared_pivot_maps_to_weighted_anchor(self):
        self.assertEqual(blend([0,0],[0,0],[rotation(50,3,4),rotation(-30,7,8)],[.25,.75]),[6.,7.])

    def test_single_owner_preserves_nonuniform_affine(self):
        actual=blend([4,5],[2,3],[(.4,.7,0,1,10,20)],[1])
        for a,b in zip(actual,[15.1,25]):self.assertAlmostEqual(a,b)

    def test_setup_identity(self):
        self.assertEqual(blend([3,4],[1,2],[rotation(0),rotation(0)],[.7,.3]),[3.,4.])

    def test_ambiguous_half_turn_and_invalid_weights_rejected(self):
        with self.assertRaisesRegex(ValueError,'ambiguous'):
            blend([0,2],[0,0],[rotation(0),rotation(180)],[.5,.5])
        with self.assertRaises(ValueError):blend([0,2],[0,0],[rotation(0)],[-1])

    def test_pair_uses_its_child_joint_not_component_root(self):
        bones=[{'name':'upper'},{'name':'lower','parent':'upper'},{'name':'tip','parent':'lower'}]
        rest={'upper':(1,0,0,1,0,0),'lower':(1,0,0,1,10,0),'tip':(1,0,0,1,20,0)}
        current=dict(rest,tip=rotation(90,20,0))
        mesh={'vertices':[2,1,10,2,.5,2,0,2,.5]}
        point=weighted_points(mesh,bones,rest,current,[])[0]
        self.assertAlmostEqual(point[0],20-math.sqrt(2))
        self.assertAlmostEqual(point[1],math.sqrt(2))

    def test_nonadjacent_pair_rejected(self):
        bones=[{'name':'a'},{'name':'b'}];rest={n:(1,0,0,1,0,0) for n in ('a','b')}
        with self.assertRaisesRegex(ValueError,'adjacent'):
            weighted_points({'vertices':[2,0,1,2,.5,1,1,2,.5]},bones,rest,rest,[])

    def test_positive_frames_do_not_prove_triangle_orientation(self):
        transforms=[rotation(0),rotation(0,-2,0)]
        points=[blend(p,[0,0],transforms,w) for p,w in
                [([0,0],[1,0]),([1,0],[0,1]),([0,1],[1,0])]]
        a,b,c=points
        signed=(b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])
        self.assertLess(signed,0)  # Mesh QA must reject even valid local frames.
