from copy import deepcopy
import unittest
from autospine_workbench.targets.spine43.mixed_character import compose
from autospine_workbench.targets.spine43.continuous_pose import world
from autospine_workbench.benchmark.layer_binding_draft import build_layer_binding_draft
from autospine_workbench.resolved_project import canonical_sha256


class MixedCharacterTests(unittest.TestCase):
    def fixture(self):
        source={'layers':[dict(layer_id=n,bbox=[0,0,10,10]) for n in ('back','leg','pending')]}
        skeleton={'bones':[dict(id='root',parent_id=None,length=0,setup_local=dict(x=0,y=0,rotation_degrees=0))]}
        atlas=dict(source_skeleton_sha256=canonical_sha256(skeleton),layers=[dict(layer_id='leg',partitions=[dict(id='leg-l')])])
        bindings=dict(schema='autospine.layer-binding-candidates/v2',authority='none',production_authorized=False,status='needs_review',
                      candidate_sha256=canonical_sha256(source),source_skeleton_sha256=canonical_sha256(skeleton),
                      bindings=[dict(layer_id=n,status='needs_review',options=[dict(id='rigid',mode='rigid',bone_ids=['root'],setup_local=dict(x=5,y=5,rotation_degrees=0))]) for n in ('back','leg','pending')])
        draft=build_layer_binding_draft(bindings);draft['records'][0].update(action='bind',option_id='rigid')
        attachment=dict(vertices=[1,0,0,0,1,1,0,1,0,1,1,0,0,-1,1])
        doc=dict(bones=[dict(name='root',x=0,y=0,rotation=0,length=0)],skins=[dict(attachments={'leg-l':{'leg-l':attachment}})],slots=[dict(name='leg-l',bone='root',attachment='leg-l')],animations={'test':{'bones':{}}})
        return doc,source,skeleton,atlas,bindings,draft

    def test_rigid_setup_and_unchanged_partition(self):
        args=self.fixture();original=deepcopy(args[0]);doc,rigid,excluded=compose(*args)
        self.assertEqual(rigid,['back']);self.assertEqual([s['name'] for s in doc['slots']],['back','leg-l'])
        self.assertEqual(excluded,[dict(layer_id='pending',reason_code='binding_pending')])
        self.assertEqual(world(doc,0)['back'],[[0,0],[10,0],[10,-10],[0,-10]])
        self.assertEqual(doc['skins'][0]['attachments']['leg-l'],original['skins'][0]['attachments']['leg-l'])
        self.assertEqual(doc['animations'],original['animations']);self.assertEqual(args[0],original)

    def test_changed_setup_and_binding_identity_rejected(self):
        args=self.fixture();args[0]['bones'][0]['x']=1
        with self.assertRaisesRegex(ValueError,'bone_setup'):compose(*args)
        args=self.fixture();args[4]['candidate_sha256']='0'*64
        with self.assertRaises(ValueError):compose(*args)
