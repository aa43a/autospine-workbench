"""Whole-character source preservation and conservative skirt admission."""
from copy import deepcopy
from hashlib import sha256
from io import BytesIO
import importlib.util
import json
import unittest

from autospine_workbench.automation.storage_io import canonical_bytes
from autospine_workbench.targets.character43.affine_pose import sample
from autospine_workbench.targets.character43.skirt_candidate import generate
from autospine_workbench.targets.character43.skirt_contact import propose
from autospine_workbench.asset.planning.skirt_mesh import build_skirt_mesh, validate_skirt_mesh


def fixture():
    from PIL import Image
    bones = [dict(name='root', x=0, y=0, rotation=0),
             dict(name='pelvis', parent='root', x=0, y=-20, rotation=0),
             dict(name='thigh_l', parent='pelvis', x=-20, y=-20, rotation=0),
             dict(name='thigh_r', parent='pelvis', x=20, y=-20, rotation=0),
             dict(name='chest', parent='pelvis', x=0, y=20, rotation=0)]
    slots = [dict(name=n, bone='root', attachment=n) for n in ('skirt', 'shirt')]
    attachments = {}; files = {}
    for name, height in [('skirt', 100), ('shirt', 40)]:
        vertices = []
        for x, y in [(-40, 0), (40, 0), (40, -height), (-40, -height)]:
            vertices.extend([1, 0, x, y, 1.])
        attachments[name] = {name: dict(type='mesh', path=name, width=80, height=height,
            vertices=vertices, uvs=[0, 0, 1, 0, 1, 1, 0, 1], triangles=[0, 1, 2, 0, 2, 3])}
        stream = BytesIO(); Image.new('RGBA', (80, height), (120, 70, 10, 255)).save(stream, format='PNG')
        files['images/'+name+'.png'] = stream.getvalue()
    doc = dict(skeleton={'spine': '4.3.26'}, bones=bones, slots=slots,
               skins=[dict(name='default', attachments=attachments)],
               animations={'idle': {'bones': {'root': {'translate': [
                   dict(time=0, x=0, y=0), dict(time=1, x=3, y=2), dict(time=2, x=0, y=0)]}}}})
    files['skeleton.json'] = canonical_bytes(doc)
    editor = deepcopy(doc); editor['skeleton']['images'] = './images/'
    files['editor/skeleton.json'] = canonical_bytes(editor)
    files['skeleton.atlas'] = b'preserved atlas bytes'
    files['numeric-reference.json'] = canonical_bytes(dict(skeleton_sha256=sha256(files['skeleton.json']).hexdigest(),
        animations={'idle': [dict(time=i/8, vertices=sample(doc, 'idle', i/8)[0]) for i in range(17)]}))
    files['character-manifest.json'] = canonical_bytes(dict(authority='none', production_authorized=False, layers=[
        dict(layer_id='skirt', name='bottomwear', state='static_reference',
             binding_decision={'action': 'pending'}, regions=[{'region_id': 'skirt'}]),
        dict(layer_id='shirt', name='topwear', state='rigid_reviewed',
             binding_decision={'action': 'bind'}, regions=[{'region_id': 'shirt'}])]))
    return files


@unittest.skipUnless(importlib.util.find_spec('PIL'), 'optional Pillow')
class CharacterSkirtTests(unittest.TestCase):
    def test_setup_and_source_preservation_and_real_deformation(self):
        files = fixture(); before = deepcopy(files)
        output, report = generate(files, 'a'*64, ['skirt'], step=16)
        self.assertEqual(files, before)
        self.assertEqual(generate(files, 'a'*64, ['skirt'], step=16)[0], output)
        self.assertTrue(report['geometry_passed']); self.assertFalse(report['selected'])
        self.assertLess(report['setup_error_px'], 1e-8)
        old = json.loads(files['skeleton.json']); new = json.loads(output['skeleton.json'])
        self.assertEqual(old['slots'], new['slots'])
        self.assertEqual(old['bones'], new['bones'][:len(old['bones'])])
        self.assertEqual(old['animations']['idle']['bones']['root'], new['animations']['idle']['bones']['root'])
        for key in ('images/skirt.png', 'images/shirt.png', 'skeleton.atlas'):
            self.assertEqual(output[key], files[key])
        self.assertEqual(json.loads(output['editor/skeleton.json'])['skeleton']['images'], './images/')
        base, _ = sample(new, 'idle', 0); moved, _ = sample(new, 'idle', .5)
        self.assertGreater(max(abs((b[0]-a[0])-1.5) for a, b in zip(base['skirt'], moved['skirt'])), .1)
        ledger = json.loads(output['character-manifest.json'])['layers'][0]
        self.assertEqual(ledger['binding_decision'], {'action': 'pending'})
        self.assertIn('skirt_waist_anchor_review_required', ledger['reason_codes'])

    def test_missing_torso_and_wrong_scope_fail_closed(self):
        files = fixture()
        with self.assertRaisesRegex(ValueError, 'selection_unsupported'):
            generate(files, 'a'*64, ['shirt'])
        doc = json.loads(files['character-manifest.json']); doc['layers'][1]['state'] = 'static_reference'
        files['character-manifest.json'] = canonical_bytes(doc)
        with self.assertRaisesRegex(ValueError, 'reviewed_torso_missing'):
            generate(files, 'a'*64, ['skirt'])

    def test_contact_is_upper_sustained_overlap_not_hip_or_isolated_noise(self):
        from PIL import Image
        alpha = Image.new('L', (80, 100), 255); torso = Image.new('L', (80, 100))
        for y in [1, *range(10, 41)]:
            for x in range(80): torso.putpixel((x, y), 255)
        result = propose(alpha, (-40, 0), [(torso, (-40, 0))], [(-20, -40), (20, -40)])
        self.assertEqual(result['waist_y'], 10)
        self.assertEqual(result['status'], 'needs_review')
        with self.assertRaisesRegex(ValueError, 'unobservable'):
            propose(alpha, (-40, 0), [], [(-20, -40), (20, -40)])

    def test_validator_rejects_changed_weights_and_source(self):
        alpha = [[255]*10 for _ in range(20)]
        mesh = build_skirt_mesh(alpha, 2)
        self.assertEqual(validate_skirt_mesh(alpha, 2, mesh), mesh)
        mesh['influences'][0][0]['weight'] = .5
        with self.assertRaisesRegex(ValueError, 'source_mismatch'):
            validate_skirt_mesh(alpha, 2, mesh)
        mesh = build_skirt_mesh(alpha, 2); mesh['influences'][0][0]['weight'] = True
        with self.assertRaisesRegex(ValueError, 'source_mismatch'):
            validate_skirt_mesh(alpha, 2, mesh)
        tiny = build_skirt_mesh(alpha, 1-1e-15, step=1)
        for weights in tiny['influences']:
            self.assertTrue(all(w['weight'] > 0 for w in weights))
            self.assertAlmostEqual(sum(w['weight'] for w in weights), 1.)

    def test_source_reference_identity_and_slot_inventory(self):
        for kind in ('hash', 'slot'):
            files = fixture(); reference = json.loads(files['numeric-reference.json'])
            if kind == 'hash': reference['skeleton_sha256'] = '0'*64
            else: del reference['animations']['idle'][0]['vertices']['shirt']
            files['numeric-reference.json'] = canonical_bytes(reference)
            with self.assertRaisesRegex(ValueError, 'source_mismatch|slot_inventory'):
                generate(files, 'a'*64, ['skirt'])

    def test_existing_deform_rejected(self):
        files = fixture(); doc = json.loads(files['skeleton.json'])
        doc['animations']['idle']['attachments'] = {'default': {'skirt': {'skirt': {
            'deform': [dict(time=0, vertices=[0.]*8), dict(time=2, vertices=[0.]*8)]}}}}
        files['skeleton.json'] = canonical_bytes(doc)
        reference = json.loads(files['numeric-reference.json'])
        reference['skeleton_sha256'] = sha256(files['skeleton.json']).hexdigest()
        files['numeric-reference.json'] = canonical_bytes(reference)
        with self.assertRaisesRegex(ValueError, 'existing_deform'):
            generate(files, 'a'*64, ['skirt'])

    def test_review_timeline_uses_exact_capture_and_safe_frame_paths(self):
        from autospine_workbench.targets.character43.skirt_review import render
        from autospine_workbench.resolved_project import canonical_sha256
        output, _ = generate(fixture(), 'a'*64, ['skirt'])
        capture = dict(authority='none', bundle_sha256=canonical_sha256({n: sha256(raw).hexdigest() for n, raw in output.items()}),
                       info=dict(width=120, height=150, left=-60, bottom=-120),
                       results=[dict(animation='idle', index=0, time=0)],
                       screenshots=[dict(animation='idle', index=0, file='frames/idle-0.png')])
        html = render(output, capture).decode()
        self.assertIn('已捕获帧时间轴', html)
        self.assertIn('bones.style.display', html)
        self.assertIn('没有自动采用', html)
        capture['screenshots'][0]['file'] = '../elsewhere.png'
        with self.assertRaisesRegex(ValueError, 'frame_path'): render(output, capture)
        capture['bundle_sha256'] = '0'*64
        with self.assertRaisesRegex(ValueError, 'capture_source'): render(output, capture)

    def test_one_unobservable_layer_does_not_discard_other_skirt(self):
        files = fixture(); doc = json.loads(files['skeleton.json'])
        mesh = deepcopy(doc['skins'][0]['attachments']['skirt']['skirt']); mesh['path'] = 'skirt2'
        for i in range(2, len(mesh['vertices']), 5): mesh['vertices'][i] += 200
        doc['skins'][0]['attachments']['skirt2'] = {'skirt2': mesh}
        doc['slots'].append(dict(name='skirt2', bone='root', attachment='skirt2'))
        files['images/skirt2.png'] = files['images/skirt.png']
        files['skeleton.json'] = canonical_bytes(doc)
        ref = json.loads(files['numeric-reference.json']); ref['skeleton_sha256'] = sha256(files['skeleton.json']).hexdigest()
        for frame in ref['animations']['idle']: frame['vertices'] = sample(doc, 'idle', frame['time'])[0]
        files['numeric-reference.json'] = canonical_bytes(ref)
        manifest = json.loads(files['character-manifest.json'])
        manifest['layers'].append(dict(layer_id='skirt2', name='bottomwear-front', state='static_reference',
            binding_decision={'action': 'pending'}, regions=[{'region_id': 'skirt2'}]))
        files['character-manifest.json'] = canonical_bytes(manifest)
        output, report = generate(files, 'a'*64, ['skirt', 'skirt2'])
        self.assertEqual([r['layer_id'] for r in report['rows']], ['skirt'])
        self.assertEqual(report['blocked_layers'], [dict(layer_id='skirt2', reason_code='skirt_waist_contact_unobservable')])
        self.assertEqual(json.loads(output['skeleton.json'])['skins'][0]['attachments']['skirt2']['skirt2'], mesh)
        self.assertEqual(json.loads(output['character-manifest.json'])['layers'][-1]['state'], 'static_reference')
        _, all_blocked = generate(files, 'a'*64, ['skirt2'])
        self.assertEqual(all_blocked['status'], 'blocked')
        self.assertEqual(all_blocked['rows'], [])
