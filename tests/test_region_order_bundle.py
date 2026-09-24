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


if __name__ == '__main__': unittest.main()
