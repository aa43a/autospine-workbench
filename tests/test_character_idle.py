from copy import deepcopy
from hashlib import sha256
import json
import unittest
from autospine_workbench.automation.storage_io import canonical_bytes
from autospine_workbench.targets.character43.idle_package import append_idle
from autospine_workbench.targets.spine43.continuous_pose import world


class IdleTests(unittest.TestCase):
    def fixture(self):
        bones=[dict(name='root',x=0,y=0,rotation=0)]
        for name,parent in [('spine','root'),('chest','spine'),('head','chest'),('thigh_l','root'),('calf_l','thigh_l'),('foot_l','calf_l'),('thigh_r','root'),('calf_r','thigh_r'),('foot_r','calf_r')]:
            bones.append(dict(name=name,parent=parent,x=10,y=0,rotation=0))
        doc=dict(bones=bones,animations={'limb-flex-15':{'bones':{}}},skins=[{'attachments':{'face':{'face':{'vertices':[1,3,0,0,1,1,3,1,0,1,1,3,0,1,1]}}}}])
        raw=canonical_bytes(doc)
        return {'skeleton.json':raw,'editor/skeleton.json':raw,'character-manifest.json':canonical_bytes({'profile':'ordinary-limb-flex-preserved-v1'}),
                'numeric-reference.json':canonical_bytes({'skeleton_sha256':sha256(raw).hexdigest(),'animations':{'limb-flex-15':[dict(time=0,vertices=world(doc,0))]}})}

    def test_frozen_motion_moves_head_and_root_preserving_old_track_and_loop(self):
        files=self.fixture();before=deepcopy(files);result=append_idle(files)
        self.assertEqual(files,before);self.assertEqual(result,append_idle(files))
        old=json.loads(files['skeleton.json']);new=json.loads(result['skeleton.json'])
        self.assertEqual(new['bones'],old['bones']);self.assertEqual(new['animations']['limb-flex-15'],old['animations']['limb-flex-15'])
        frames=json.loads(result['numeric-reference.json'])['animations']['idle']
        self.assertEqual(frames[0]['vertices'],world(old,0));self.assertEqual(frames[0]['vertices'],frames[-1]['vertices'])
        self.assertNotEqual(frames[0]['vertices'],frames[32]['vertices'])
        self.assertEqual(new['animations']['idle']['bones']['root']['translate'][1]['y'],.1)
        self.assertEqual(result['editor/skeleton.json'],result['skeleton.json'])

    def test_sleeve_profile_or_missing_bone_not_silently_skipped(self):
        files=self.fixture();files['character-manifest.json']=canonical_bytes({'profile':'sleeve'})
        with self.assertRaisesRegex(ValueError,'source_unsupported'):append_idle(files)
        files=self.fixture();doc=json.loads(files['skeleton.json']);doc['bones'].pop();files['skeleton.json']=canonical_bytes(doc)
        with self.assertRaisesRegex(ValueError,'bones_missing'):append_idle(files)
