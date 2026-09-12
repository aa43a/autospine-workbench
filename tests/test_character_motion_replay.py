"""Only receipt-only changes can replay an exact existing motion candidate."""
import json
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from autospine_workbench.automation.character_motion_replay import equivalent, replay


class MotionReplayTests(unittest.TestCase):
    def test_real_composition_replay_keeps_render_payload(self):
        from test_character_motion_composition import package
        from autospine_workbench.targets.character43.motion_composition import compose
        old=package('idle'); manifest=json.loads(old['character-manifest.json'])
        manifest['source_addresses']={'base_bundle_sha256':'1'*64}
        old['character-manifest.json']=json.dumps(manifest).encode()
        current=dict(old); manifest['source_addresses']['base_bundle_sha256']='2'*64
        current['character-manifest.json']=json.dumps(manifest).encode()
        motion=package('walk'); bundles={'a'*64:old,'c'*64:current,'b'*64:motion}
        expected=compose(old,motion,'a'*64,'b'*64)
        actual=replay(SimpleNamespace(read=bundles.__getitem__),'a'*64,'c'*64,'b'*64)
        self.assertEqual({k:v for k,v in actual.items() if k not in ('character-manifest.json','motion-replay.json')},
                         {k:v for k,v in expected.items() if k != 'character-manifest.json'})

    def bundle(self, address='a'*64, **extra):
        return {'skeleton.json':b'{}', 'texture.png':b'exact',
            'character-manifest.json':json.dumps(dict(source_addresses={
                'base_bundle_sha256':address, 'input_identity_sha256':'b'*64}, layers=[], **extra)).encode()}

    def test_only_base_receipt_may_change(self):
        old=self.bundle(); new=self.bundle('c'*64)
        self.assertTrue(equivalent(old,new))
        self.assertFalse(equivalent(old,{**new,'texture.png':b'changed'}))
        self.assertFalse(equivalent(old,self.bundle('c'*64,decision='confirmed')))
        self.assertFalse(equivalent(old,{**new,'unexpected.json':b'{}'}))
        self.assertEqual(json.loads(old['character-manifest.json'])['source_addresses']['base_bundle_sha256'],'a'*64)

    def test_replay_records_both_addresses_without_rewriting_old_bundle(self):
        old,new=self.bundle(),self.bundle('c'*64)
        bundles={'d'*64:old,'e'*64:new,'f'*64:{'motion':b'exact'}}
        store=SimpleNamespace(read=lambda digest:bundles[digest])
        with patch('autospine_workbench.targets.character43.motion_composition.compose',return_value=dict(old)) as compose:
            result=replay(store,'d'*64,'e'*64,'f'*64)
            compose.assert_called_once_with(old,bundles['f'*64],'d'*64,'f'*64)
        manifest=json.loads(result['character-manifest.json'])
        self.assertEqual(manifest['source_addresses']['base_bundle_sha256'],'c'*64)
        self.assertIn('motion-replay.json',manifest['files'])
        self.assertNotIn('motion-replay.json',old)
        receipt=json.loads(result['motion-replay.json'])
        self.assertEqual(receipt['previous_character_sha256'],'d'*64)
        self.assertEqual(receipt['current_character_sha256'],'e'*64)
        self.assertEqual(receipt['authority'],'none')
