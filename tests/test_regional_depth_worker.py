from copy import deepcopy
import json
import unittest
from unittest.mock import patch
from test_motion_target_intake import inputs
from autospine_workbench.automation.motion_target_worker import build_candidate
from autospine_workbench.automation.storage_io import canonical_bytes
from autospine_workbench.targets.character43.regional_depth_profile import PROFILE
from autospine_workbench.targets.character43.depth_region_partition import build
from autospine_workbench.targets.character43.regional_depth_contract import verify


class RegionalWorkerTests(unittest.TestCase):
    def test_selected_partition_references_match_and_keep_original_artwork(self):
        files, motion, bvh, mapping = inputs()
        doc = json.loads(files['skeleton.json'])
        doc['skins'][0]['attachments']['point']['point'].update(type='mesh', uvs=[0, 0, 1, 0, 0, 1])
        doc['slots'] = [dict(name='point', attachment='point', bone='root')]
        files['skeleton.json'] = canonical_bytes(doc); before = deepcopy(files)

        def apply(document, files, animation, depth, *args, **kwargs):
            candidate, partition = build(document, ['point'])
            order = dict(status='no_visible_order_change', failures=[], frames=[])
            depth.update(profile=PROFILE, selected=True, status='depth_order_sampled_candidate',
                         order=order, regional=dict(partition=partition))
            return candidate, depth, verify(document, candidate, animation, ['point'], order)

        with patch('autospine_workbench.targets.character43.regional_depth_profile.apply', side_effect=apply):
            result, _, geometry = build_candidate(files, motion, bvh, mapping,
                character_digest='a'*64, motion_digest='b'*64, depth_review_profile=PROFILE)
        self.assertTrue(geometry['passed'])
        self.assertEqual(files, before)
        self.assertEqual(result['images/point.png'], files['images/point.png'])
        skeleton = json.loads(result['skeleton.json'])
        slots = {s['name'] for s in skeleton['slots']}
        setup = json.loads(result['rig-setup-reference.json'])['vertices']
        self.assertEqual(set(setup), slots)
        self.assertNotIn('point', slots)
        self.assertEqual(skeleton['bones'], doc['bones'])
        self.assertIn('motion-regional-transform.json', result)
