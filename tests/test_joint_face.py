from copy import deepcopy
import json
import math
from pathlib import Path
import unittest

from autospine_workbench.targets.character43.joint_face import apply, defaults, inventory, normalize
from autospine_workbench.targets.character43.affine_pose import sample


def fixture():
    roles = ['eyewhite-l', 'irides-l', 'eyelash-l', 'eyebrow-l', 'mouth', 'body']
    document = dict(bones=[dict(name='root', x=2., y=3., rotation=20),
                           dict(name='head', parent='root', x=4., y=5., rotation=-31)],
                    slots=[], skins=[dict(name='default', attachments={})],
                    animations={'body': dict(bones={'head': {'rotate': [dict(time=0, value=0), dict(time=2, value=7)]}})})
    layers = []
    for i, role in enumerate(roles):
        slot = f'layer-{i:03d}'
        points = [(12, 8), (12, -12), (2, -12), (2, 8)]
        if role == 'irides-l':
            points = [(11, 4), (11, -8), (3, -8), (3, 4)]
        mesh = dict(type='mesh', width=20, height=10, path=slot,
                    uvs=[0, 0, 1, 0, 1, 1, 0, 1], triangles=[0, 1, 2, 0, 2, 3],
                    vertices=[v for x, y in points for v in (1, 1, x, y, 1.)])
        document['skins'][0]['attachments'][slot] = {slot: mesh}
        document['slots'].append(dict(name=slot, bone='head', attachment=slot))
        layers.append(dict(layer_id=slot, name=role))
    files = {'character-manifest.json': json.dumps(dict(layers=layers)).encode()}
    return files, document


class JointFaceTests(unittest.TestCase):
    def test_off_is_identity_and_neutral_setup_preserves_world_geometry(self):
        files, doc = fixture(); old = deepcopy(doc)
        result, updates, report = apply(files, doc, 'body', defaults(), [0, 1, 2])
        self.assertEqual(result, old); self.assertEqual(updates, {})
        config = defaults(); config['enabled'] = True; config['blink']['enabled'] = False
        result, _, report = apply(files, doc, 'body', config, [0, 1, 2])
        self.assertEqual(doc, old)
        for time in [0, .5, 1, 1.333, 2]:
            before, after = sample(doc, 'body', time)[0], sample(result, 'body', time)[0]
            self.assertLess(max(math.dist(p, q) for s in before for p, q in zip(before[s], after[s])), 1e-10)
        self.assertEqual(result['animations']['body']['bones']['head'], old['animations']['body']['bones']['head'])
        self.assertEqual(result['skins'][0]['attachments']['layer-005'], old['skins'][0]['attachments']['layer-005'])

    def test_blink_has_nonzero_mesh_but_hides_both_white_and_iris(self):
        files, doc = fixture(); config = defaults(); config['enabled'] = True
        result, _, report = apply(files, doc, 'body', config, [0, 2])
        closed = config['blink']['phase']+config['blink']['duration']*.4
        self.assertIn(closed, report['sample_times'])
        for slot in ('layer-000', 'layer-001'):
            keys = result['animations']['body']['slots'][slot]['alpha']
            self.assertEqual(next(k['value'] for k in keys if k['time'] == closed), 0)
        self.assertNotIn('layer-002', result['animations']['body']['slots'])
        for slot in ('layer-000', 'layer-001', 'layer-002'):
            self.assertAlmostEqual(report['channels'][slot]['min_scale_y'], .08)
        before = sample(doc, 'body', closed)[0]
        after = sample(result, 'body', closed)[0]
        def area(points):
            a, b, c = points[:3]
            return (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])
        self.assertAlmostEqual(area(after['layer-000'])/area(before['layer-000']), .08)

    def test_missing_lash_skips_blink_and_preserves_iris(self):
        files, doc = fixture()
        manifest = json.loads(files['character-manifest.json']); manifest['layers'][2]['name'] = 'decoration'
        files['character-manifest.json'] = json.dumps(manifest)
        config = defaults(); config['enabled'] = True
        result, _, report = apply(files, doc, 'body', config, [0, 2])
        self.assertIn('blink', report['missing'])
        self.assertFalse(result['animations']['body'].get('slots'))
        self.assertEqual(report['channels']['layer-001']['min_scale_y'], 1)

    def test_manual_keys_override_auto_blink_and_keep_exact_times(self):
        files, doc = fixture(); config = defaults(); config['enabled'] = True
        config['blink']['keys'] = [dict(time=0, value=0), dict(time=.5, value=0),
                                   dict(time=1.5, value=1), dict(time=2, value=0)]
        result, _, report = apply(files, doc, 'body', config, [0, 2])
        alpha = result['animations']['body']['slots']['layer-000']['alpha']
        self.assertEqual(next(k['value'] for k in alpha if k['time'] == .5), 1)
        self.assertIn(1.5, report['sample_times'])

    def test_old_deform_basis_conversion_preserves_all_animations_and_sparse_offsets(self):
        files, doc = fixture(); config = defaults(); config['enabled'] = True; config['blink']['enabled'] = False
        target = doc['animations']['body'].setdefault('attachments', {}).setdefault('default', {})
        target['layer-000'] = {'layer-000': {'deform': [dict(time=0, vertices=[1, 2]*4), dict(time=2, vertices=[2, 3]*4)]}}
        doc['animations']['other'] = deepcopy(doc['animations']['body'])
        doc['animations']['other']['attachments']['default']['layer-000']['layer-000']['deform'] = [
            dict(time=0, offset=2, vertices=[3, 4])]
        result, _, _ = apply(files, doc, 'body', config, [0, 1, 2])
        # Existing affine sampler does not pad sparse offsets; compare the padded equivalent.
        source = deepcopy(doc)
        source['animations']['other']['attachments']['default']['layer-000']['layer-000']['deform'][0] = dict(
            time=0, vertices=[0, 0, 3, 4, 0, 0, 0, 0])
        for animation in ('body', 'other'):
            for time in [0, .37, 1, 2]:
                before = sample(source, animation, time)[0]; after = sample(result, animation, time)[0]
                self.assertLess(max(math.dist(p, q) for s in before for p, q in zip(before[s], after[s])), 1e-10)

    def test_existing_alpha_is_preserved_and_config_is_strict(self):
        files, doc = fixture(); config = defaults(); config['enabled'] = True
        doc['animations']['body']['slots'] = {'layer-000': {'alpha': [dict(time=0, value=.3)]}}
        before = deepcopy(doc)
        result, _, report = apply(files, doc, 'body', config, [0, 2])
        self.assertIn('blink', report['missing'])
        self.assertEqual(result['animations']['body']['slots'], before['animations']['body']['slots'])
        self.assertEqual(doc, before)
        for bad in [dict(gaze={'x': float('nan')}), dict(mouth={'open': 2}), dict(anchors={'x': [0]}),
                    dict(turn={'keys': [dict(time=3, yaw=0)]})]:
            with self.assertRaises(ValueError):
                normalize(bad, 2)

    def test_real_alice_available_and_neutral_helpers_preserve_setup(self):
        root = Path('workspace/builds/animated-preview-v1/6e5c59db4ef072075b798efab12acf8ffdc883368a61a4bf3c1646305ef68b98')
        if not root.is_dir():
            self.skipTest('local Alice artifact unavailable')
        files = {'character-manifest.json': (root/'character-manifest.json').read_bytes()}
        doc = json.loads((root/'skeleton.json').read_bytes())
        observed = inventory(files, doc)
        self.assertTrue(all(observed['capabilities'].values()))
        config = defaults(); config['enabled'] = True; config['blink']['enabled'] = False
        result, _, report = apply(files, doc, 'idle', config, [0, 1, 2])
        for time in [0, .27, 1, 2]:
            before = sample(doc, 'idle', time)[0]; after = sample(result, 'idle', time)[0]
            self.assertLess(max(math.dist(p, q) for s in before for p, q in zip(before[s], after[s])), 1e-9)
        self.assertEqual(len(report['affected_slots']), 9)

    def test_existing_attachment_switch_is_reported_and_left_untouched(self):
        files, doc = fixture(); config = defaults(); config['enabled'] = True
        doc['animations']['body']['slots'] = {'layer-001': {'attachment': [dict(time=0, name='layer-001')]}}
        before = deepcopy(doc)
        result, _, report = apply(files, doc, 'body', config, [0, 1, 2])
        part = next(p for p in report['inventory']['parts'] if p['slot'] == 'layer-001')
        self.assertFalse(part['available'])
        self.assertEqual(part['reason'], 'facial_existing_attachment_timeline_requires_mapping')
        self.assertEqual(result['skins'][0]['attachments']['layer-001'], before['skins'][0]['attachments']['layer-001'])
        self.assertEqual(result['animations']['body']['slots']['layer-001'], before['animations']['body']['slots']['layer-001'])


if __name__ == '__main__':
    unittest.main()
