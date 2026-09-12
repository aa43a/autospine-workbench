import json
import unittest
from hashlib import sha256
from unittest.mock import patch
from autospine_workbench.automation.storage_io import canonical_bytes as raw
from autospine_workbench.targets.character43.builtin_idle_candidate import generate
from autospine_workbench.targets.character43.motion_composition import compose
from autospine_workbench.targets.character43.motionir_candidate import sample
from test_character_motionir_candidate import fixture


def source():
    doc = fixture()
    for name in ('spine', 'chest', 'head'):
        doc['bones'].append(dict(name=name, parent='root', x=0, y=0, rotation=0))
    doc['skins'][0]['attachments']['point']['point'].update(
        triangles=[0, 1, 2], vertices=[1, 0, 0, 0, 1, 1, 0, 10, 0, 1, 1, 0, 0, 10, 1])
    result = {'skeleton.json': raw(doc), 'images/point.png': b'texture', 'skeleton.atlas': b'atlas',
              'character-manifest.json': raw(dict(layers=[{'state': 'pending'}]))}
    result['numeric-reference.json'] = raw(dict(skeleton_sha256=sha256(result['skeleton.json']).hexdigest(),
        animations={'existing': [dict(time=t, vertices=sample(doc, 'existing', t)[0]) for t in (0, 2)]}))
    return result


class IdleTests(unittest.TestCase):
    def test_loop_determinism_and_preserved_source_clips(self):
        base = source(); before = dict(base)
        candidate = generate(base, 'a'*64, samples=4)
        self.assertEqual(candidate, generate(base, 'a'*64, samples=4))
        self.assertEqual(base, before)
        frames = json.loads(candidate['numeric-reference.json'])['animations']['idle']
        self.assertEqual(frames[0]['vertices'], frames[-1]['vertices'])
        self.assertIn(.5, [f['time'] for f in frames])
        self.assertNotEqual(frames[0]['vertices'], frames[2]['vertices'])
        merged = compose(base, candidate, 'a'*64, 'b'*64)
        self.assertEqual(json.loads(merged['skeleton.json'])['animations']['existing'],
                         json.loads(base['skeleton.json'])['animations']['existing'])
        self.assertEqual(json.loads(merged['character-manifest.json'])['layers'], [{'state': 'pending'}])

    def test_invalid_grid_and_open_loop_rejected(self):
        for count in (True, 2, 1026):
            with self.assertRaisesRegex(ValueError, 'samples_invalid'):
                generate(source(), 'a'*64, count)
        from autospine_workbench.motion_builtin import build_builtin_motion
        motion = build_builtin_motion('idle').document
        motion['tracks'][1]['keys'][-1]['value'] = [1., 0.]
        with patch('autospine_workbench.targets.character43.builtin_idle_candidate.build_builtin_motion') as builder:
            builder.return_value.document = motion
            with self.assertRaisesRegex(ValueError, 'endpoints must match'):
                generate(source(), 'a'*64)
