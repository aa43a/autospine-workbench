from copy import deepcopy
import json
import unittest

from m4_regional_replay_inputs import prepare
from autospine_workbench.targets.character43.regional_depth_profile import partition_slots


def fixture():
    skeleton=dict(bones=[dict(name='root')],slots=[dict(name='skirt')],animations={})
    source={'skeleton.json':json.dumps(skeleton).encode(),'images/skirt.png':b'image',
            'skeleton.atlas':b'atlas','skirt-trial.json':json.dumps(dict(
                profile='fixed-waist-three-chain-sway-v1',rows=[dict(layer_id='skirt')])).encode()}
    candidate={k:v for k,v in source.items() if k!='skirt-trial.json'}
    skeleton['animations']={'external-motion':{}}
    candidate['skeleton.json']=json.dumps(skeleton).encode()
    candidate['character-manifest.json']=b'{"source_character_sha256":"character"}'
    return candidate,source


class RegionalReplayInputsTests(unittest.TestCase):
    def test_restores_worker_partition_inventory_without_changing_candidate(self):
        candidate,source=fixture();before=deepcopy((candidate,source))
        inputs,receipt=prepare(candidate,source,'character')
        self.assertEqual(partition_slots(inputs,json.loads(inputs['skeleton.json'])),['skirt'])
        self.assertEqual(inputs['skeleton.json'],candidate['skeleton.json'])
        self.assertIn('skirt-trial.json',receipt['restored_metadata'])
        self.assertEqual((candidate,source),before)

    def test_wrong_source_changed_rig_texture_or_metadata_rejected(self):
        candidate,source=fixture()
        with self.assertRaisesRegex(ValueError,'identity'):prepare(candidate,source,'other')
        for name,raw,reason in [('skeleton.json',b'{"bones":[],"slots":[]}','rig_changed'),
                               ('images/skirt.png',b'other','texture_changed'),
                               ('skirt-trial.json',b'{}','metadata_changed')]:
            changed=dict(candidate);changed[name]=raw
            with self.assertRaisesRegex(ValueError,reason):prepare(changed,source,'character')

    def test_absent_source_metadata_is_not_invented(self):
        candidate,source=fixture();del source['skirt-trial.json']
        inputs,receipt=prepare(candidate,source,'character')
        self.assertEqual(receipt['restored_metadata'],{})
        self.assertNotIn('skirt-trial.json',inputs)
        candidate['skirt-trial.json']=b'{}'
        with self.assertRaisesRegex(ValueError,'without_source'):prepare(candidate,source,'character')


if __name__=='__main__':unittest.main()
