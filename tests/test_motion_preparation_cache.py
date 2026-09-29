"""Checkpoint reuse must be indistinguishable from full builds."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from autospine_workbench.automation.motion_preparation_cache import PreparationCache, identity
from autospine_workbench.automation.motion_target_worker import build_candidate
from autospine_workbench.automation.storage_io import canonical_bytes
from test_motion_target_intake import inputs


class PreparationCacheTests(unittest.TestCase):
    def test_only_layer_inputs_are_excluded(self):
        base = dict(character_sha256='a', motion_identity={'bundle_sha256':'b'}, clip=None)
        key = identity(base, 'algorithm')
        self.assertEqual(key, identity(dict(base, job_id='new', layer_edits={}, layer_edit_receipt='receipt'), 'algorithm'))
        for field in ('character_sha256', 'motion_identity', 'clip', 'pose_profile', 'projection', 'contact_correction'):
            self.assertNotEqual(key, identity(dict(base, **{field:'changed'}), 'algorithm'))
        self.assertNotEqual(key, identity(base, 'new algorithm'))

    def test_changed_edits_match_full_build_and_skip_preparation(self):
        files, motion, bvh, mapping = inputs()
        document = json.loads(files['skeleton.json'])
        document['slots'] = [dict(name='point', attachment='point', bone='root')]
        attachment = document['skins'][0]['attachments']['point']['point']
        attachment.update(type='mesh', uvs=[0,0,1,0,0,1])
        files['skeleton.json'] = canonical_bytes(document)
        options = dict(character_digest='a'*64, motion_digest='b'*64)
        with tempfile.TemporaryDirectory() as root:
            request = dict(character_sha256='a'*64, motion_identity={'bundle_sha256':'b'*64})
            cache = PreparationCache(root, request)
            cold = build_candidate(files, motion, bvh, mapping, checkpoint=cache, **options)
            for edits in (None, dict(profile='slot-world-affine-v1', transforms=[], draw_order=['point']),
                          dict(profile='slot-world-affine-v1', draw_order=[], transforms=[
                              dict(slot='point', dx=3, dy=2, rotation=10, scaleX=1.1, scaleY=.9)])):
                expected = build_candidate(files, motion, bvh, mapping, layer_edits=edits, **options)
                hit = PreparationCache(root, dict(request, job_id='second', layer_edits=edits))
                with patch('autospine_workbench.automation.motion_target_worker._prepare_candidate',
                           side_effect=AssertionError('preparation must not run')):
                    actual = build_candidate(files, motion, bvh, mapping, layer_edits=edits, checkpoint=hit, **options)
                self.assertEqual(expected, actual)
                self.assertEqual(hit.status, 'hit')
            self.assertEqual(cold, build_candidate(files, motion, bvh, mapping, **options))

    def test_corruption_falls_back(self):
        with tempfile.TemporaryDirectory() as root:
            cache = PreparationCache(root, {})
            cache.save({'document': {'test': 1}})
            payload = next((Path(root)/'motion-preparation-cache').glob('*.payload'))
            payload.write_bytes(b'{}')
            self.assertIsNone(cache.load())
            self.assertEqual(cache.status, 'unavailable')


if __name__ == '__main__':
    unittest.main()
