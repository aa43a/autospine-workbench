from copy import deepcopy
from hashlib import sha256
import json
import unittest
from unittest.mock import patch

from test_depth_region_partition import source
from autospine_workbench.resolved_project import canonical_sha256
from autospine_workbench.automation.storage_io import canonical_bytes
from autospine_workbench.targets.character43.affine_pose import sample
from autospine_workbench.targets.character43.numeric_reference import read, write
from autospine_workbench.targets.character43.region_order_bundle import build


def fixture():
    doc, images = source(); doc['skins'][0]['name'] = 'default'
    raw = canonical_bytes(doc); digest = sha256(raw).hexdigest()
    files = dict(images, **{'skeleton.json': raw, 'skeleton.atlas': b'atlas',
        'motion-ir.json': b'{}', 'motion-contact.json': b'{}',
        'character-manifest.json': b'{}', 'motion-depth.json': b'old depth',
        'deformation.json': b'{"passed":false,"records":[]}',
        'motion-review.json': canonical_bytes(dict(reference_length_px=100, issues=[
            dict(stage='geometry', reason_code='old_slot_failure'),
            dict(stage='projection', reason_code='source_problem')]))})
    frames = [dict(time=t, vertices=sample(doc, 'test', t)[0]) for t in (0, .5, 1)]
    files['rig-setup-reference.json'] = canonical_bytes(dict(skeleton_sha256=digest, vertices=frames[0]['vertices']))
    files = write(files, dict(skeleton_sha256=digest, animations={'test': frames}), limit=1)
    plan = dict(slot='a', animation='test', region_order=dict(
        mesh_sha256=canonical_sha256(doc['skins'][0]['attachments']['a']['a']),
        triangles=[0, 2], reference_slot='b', side='after'))
    return files, plan


class RegionOrderBundleTests(unittest.TestCase):
    @patch('autospine_workbench.targets.character43.final_motion_contact.recheck', return_value={'status':'not_evaluated'})
    def test_references_and_evidence_follow_new_region_identity(self, contact):
        files, plan = fixture(); original = deepcopy(files)
        output, evidence, geometry = build(files, plan)
        digest = sha256(output['skeleton.json']).hexdigest()
        reference = read(output)
        regions = json.loads(output['motion-repair.json'])['region_order']['regions']
        self.assertEqual(reference['skeleton_sha256'], digest)
        for before, after in zip(read(files)['animations']['test'], reference['animations']['test']):
            self.assertEqual(after['vertices']['b'], before['vertices']['b'])
            for region in regions:
                self.assertEqual(after['vertices'][region['slot']],
                                 [before['vertices']['a'][i] for i in region['source_vertex_indices']])
        self.assertNotIn('motion-depth.json', output)
        self.assertEqual(output['parent-motion-review.json'], files['motion-review.json'])
        self.assertEqual(evidence['runtime_status'], 'not_evaluated')
        self.assertEqual(evidence['status'], 'needs_changes')
        parent = json.loads(files['motion-review.json'])
        self.assertEqual(evidence['issues'][:len(parent['issues'])], parent['issues'])
        self.assertEqual(evidence['inherited_issue_context']['source_review_sha256'],
                         sha256(files['motion-review.json']).hexdigest())
        self.assertEqual(geometry['skeleton_sha256'], digest)
        self.assertEqual(files, original)
        for path, value in json.loads(output['character-manifest.json'])['files'].items():
            self.assertEqual(sha256(output[path]).hexdigest(), value)
        contact.assert_called_once()

    def test_stale_mesh_or_reference_rejected(self):
        files, plan = fixture(); plan['region_order']['mesh_sha256'] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'mesh_changed'): build(files, plan)
        files, plan = fixture()
        setup = json.loads(files['rig-setup-reference.json']); setup['skeleton_sha256'] = '0' * 64
        files['rig-setup-reference.json'] = canonical_bytes(setup)
        with self.assertRaisesRegex(ValueError, 'source_identity'): build(files, plan)

    @patch('autospine_workbench.targets.character43.final_motion_contact.recheck', return_value={'status':'not_evaluated'})
    def test_scope_then_order_keeps_failures_and_exact_parent_review(self, contact):
        from autospine_workbench.targets.character43.occlusion_scope_bundle import build as scope_build
        files, _ = fixture(); doc = json.loads(files['skeleton.json'])
        meshes = doc['skins'][0]['attachments']
        review = json.loads(files['motion-review.json'])
        review['issues'] += [dict(stage='contact', reason_code='foot_sliding'),
                             dict(stage='material', reason_code='transparent_edge', slot='a', triangle=0)]
        files['motion-review.json'] = canonical_bytes(review)
        scope = dict(slot='a', animation='test', contact_scope=dict(reference_slot='b',
            mesh_sha256=canonical_sha256(meshes['a']['a']),
            reference_mesh_sha256=canonical_sha256(meshes['b']['b']), regions={'occlusion':[0]}))
        parent, _, _ = scope_build(files, scope)
        scene = json.loads(parent['skeleton.json']); slot = 'a-depth-001'
        plan = dict(slot=slot, animation='test', region_order=dict(
            mesh_sha256=canonical_sha256(scene['skins'][0]['attachments'][slot][slot]),
            triangles=[0], reference_slot='b', side='after', interval=[.25, .75]))
        output, evidence, _ = build(parent, plan)
        inherited = json.loads(parent['motion-review.json'])['issues']
        self.assertEqual(evidence['issues'][:len(inherited)], inherited)
        self.assertEqual(output['parent-motion-review.json'], parent['motion-review.json'])
        context = evidence['inherited_issue_context']
        self.assertEqual(context['issue_count'], len(inherited))
        self.assertEqual(context['source_skeleton_sha256'], sha256(parent['skeleton.json']).hexdigest())
        self.assertEqual(context['location_scope'], 'parent_candidate_not_current_partition')
        self.assertEqual(evidence['runtime_status'], 'not_evaluated')
        self.assertEqual(evidence['depth_order_status'], 'not_evaluated')

    @patch('autospine_workbench.targets.character43.final_motion_contact.recheck', return_value={'status':'not_evaluated'})
    def test_interval_bundle_keeps_timeline_and_profile(self, contact):
        files, plan = fixture(); plan['region_order']['interval'] = [.25, .75]
        output, _, _ = build(files, plan)
        report = json.loads(output['motion-repair.json'])
        scene = json.loads(output['skeleton.json'])
        self.assertEqual(report['profile'], 'selected-region-interval-order-v1')
        self.assertEqual(report['region_order']['interval'], [.25, .75])
        self.assertEqual([s['name'] for s in scene['slots']], report['region_order']['setup_order'])
        self.assertEqual(scene['animations']['test']['drawOrder'][-1], dict(time=.75, offsets=[]))
        self.assertEqual(json.loads(output['character-manifest.json'])['files']['skeleton.json'],
                         sha256(output['skeleton.json']).hexdigest())


if __name__ == '__main__': unittest.main()
