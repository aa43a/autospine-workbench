"""Generic onboarding preserves uncertainty and does not require tmp HTML history."""
from copy import deepcopy
from hashlib import sha256
from io import BytesIO
from types import SimpleNamespace
import unittest
from PIL import Image

from autospine_workbench.automation.sleeve_onboarding_source import build_inputs, SleeveOnboardingError
from autospine_workbench.asset.planning.sleeve_weights import build as weights
from autospine_workbench.resolved_project import canonical_sha256


def inputs():
    image = Image.new('RGBA', (32, 48))
    for y in range(48):
        for x in range(3, 10):
            image.putpixel((x, y), (100, 80, 90, 255))
    # Unrelated disconnected piece must stay unassigned, not silently dropped.
    image.putpixel((25, 25), (100, 80, 90, 255))
    image.putpixel((30, 30), (100, 80, 90, 4))
    buffer = BytesIO(); image.save(buffer, format='PNG'); raw = buffer.getvalue()
    layer = dict(layer_id='layer', name='sleeve-l', bbox=[100, 200, 132, 248],
                 image_sha256=sha256(raw).hexdigest())
    ids = ['upperarm_l', 'forearm_l', 'hand_l']
    skeleton = dict(status='candidate_requires_review', bones=[dict(id=b,
        parent_id=ids[i-1] if i else 'chest', head_xy=[106, 200+16*i],
        tail_xy=[106, 216+16*i], world_rotation_degrees=90) for i, b in enumerate(ids)])
    return SimpleNamespace(candidate={'layers': [layer]}, images={'layer': raw}, skeleton=skeleton,
        bindings={'bindings': [{'layer_id': 'layer', 'options': [dict(mode='mesh_chain', bone_ids=ids)]}]},
        draft={'records': []}, source_addresses={'input_identity_sha256': 'a'*64})


class SleeveOnboardingSourceTests(unittest.TestCase):
    def test_fresh_source_editable_with_unknown_components_preserved(self):
        data = inputs(); original = deepcopy(data.__dict__)
        source, regions, draft, aux = build_inputs(data, 'arbitrary-import')
        self.assertEqual(source['schema'], 'autospine.component-mesh-candidates/v1')
        self.assertEqual(regions['schema'], 'autospine.sleeve-regions/v2')
        self.assertEqual(len(source['records']), 3)
        self.assertEqual(len(regions['records']), 1)
        self.assertEqual(aux['ownership']['records'][1]['status'], 'pending')
        self.assertEqual(aux['ownership']['records'][2]['status'], 'pending')
        self.assertFalse(aux['origin']['human_reviewed'])
        self.assertEqual(aux['plan']['profile'], 'sleeve-onboarding-v1')
        self.assertEqual(source['sources']['plan_sha256'], canonical_sha256(aux['plan']))
        self.assertTrue(all(a['origin'] == 'pending' for r in draft['records'] for a in r['assignments']))
        self.assertEqual(data.__dict__, original)
        self.assertEqual(build_inputs(data, 'arbitrary-import'), (source, regions, draft, aux))
        result = weights(source, regions, draft, data.skeleton)
        self.assertEqual(len(result['records']), 3)
        self.assertFalse(result['production_authorized'])

    def test_missing_joint_review_or_arm_options_is_explicit(self):
        data = inputs(); data.skeleton['status'] = 'blocked'
        with self.assertRaises(SleeveOnboardingError) as error:
            build_inputs(data, 'new')
        self.assertEqual(error.exception.reason_code, 'sleeve_source_joints_unreviewed')
        data = inputs(); data.bindings['bindings'][0]['options'] = []
        with self.assertRaises(SleeveOnboardingError) as error:
            build_inputs(data, 'new')
        self.assertEqual(error.exception.reason_code, 'sleeve_mesh_review_required')
        self.assertTrue(any(b.get('reason_code') == 'sleeve_arm_chain_required' for b in error.exception.blockers))

    def test_nonarm_semantic_is_not_overridden_by_name(self):
        data = inputs(); data.candidate['layers'][0]['semantic'] = 'accessory.ribbon'
        with self.assertRaises(SleeveOnboardingError) as error:
            build_inputs(data, 'new')
        self.assertEqual(error.exception.reason_code, 'sleeve_no_eligible_layers')


if __name__ == '__main__':
    unittest.main()
