from copy import deepcopy
import math
import unittest

from autospine_workbench.targets.character43.torso_projection_source import shapes
from autospine_workbench.targets.character43.torso_projection_candidate import build,transformed
from autospine_workbench.targets.character43.affine_pose import matrices,sample


def observations(angle):
    c,s=math.cos(math.radians(angle)),math.sin(math.radians(angle))
    return [(-c,-2,-s),(c,-2,s),(0,0,0)]


def fixture():
    bones=[dict(name='root',x=0,y=0,rotation=0),
        dict(name='chest',parent='root',x=0,y=1,rotation=90),
        dict(name='neck',parent='chest',x=2,y=0,rotation=0),
        dict(name='clavicle_l',parent='chest',x=0,y=0,rotation=-90),
        dict(name='upperarm_l',parent='clavicle_l',x=1,y=0,rotation=-30),
        dict(name='upperarm_r',parent='chest',x=0,y=1,rotation=30)]
    attachments={}
    for name,index in [('torso',1),('head',2),('arm',4),('leg',0)]:
        attachments[name]={name:dict(vertices=[1,index,0,0,1,1,index,1,0,1,1,index,0,1,1],triangles=[0,1,2])}
    return dict(bones=bones,skins=[dict(attachments=attachments)],
        animations={'move':{'bones':{'root':{'rotate':[dict(time=0,value=0),dict(time=1,value=0)]}}}})


class TorsoProjectionTests(unittest.TestCase):
    def test_turn_shortens_width_without_height_loss(self):
        report=shapes([observations(0),observations(50)],[0,1])
        row=report['records'][1]
        self.assertAlmostEqual(row['transverse'],math.cos(math.radians(50)))
        self.assertAlmostEqual(row['longitudinal'],1)
        self.assertEqual(row['reasons'],[])

    def test_side_and_back_frames_are_retained_and_blocked(self):
        for angle,reason in [(90,'torso_side_view_degenerate'),(120,'torso_back_view_requires_artwork')]:
            report=shapes([observations(0),observations(angle)],[0,1])
            candidate,receipt=build(fixture(),'move',report,samples=3)
            self.assertIsNone(candidate)
            self.assertIn(reason,receipt['failures'][0]['reasons'])
            self.assertEqual(receipt['failures'][0]['time'],1)

    def test_roll_does_not_apply_second_rotation(self):
        frame=observations(0); a=.4
        rotated=[(math.cos(a)*x-math.sin(a)*y,math.sin(a)*x+math.cos(a)*y,z) for x,y,z in frame]
        row=shapes([frame,rotated],[0,1])['records'][1]
        self.assertAlmostEqual(row['transverse'],1)
        self.assertAlmostEqual(row['longitudinal'],1)
        self.assertAlmostEqual(row['shear'],0)

    def test_bake_preserves_arm_head_shapes_and_leg_and_inputs(self):
        doc=fixture(); original=deepcopy(doc)
        candidate,receipt=build(doc,'move',shapes([observations(0),observations(50)],[0,1]),samples=3)
        self.assertEqual(doc,original)
        self.assertEqual(candidate['bones'],doc['bones'])
        self.assertEqual(candidate['skins'],doc['skins'])
        before=sample(doc,'move',1)[0]; after=sample(candidate,'move',1)[0]
        for name in ('head','arm'):
            self.assertAlmostEqual(math.dist(before[name][0],before[name][1]),math.dist(after[name][0],after[name][1]))
        self.assertNotEqual(after['arm'][0],before['arm'][0])
        self.assertEqual(after['leg'],before['leg'])
        self.assertNotIn('leg',receipt['changed_slots'])
        self.assertAlmostEqual(math.dist(after['torso'][0],after['torso'][2]),math.cos(math.radians(50)))

    def test_existing_deform_is_composed_not_discarded(self):
        doc=fixture()
        doc['animations']['move']['attachments']={'default':{'arm':{'arm':{'deform':[
            dict(time=0,vertices=[.1,.2]*3),dict(time=1,vertices=[.3,.4]*3)]}}}}
        before=sample(doc,'move',1)[0]
        candidate,_=build(doc,'move',shapes([observations(0),observations(50)],[0,1]),samples=3)
        after=sample(candidate,'move',1)[0]
        self.assertAlmostEqual(math.dist(before['arm'][0],before['arm'][1]),math.dist(after['arm'][0],after['arm'][1]))
        for name,points in sample(doc,'move',0)[0].items():
            for a,b in zip(points,sample(candidate,'move',0)[0][name]):
                for x,y in zip(a,b): self.assertAlmostEqual(x,y)


if __name__=='__main__': unittest.main()
