import json
from hashlib import sha256
import unittest
from autospine_workbench.targets.character43.numeric_reference import carry_setup


class SetupCarryTests(unittest.TestCase):
    def fixture(self):
        before=json.dumps(dict(bones=[],slots=[],skins=[],animations={'idle':{}})).encode()
        after=json.dumps(dict(bones=[],slots=[],skins=[],animations={'move':{}})).encode()
        reference=dict(skeleton_sha256=sha256(before).hexdigest(),vertices={'a':[[1,2]]},time=0)
        return {'skeleton.json':before,'rig-setup-reference.json':json.dumps(reference).encode()},{'skeleton.json':after}

    def test_exact_reference_survives_animation_change(self):
        source,output=self.fixture();original=dict(source)
        self.assertEqual(carry_setup(source,output),{'a':[[1,2]]})
        self.assertEqual(source,original)
        self.assertEqual(json.loads(output['rig-setup-reference.json'])['skeleton_sha256'],sha256(output['skeleton.json']).hexdigest())

    def test_stale_source_and_bind_change_rejected(self):
        source,output=self.fixture();source['skeleton.json']=b'{}'
        with self.assertRaisesRegex(ValueError,'source_mismatch'):carry_setup(source,output)
        source,output=self.fixture();output['skeleton.json']=b'{"bones":[{"name":"new"}]}'
        with self.assertRaisesRegex(ValueError,'bind_changed'):carry_setup(source,output)

    def test_legacy_without_setup_stays_unchanged(self):
        output={'skeleton.json':b'{}'}
        self.assertIsNone(carry_setup({},output));self.assertEqual(output,{'skeleton.json':b'{}'})
