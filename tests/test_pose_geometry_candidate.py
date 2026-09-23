from copy import deepcopy
from hashlib import sha256
import json
import unittest

from test_pose_geometry_patch import fixture
from autospine_workbench.resolved_project import canonical_sha256
from autospine_workbench.automation.storage_io import canonical_bytes
from autospine_workbench.targets.character43.affine_pose import sample
from autospine_workbench.targets.character43.numeric_reference import read
from autospine_workbench.targets.character43.pose_geometry_candidate import build


def bundle(other_failure=False):
    doc, request = fixture()
    doc['skins'][0]['name'] = 'default'
    if other_failure:
        channels = doc['animations']['move']['attachments']['default']
        channels['other'] = {'other': deepcopy(channels['leg']['leg'])}
    request['document_sha256'] = canonical_sha256(doc)
    raw = canonical_bytes(doc)
    digest = sha256(raw).hexdigest()
    setup = sample(dict(doc, animations={'setup': {}}), 'setup', 0)[0]
    files = {'skeleton.json': raw, 'skeleton.atlas': b'atlas', 'images/body.png': b'texture',
             'rig-setup-reference.json': canonical_bytes(dict(skeleton_sha256=digest, vertices=setup)),
             'numeric-reference.json': canonical_bytes(dict(skeleton_sha256=digest, animations={
                 'move': [dict(time=t, vertices=sample(doc, 'move', t)[0]) for t in (0, .37, 1, 2)]})),
             'motion-ir.json': canonical_bytes(dict(duration_ticks=2, ticks_per_second=1, markers=[])),
             'motion-contact.json': b'{}', 'deformation.json': b'{"passed":false}',
             'motion-review.json': canonical_bytes(dict(reference_length_px=10, status='accepted',
                 selected=True, issues=[dict(stage='projection', reason_code='source_limitation')])),
             'motion-depth.json': b'old depth', 'runtime.json': b'old runtime',
             'character-manifest.json': b'{"selected":true,"production_authorized":true}'}
    return files, dict(animation='move', slot='leg', pose_geometry=request)


class PoseGeometryCandidateTests(unittest.TestCase):
    def test_fresh_whole_scene_evidence_and_exact_inputs(self):
        files, plan = bundle()
        original = deepcopy(files)
        output, evidence, geometry = build(files, plan)
        self.assertEqual(files, original)
        self.assertTrue(geometry['passed'])
        self.assertEqual({r['slot'] for r in geometry['records']}, {'leg', 'other'})
        self.assertIn(.37, [r['time'] for r in read(output)['animations']['move']])
        for name in ('skeleton.atlas', 'images/body.png', 'motion-ir.json'):
            self.assertEqual(files[name], output[name])
        self.assertNotIn('motion-depth.json', output)
        self.assertNotIn('runtime.json', output)
        self.assertEqual(evidence['runtime_status'], 'not_evaluated')
        self.assertFalse(evidence['selected'])
        self.assertEqual(evidence['contact_status'], 'unavailable_no_labels')
        self.assertEqual(output['parent-motion-review.json'], files['motion-review.json'])
        manifest = json.loads(output['character-manifest.json'])
        self.assertFalse(manifest['selected'])
        for name, digest in manifest['files'].items():
            self.assertEqual(sha256(output[name]).hexdigest(), digest)

    def test_repaired_leg_does_not_hide_other_attachment_failure(self):
        files, plan = bundle(other_failure=True)
        output, evidence, geometry = build(files, plan)
        self.assertTrue(json.loads(output['pose-geometry-report.json'])['sampled_geometry_passed'])
        self.assertFalse(geometry['passed'])
        self.assertFalse(next(r for r in geometry['records'] if r['slot'] == 'other')['passed'])
        self.assertEqual(evidence['status'], 'needs_changes')

    def test_stale_reference_missing_setup_and_cross_slot_rejected(self):
        files, plan = bundle()
        bad = dict(files, **{'numeric-reference.json': canonical_bytes(dict(
            skeleton_sha256='0'*64, animations={'move': []}))})
        with self.assertRaisesRegex(ValueError, 'reference_mismatch'): build(bad, plan)
        with self.assertRaisesRegex(ValueError, 'scope_mismatch'): build(files, dict(plan, slot='other'))
        del files['rig-setup-reference.json']
        with self.assertRaisesRegex(ValueError, 'setup_required'): build(files, plan)
