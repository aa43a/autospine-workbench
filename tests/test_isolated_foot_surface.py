from copy import deepcopy
import unittest
from autospine_workbench.targets.character43.isolated_foot_surface import build
from autospine_workbench.targets.character43.affine_pose import sample


class IsolatedFootSurfaceTests(unittest.TestCase):
    def fixture(self):
        mesh=dict(type='mesh',triangles=[0,1,2],uvs=[0,0,1,0,0,1],
                  vertices=[1,1,0,0,1,1,1,1,0,1,1,1,0,1,1])
        document=dict(bones=[dict(name='root',x=0,y=0,rotation=0),dict(name='foot_l',parent='root',x=0,y=0,rotation=0)],
            slots=[dict(name='shoe',bone='root'),dict(name='leg',bone='root')],
            skins=[dict(name='default',attachments={s:{s:deepcopy(mesh)} for s in ('shoe','leg')})],
            animations={'move':dict(bones={})})
        adjusted=deepcopy(document)
        adjusted['animations']['move']['bones']['foot_l']=dict(rotate=[dict(time=0,value=90)])
        return document,adjusted

    def test_selected_shoe_moves_but_leg_keeps_old_foot_frame(self):
        document,adjusted=self.fixture();before=deepcopy(document)
        result,report=build(document,adjusted,'move',{'shoe':'foot_l'})
        a,b,c=[sample(d,'move',0)[0] for d in (document,adjusted,result)]
        self.assertEqual(c['leg'],a['leg']);self.assertEqual(c['shoe'],b['shoe'])
        self.assertEqual(result['slots'],document['slots']);self.assertEqual(document,before)
        self.assertFalse(report['selected'])

    def test_mixed_mesh_is_not_silently_rebound(self):
        document,adjusted=self.fixture()
        for d in (document,adjusted):d['skins'][0]['attachments']['shoe']['shoe']['vertices'][1]=0
        with self.assertRaisesRegex(ValueError,'mixed_mesh_rejected'):
            build(document,adjusted,'move',{'shoe':'foot_l'})

    def test_other_animation_keeps_original_motion(self):
        document,adjusted=self.fixture()
        other=dict(bones={'foot_l':dict(rotate=[dict(time=0,value=35)])})
        for d in (document,adjusted):d['animations']['other']=deepcopy(other)
        result,_=build(document,adjusted,'move',{'shoe':'foot_l'})
        self.assertEqual(sample(result,'other',0)[0],sample(document,'other',0)[0])

    def test_unrelated_track_edit_rejected(self):
        document,adjusted=self.fixture()
        adjusted['animations']['move']['bones']['root']=dict(rotate=[dict(time=0,value=10)])
        with self.assertRaisesRegex(ValueError,'changes_outside_foot_tracks'):
            build(document,adjusted,'move',{'shoe':'foot_l'})
