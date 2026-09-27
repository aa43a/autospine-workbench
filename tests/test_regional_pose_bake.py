import unittest
from copy import deepcopy
from autospine_workbench.targets.character43.regional_pose_bake import bake
from autospine_workbench.targets.character43.affine_pose import sample


class RegionalPoseBakeTests(unittest.TestCase):
    def source(self):
        return dict(bones=[dict(name='root',x=0,y=0,rotation=0)],slots=[],
            skins=[dict(attachments={'cloth':{'cloth':dict(vertices=[1,0,0,0,1],uvs=[0,0],triangles=[])}})],
            animations={'move':dict(bones={'root':{'rotate':[dict(time=0,value=0),dict(time=2,value=90)]}},
                attachments={'default':{'cloth':{'cloth':{'deform':[
                    dict(time=0,vertices=[0,0]),dict(time=2,vertices=[2,0])]}}}})})

    def test_world_pose_and_outside_interval_preserved(self):
        source=self.source(); changed=bake(source,'move','cloth',{1:[[3,4]]},(.5,1.5))
        actual=sample(changed,'move',1)[0]['cloth'][0]
        for a,b in zip(actual,[3,4]):self.assertAlmostEqual(a,b,places=6)
        for t in (0,.2,.5,1.5,1.8,2):
            self.assertEqual(sample(source,'move',t)[0],sample(changed,'move',t)[0])
        self.assertEqual(source['animations']['move']['bones'],changed['animations']['move']['bones'])
        self.assertEqual(source['skins'],changed['skins'])
        self.assertEqual(len(source['animations']['move']['attachments']['default']['cloth']['cloth']['deform']),2)

    def test_endpoints_cannot_be_overwritten(self):
        with self.assertRaisesRegex(ValueError,'outside_interval'):
            bake(self.source(),'move','cloth',{.5:[[0,0]]},(.5,1.5))

    def test_other_attachment_curve_and_original_breakpoints_retained(self):
        source=self.source()
        tracks=source['animations']['move']['attachments']['default']
        tracks['other']={'other':deepcopy(tracks['cloth']['cloth'])}
        source['skins'][0]['attachments']['other']={'other':deepcopy(
            source['skins'][0]['attachments']['cloth']['cloth'])}
        tracks['cloth']['cloth']['deform'].insert(1,dict(time=.83,vertices=[.2,.1]))
        changed=bake(source,'move','cloth',{1:[[3,4]]},(.5,1.5))
        actual=changed['animations']['move']['attachments']['default']
        self.assertEqual(actual['other'],tracks['other'])
        self.assertIn(.83,[k['time'] for k in actual['cloth']['cloth']['deform']])
