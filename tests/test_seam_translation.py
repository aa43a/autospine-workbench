"""Rigid seam correction, alpha gating and bounded failure cases."""
from copy import deepcopy
from io import BytesIO
import unittest
from PIL import Image
from autospine_workbench.targets.spine43.seam_translation import constrain
from autospine_workbench.targets.spine43.continuous_pose import world


def fixture(distance=4,alpha=255):
    points=[(10,0),(12,0),(10,2)];driver=[];follower=[]
    for x,y in points:
        driver.extend([2,0,x,y,.5,1,x,y,.5]);follower.extend([1,1,x,y,1])
    attachment=lambda v:{'vertices':v,'triangles':[0,1,2],'uvs':[.25,.25,.75,.25,.25,.75]}
    doc={'bones':[{'name':'root','x':0,'y':0,'rotation':0},{'name':'foot','parent':'root','x':0,'y':0,'rotation':0}],
        'skins':[{'attachments':{'leg':{'leg':attachment(driver)},'shoe':{'shoe':attachment(follower)}}}],
        'animations':{'continuous-corrective-inspection':{'bones':{},'attachments':{'default':{'leg':{'leg':{'deform':[
            {'time':0,'vertices':[0.]*12},{'time':1,'vertices':[distance,0.]*6},{'time':2,'vertices':[0.]*12}]}}}}}}}
    buffer=BytesIO();Image.new('RGBA',(8,8),(255,255,255,alpha)).save(buffer,format='PNG')
    return doc,{'editor/images/'+n+'.png':buffer.getvalue() for n in ('leg','shoe')}


class SeamTranslationTests(unittest.TestCase):
    def test_translation_closes_synthetic_seam_without_shape_change(self):
        source,files=fixture();before=deepcopy(source);doc,qa=constrain(source,files)
        self.assertEqual(source,before);self.assertEqual(constrain(source,files),(doc,qa))
        self.assertEqual(qa['status'],'candidate_requires_review')
        self.assertGreater(qa['before']['seam_proxy'][0]['max_distance_growth_px'],2)
        self.assertLess(qa['after']['seam_proxy'][0]['max_distance_growth_px'],1e-7)
        self.assertEqual(world(doc,0),world(doc,2))
        self.assertAlmostEqual(qa['after']['regions']['shoe']['max_area_ratio'],1)
        self.assertEqual(qa['candidates'][0]['review_status'],'pending')

    def test_over_budget_remains_blocked(self):
        source,files=fixture(100);_,qa=constrain(source,files)
        self.assertEqual(qa['status'],'blocked')
        self.assertLessEqual(qa['candidates'][0]['max_translation_px'],16)
        self.assertGreater(qa['candidates'][0]['capped_keys'],0)

    def test_transparent_contact_is_noop(self):
        source,files=fixture(alpha=0);doc,qa=constrain(source,files)
        self.assertEqual(qa['status'],'candidate_noop');self.assertEqual(qa['candidates'],[])
        self.assertEqual(world(source,1),world(doc,1))

    def test_ambiguous_driver_is_not_chosen(self):
        source,files=fixture();a=source['skins'][0]['attachments']
        a['other']={'other':deepcopy(a['leg']['leg'])};files['editor/images/other.png']=files['editor/images/leg.png']
        _,qa=constrain(source,files);self.assertEqual(qa['candidates'],[])

    def test_missing_texture_fails(self):
        source,files=fixture();files.pop('editor/images/shoe.png')
        with self.assertRaises(KeyError):constrain(source,files)
