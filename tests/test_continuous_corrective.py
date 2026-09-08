"""Linear interpolation, loop closure, source purity and seam separation."""
from copy import deepcopy
import math
import unittest
from autospine_workbench.asset.joints.combined_corrective import POSES
from autospine_workbench.targets.spine43.continuous_bake import blend,bake
from autospine_workbench.targets.spine43.continuous_pose import world,interpolate,inspect


def fixture():
    bones=[{'name':'root','x':0,'y':0,'rotation':0},
           {'name':'main','parent':'root','x':0,'y':0,'rotation':0}]
    attachment=lambda index:{'triangles':[0,1,2],'vertices':[1,index,10,0,1,1,index,12,0,1,1,index,10,2,1]}
    return {'bones':bones,'skins':[{'attachments':{'moving':{'moving':attachment(1)},'fixed':{'fixed':attachment(0)}}}],
        'animations':{'combined-pose-inspection':{'bones':{'main':{'rotate':[{'time':i*.5,'value':-a,'curve':'stepped'} for i,(a,b) in enumerate(POSES)]}},
        'attachments':{'default':{'moving':{'moving':{'deform':[{'time':i*.5,'vertices':[0]*6,'curve':'stepped'} for i in range(len(POSES))]}}}}}}}


class ContinuousCorrectiveTests(unittest.TestCase):
    def test_bilinear_field_and_domain(self):
        grid={(a,b):[a+2*b,a*b] for a in (0,30,60) for b in (-30,0,30)}
        self.assertEqual(blend(grid,15,-15),[-15,-225])
        for a,b in ((-1,0),(0,31),(math.nan,0),(0,math.inf)):
            with self.assertRaises(ValueError):blend(grid,a,b)

    def test_linear_and_stepped_midpoint(self):
        keys=[{'time':0,'vertices':[2,4]},{'time':1,'vertices':[6,8]}]
        self.assertEqual(interpolate(keys,.5,'vertices'),[4,6])
        keys[0]['curve']='stepped'
        self.assertEqual(interpolate(keys,.5,'vertices'),[2,4])

    def test_local_deform_midpoint_is_transformed_by_bone(self):
        doc=fixture();doc['bones'][1]['rotation']=90
        doc['animations']={'test':{'bones':{},'attachments':{'default':{'moving':{'moving':{'deform':[
            {'time':0,'vertices':[0]*6},{'time':1,'vertices':[2,0,2,0,2,0]}]}}}}}}
        point=world(doc,.5)['moving'][0]
        self.assertAlmostEqual(point[0],0);self.assertAlmostEqual(point[1],11)

    def test_bake_loop_source_purity_and_seam_failure(self):
        source=fixture();before=deepcopy(source);doc,qa=bake(source)
        self.assertEqual(source,before);self.assertEqual(bake(source),(doc,qa))
        self.assertEqual(world(doc,0),world(doc,2));self.assertNotEqual(world(doc,0),world(doc,1))
        self.assertTrue(all(r['passed'] for r in qa['regions'].values()))
        self.assertEqual(qa['seam_proxy'][0]['status'],'blocked')
        self.assertEqual(qa['sample_count'],121)
        self.assertGreater(qa['seam_proxy'][0]['max_distance_growth_px'],2)
        self.assertNotIn('curve',doc['animations']['continuous-corrective-inspection']['bones']['main']['rotate'][0])

    def test_missing_pairs_are_not_seam_pass(self):
        source=fixture();del source['skins'][0]['attachments']['fixed']
        _,qa=bake(source)
        self.assertEqual(qa['unpaired_regions'],['moving'])
        self.assertEqual(qa['seam_coverage'],'unproven')

    def test_degenerate_mesh_blocked(self):
        source=fixture();source['skins'][0]['attachments']['moving']['moving']['triangles']=[0,0,0]
        with self.assertRaisesRegex(ValueError,'degenerate'):bake(source)
