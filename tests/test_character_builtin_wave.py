import json
import unittest
from hashlib import sha256
from autospine_workbench.automation.storage_io import canonical_bytes as raw
from autospine_workbench.targets.character43.builtin_wave_candidate import generate
from autospine_workbench.targets.character43.motion_composition import compose
from autospine_workbench.targets.character43.affine_pose import sample
from test_character_wave import WaveTests


def source(mixed=False):
    doc = WaveTests().fixture()
    # Fixed pelvis vertex paired with moving arm vertices creates a real stretch failure.
    doc['skins'] = [{'attachments': {'arm': {'arm': {'triangles': [0, 1, 2],
        'vertices': [1, 0 if mixed else 3, 0, 0, 1, 1, 3, 1, 0, 1, 1, 3, 0, 1, 1]}}}}]
    files = {'skeleton.json': raw(doc), 'images/arm.png': b'texture', 'skeleton.atlas': b'atlas',
             'character-manifest.json': raw({'layers': [{'state': 'pending'}]})}
    files['numeric-reference.json'] = raw(dict(skeleton_sha256=sha256(files['skeleton.json']).hexdigest(),
        animations={'old': [dict(time=t, vertices=sample(doc, 'old', t)[0]) for t in (0, 2)]}))
    return files


class BuiltinWaveTests(unittest.TestCase):
    def test_rigid_attachment_follows_wave_and_preserves_previous_clip(self):
        base = source(); before = dict(base)
        candidate = generate(base, 'a'*64)
        self.assertEqual(base, before)
        self.assertEqual(candidate, generate(base, 'a'*64))
        self.assertTrue(json.loads(candidate['deformation.json'])['passed'])
        result = compose(base, candidate, 'a'*64, 'b'*64)
        self.assertEqual(set(json.loads(result['skeleton.json'])['animations']), {'old', 'wave-left'})
        frames = json.loads(candidate['numeric-reference.json'])['animations']['wave-left']
        self.assertIn(.4, [f['time'] for f in frames])
        self.assertNotEqual(frames[0]['vertices'], frames[len(frames)//2]['vertices'])

    def test_failed_candidate_cannot_be_composed_or_hide_failed_slot(self):
        base = source(mixed=True)
        candidate = generate(base, 'a'*64)
        self.assertEqual(json.loads(candidate['character-manifest.json'])['status'], 'blocked')
        self.assertEqual(json.loads(candidate['motion-review.json'])['failing_slots'], ['arm'])
        with self.assertRaisesRegex(ValueError, 'composition_geometry'):
            compose(base, candidate, 'a'*64, 'b'*64)

    def test_existing_wave_is_not_replaced(self):
        base = source(); doc = json.loads(base['skeleton.json'])
        doc['animations']['wave-left'] = {}; base['skeleton.json'] = raw(doc)
        with self.assertRaisesRegex(ValueError, 'name_conflict'):
            generate(base, 'a'*64)
