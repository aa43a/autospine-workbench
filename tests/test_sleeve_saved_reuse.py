"""An unrelated source closure can change; no annotation evidence may change."""
from copy import deepcopy
import unittest

from test_sleeve_onboarding_source import inputs
from autospine_workbench.automation.sleeve_onboarding_source import build_inputs
from autospine_workbench.automation.sleeve_saved_reuse import reuse


class SavedReuseTests(unittest.TestCase):
    def test_only_source_closure_change_is_allowed(self):
        _, candidate, draft, _ = build_inputs(inputs(), 'fresh')
        previous = dict(saved=True, source_sha256='a'*64, revision=2)
        current = deepcopy(candidate); current['source_sha256'] = 'b'*64
        result = reuse(previous, candidate, draft, current, 'a'*64)
        self.assertEqual(result[0]['records'], draft['records'])
        self.assertFalse(result[1]['motion_review_reused'])
        mutations = [
            lambda c: c.update(skeleton_sha256='f'*64),
            lambda c: c.update(profile='different'),
            lambda c: c['records'][0].update(source_image_sha256='e'*64),
            lambda c: c['records'][0]['vertices_xy'][0].__setitem__(0, 999),
            lambda c: c['records'][0]['triangles'][0].reverse(),
            lambda c: c['records'][0]['suggestions'][0].update(suggested_role='unknown'),
            lambda c: c['records'][0].update(bone_ids=['upperarm_r', 'forearm_r', 'hand_r']),
        ]
        for mutate in mutations:
            changed = deepcopy(current); mutate(changed)
            self.assertNotEqual(changed, current)
            self.assertIsNone(reuse(previous, candidate, draft, changed, 'a'*64))
        self.assertIsNone(reuse(dict(previous, saved=False), candidate, draft, current, 'a'*64))
        self.assertIsNone(reuse(previous, candidate, draft, current, 'c'*64))
