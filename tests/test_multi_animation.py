from copy import deepcopy
from hashlib import sha256
import json
from unittest import TestCase

from autospine_workbench.automation.storage_io import canonical_bytes
from autospine_workbench.resolved_project import canonical_sha256
from autospine_workbench.targets.character43.multi_animation import build
from autospine_workbench.targets.character43.numeric_reference import read
from autospine_workbench.targets.character43.affine_pose import sample
from test_joint_face import fixture


def source(name, angle=7):
    files, doc = fixture()
    doc['animations']['body']['bones']['head']['rotate'][-1]['value'] = angle
    files['skeleton.json'] = canonical_bytes(doc)
    digest = sha256(files['skeleton.json']).hexdigest()
    setup = deepcopy(doc); setup['animations']['body'] = {}
    points = sample(setup, 'body', 0)[0]
    files['rig-setup-reference.json'] = canonical_bytes(dict(skeleton_sha256=digest, time=0, vertices=points))
    files['numeric-reference.json'] = canonical_bytes(dict(skeleton_sha256=digest, animations={
        'body': [dict(time=t, vertices=sample(doc, 'body', t)[0]) for t in (0, 1, 2)]}))
    files['skeleton.atlas'] = b'textures/test.png'
    files['textures/test.png'] = b'pixels'
    files['motion-review.json'] = canonical_bytes(dict(issues=[{'reason_code': 'source_limit'}]))
    return address(name, files)


def address(name, files):
    return dict(name=name, files=files, artifact_sha256=canonical_sha256({n: sha256(v).hexdigest() for n, v in files.items()}))


class MultiAnimationTests(TestCase):
    def test_two_different_tracks_keep_exact_samples_and_separate_evidence(self):
        a, b = source('breathing'), source('wave', 50)
        output, report = build([a, b])
        doc = json.loads(output['skeleton.json']); ref = read(output)
        self.assertEqual(set(doc['animations']), {'breathing-01', 'wave-01'})
        for item in (a, b):
            exported = report['sources'][0 if item is a else 1]['animation_mapping']['body']
            original = json.loads(item['files']['skeleton.json'])
            self.assertEqual(doc['animations'][exported], original['animations']['body'])
            self.assertEqual(ref['animations'][exported], read(item['files'])['animations']['body'])
            self.assertEqual(sample(doc, exported, 1)[0], sample(original, 'body', 1)[0])
            self.assertEqual(output[f"sources/{item['name']}/motion-review.json"], item['files']['motion-review.json'])
        self.assertEqual(report['visual_status'], 'not_reviewed')
        self.assertEqual(report['status'], 'requires_runtime_validation')
        self.assertNotIn('joint-animation.json', output)
        self.assertEqual(json.loads(output['character-manifest.json'])['animations'], sorted(doc['animations']))

    def test_changed_bind_structure_or_texture_is_rejected(self):
        a, b = source('one'), source('two')
        b['files']['textures/test.png'] = b'different'
        b = address('two', b['files'])
        with self.assertRaisesRegex(ValueError, 'incompatible_texture_assets'):
            build([a, b])

    def test_reference_identity_and_aliases_are_required(self):
        a, b = source('one'), source('two')
        reference = read(b['files']); reference['skeleton_sha256'] = '0' * 64
        b['files']['numeric-reference.json'] = canonical_bytes(reference)
        b = address('two', b['files'])
        with self.assertRaisesRegex(ValueError, 'reference_source'):
            build([a, b])
        with self.assertRaisesRegex(ValueError, 'names_invalid'):
            build([a, source('one')])
        with self.assertRaisesRegex(ValueError, 'names_invalid'):
            build([a, source('../unsafe')])
