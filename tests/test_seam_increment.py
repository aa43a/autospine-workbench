import unittest
from copy import deepcopy
from unittest.mock import patch
from autospine_workbench.targets.spine43.seam_increment import geometry,select,solve


class IncrementTests(unittest.TestCase):
    def fixture(self):
        reference=[[0.,0.],[1.,0.],[0.,1.]]
        anchors=[{'triangle':[0,1,2],'barycentric':[float(i==j) for i in range(3)]} for j in range(3)]
        return reference,anchors,[[0,1,2]]

    def test_fixed_reference_cannot_reset_area_budget(self):
        ref,anchors,tri=self.fixture();current=[[0,0],[.51,0],[0,1]]
        delta,qa=select(ref,current,[[0,0],[-.2,0],[0,0]],anchors,[[0,0],[-.2,0],[0,0]],tri)
        points=[[a+b for a,b in zip(p,d)] for p,d in zip(current,delta)]
        self.assertTrue(geometry(ref,points,tri));self.assertGreater(qa['backtracks'],0)
        self.assertGreaterEqual(points[1][0],.5)

    def test_residual_regression_retains_original_deform(self):
        ref,anchors,tri=self.fixture();current=[[x+3,y+2] for x,y in ref]
        delta,qa=select(ref,current,[[-1,0]]*3,anchors,[[1,0]]*3,tri)
        self.assertEqual(delta,[[0.,0.]]*3);self.assertEqual(qa['status'],'retained_baseline')

    def test_increment_cap_and_zero(self):
        ref,anchors,tri=self.fixture()
        delta,qa=solve(ref,ref,anchors,[[50,0]]*3,tri,[[0,1,2]])
        self.assertLessEqual(qa['max_increment_px'],2+1e-8)
        delta,qa=solve(ref,ref,anchors,[[0,0]]*3,tri,[[0,1,2]])
        self.assertEqual(delta,[[0.,0.]]*3)

    def test_invalid_baseline_rejected(self):
        ref,anchors,tri=self.fixture()
        with self.assertRaisesRegex(ValueError,'increment_baseline_geometry_failed'):
            select(ref,[[0,0],[.4,0],[0,1]],[[0,0]]*3,anchors,[[0,0]]*3,tri)

    def test_zero_increment_bake_keeps_existing_animation(self):
        from tests.test_seam_translation import fixture
        from autospine_workbench.targets.spine43.seam_increment_bake import bake
        from autospine_workbench.targets.spine43.continuous_pose import world
        reference,files=fixture(distance=2);source=deepcopy(reference)
        animation=next(iter(source['animations'].values()))
        animation['attachments']['default']['shoe']={'shoe':{'deform':[{'time':t,'vertices':[d,0.]*3} for t,d in ((0,0),(1,.5),(2,0))]}}
        frozen=deepcopy(source);anchor={'triangle':[0,1,2],'barycentric':[1.,0.,0.],'pixel_xy':[0,0]}
        mapped={'boundaries':{n:{'samples':[anchor]} for n in ('leg','shoe')},
                'relations':[{'driver':'leg','follower':'shoe','pairs':[{'driver_sample':0,'follower_sample':0}]}]}
        parameters={'analysis':{'relations':[{'driver':'leg','follower':'shoe','groups':[]}]}}
        zero=lambda ref,current,*args:([[0.,0.] for _ in current],{'status':'retained_baseline','scale':0.,'backtracks':13})
        with patch('autospine_workbench.targets.spine43.seam_increment_bake.solve',side_effect=zero):
            doc,_=bake(source,reference,files,mapped,parameters)
        self.assertEqual(source,frozen)
        for i in range(121):
            for a,b in zip(world(source,i/60)['shoe'],world(doc,i/60)['shoe']):
                for x,y in zip(a,b):self.assertAlmostEqual(x,y,places=12)
