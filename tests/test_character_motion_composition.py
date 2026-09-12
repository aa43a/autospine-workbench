from hashlib import sha256
import json
import unittest
from autospine_workbench.automation.storage_io import canonical_bytes as raw
from autospine_workbench.targets.character43.motion_composition import compose


def package(name):
    doc = dict(bones=[{'name': 'root'}], slots=[{'name': 'leg'}], skins=[{'attachments': {'leg': {'leg': {
        'triangles': [0, 1, 2], 'vertices': [1, 0, 0, 0, 1, 1, 0, 1, 0, 1, 1, 0, 0, 1, 1]}}}}], animations={name: {}})
    frames = [dict(time=t, vertices={'leg': [[0, 0], [1, 0], [0, 1]]}) for t in (0, 1)]
    files = {'skeleton.json': raw(doc), 'images/leg.png': b'texture', 'skeleton.atlas': b'atlas'}
    files['numeric-reference.json'] = raw(dict(skeleton_sha256=sha256(files['skeleton.json']).hexdigest(), animations={name: frames}))
    files['character-manifest.json'] = raw(dict(source_character_sha256='a'*64, authority='none', production_authorized=False,
        layers=[{'layer_id': 'source', 'state': 'partial'}], animations=[name]))
    return files


class MotionCompositionTests(unittest.TestCase):
    def test_preserves_character_ledger_and_existing_frames(self):
        base, motion = package('idle'), package('walk'); before = dict(base)
        result = compose(base, motion, 'a'*64, 'b'*64)
        self.assertEqual(base, before)
        self.assertEqual(set(json.loads(result['skeleton.json'])['animations']), {'idle', 'walk'})
        ref = json.loads(result['numeric-reference.json'])
        self.assertEqual(ref['animations']['idle'], json.loads(base['numeric-reference.json'])['animations']['idle'])
        manifest = json.loads(result['character-manifest.json'])
        self.assertEqual(manifest['layers'], json.loads(base['character-manifest.json'])['layers'])
        self.assertEqual(manifest['qa']['runtime_status'], 'not_run')
        self.assertFalse(manifest['full_character_animation'])

    def test_wrong_source_texture_and_duplicate_motion_rejected(self):
        base, motion = package('idle'), package('walk')
        with self.assertRaisesRegex(ValueError, 'source'):
            compose(base, motion, 'c'*64, 'b'*64)
        with self.assertRaisesRegex(ValueError, 'texture_changed'):
            compose(base, {**motion, 'images/leg.png': b'changed'}, 'a'*64, 'b'*64)
        with self.assertRaisesRegex(ValueError, 'duplicate'):
            compose(base, package('idle'), 'a'*64, 'b'*64)

    def test_changed_rig_cannot_reintroduce_old_region(self):
        motion = package('walk'); doc = json.loads(motion['skeleton.json'])
        doc['slots'].append({'name': 'excluded-residual'}); motion['skeleton.json'] = raw(doc)
        with self.assertRaisesRegex(ValueError, 'rig_changed'):
            compose(package('idle'), motion, 'a'*64, 'b'*64)
