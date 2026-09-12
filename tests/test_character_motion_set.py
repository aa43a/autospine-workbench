import json
import unittest
from autospine_workbench.targets.character43.motion_set import combine
from autospine_workbench.targets.character43.motion_composition import compose
from test_character_motion_composition import package


class MotionSetTests(unittest.TestCase):
    def test_multiple_clips_retain_references_and_original_character(self):
        base = package('existing'); a = package('idle'); b = package('walk')
        a['motion-review.json'] = b'{"visual_status":"needs_review"}'
        result = combine(base, 'a'*64, [('b'*64, a), ('c'*64, b)])
        self.assertEqual(result, combine(base, 'a'*64, [('c'*64, b), ('b'*64, a)]))
        self.assertEqual(json.loads(result['numeric-reference.json'])['animations']['walk'],
                         json.loads(b['numeric-reference.json'])['animations']['walk'])
        self.assertEqual(result['motion-set-sources/'+'b'*64+'/motion-review.json'], a['motion-review.json'])
        merged = compose(base, result, 'a'*64, 'd'*64)
        self.assertEqual(merged['motion-candidates/'+'d'*64+'/motion-set-sources/'+'b'*64+'/motion-review.json'],
                         a['motion-review.json'])
        self.assertEqual(set(json.loads(merged['skeleton.json'])['animations']), {'existing', 'idle', 'walk'})
        self.assertEqual(json.loads(merged['character-manifest.json'])['layers'],
                         json.loads(base['character-manifest.json'])['layers'])

    def test_conflicting_clips_and_sources_rejected(self):
        with self.assertRaisesRegex(ValueError, 'duplicate_clip'):
            combine(package('old'), 'a'*64, [('b'*64, package('idle')), ('c'*64, package('idle'))])
        with self.assertRaisesRegex(ValueError, 'duplicate_source'):
            combine(package('old'), 'a'*64, [('b'*64, package('idle')), ('b'*64, package('walk'))])
        with self.assertRaisesRegex(ValueError, 'composition_source'):
            combine(package('old'), 'e'*64, [('b'*64, package('idle'))])

    def test_changed_texture_cannot_be_grouped(self):
        motion = package('walk'); motion['images/leg.png'] = b'wrong'
        with self.assertRaisesRegex(ValueError, 'texture_changed'):
            combine(package('old'), 'a'*64, [('b'*64, motion)])
