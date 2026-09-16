import unittest
from copy import deepcopy
from autospine_workbench.automation.character_mount_revalidation import equivalent
from autospine_workbench.automation.storage_io import canonical_bytes


class MountRevalidationTests(unittest.TestCase):
    def fixture(self):
        manifest={'source_addresses':{'resolved_project_sha256':'a'*64,'base_bundle_sha256':'b'*64},
            'source_character_sha256':'c'*64,'layers':[{'layer_id':'wing'}],'files':{}}
        old={'character-manifest.json':canonical_bytes(manifest),'skeleton.json':b'rig and motion',
            'numeric-reference.json':b'frames','images/wing.png':b'texture',
            'skirt-trial.json':canonical_bytes({'source_character_sha256':'c'*64,'rows':[1]})}
        changed=deepcopy(manifest);changed['source_addresses']['base_bundle_sha256']='d'*64
        changed['source_character_sha256']='e'*64;changed['motion_replay_sha256']='f'*64
        new={**old,'character-manifest.json':canonical_bytes(changed),
            'motion-replay.json':b'receipt',
            'skirt-trial.json':canonical_bytes({'source_character_sha256':'e'*64,'rows':[1]})}
        return old,new,changed

    def test_only_receipt_changes_reuse_render_identical_content(self):
        old,new,_=self.fixture();self.assertTrue(equivalent(old,new))
        for key in ('skeleton.json','numeric-reference.json','images/wing.png'):
            self.assertFalse(equivalent(old,{**new,key:b'changed'}))

    def test_identity_layer_and_profile_changes_block(self):
        old,new,manifest=self.fixture()
        for change in (lambda m:m['source_addresses'].update(resolved_project_sha256='f'*64),
                       lambda m:m.update(layers=[])):
            modified=deepcopy(manifest);change(modified)
            self.assertFalse(equivalent(old,{**new,'character-manifest.json':canonical_bytes(modified)}))
        self.assertFalse(equivalent(old,{**new,'skirt-trial.json':canonical_bytes({'rows':[2]})}))
