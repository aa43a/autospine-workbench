from hashlib import sha256
import unittest

from autospine_workbench.automation.storage_io import canonical_bytes
from autospine_workbench.targets.character43.affine_pose import sample
from autospine_workbench.targets.character43.repair_feasibility import inspect
from test_character_affine_repair import fixture


def evidence(fixed=True):
    doc=fixture()
    mesh=doc['skins'][0]['attachments']['mesh']['mesh']
    mesh.update(type='mesh',uvs=[0,0,1,0,0,1])
    if fixed:mesh['vertices']=[1,0,0,0,1,1,0,1,0,1,1,0,0,1,1]
    doc['slots']=[dict(name='mesh',bone='a',attachment='mesh')]
    raw=canonical_bytes(doc);digest=sha256(raw).hexdigest()
    setup=sample(dict(doc,animations={'walk':{'bones':{}}}),'walk',0)[0]
    return {'skeleton.json':raw,
        'rig-setup-reference.json':canonical_bytes(dict(skeleton_sha256=digest,vertices=setup)),
        'numeric-reference.json':canonical_bytes(dict(skeleton_sha256=digest,
            animations={'walk':[dict(time=0),dict(time=1)]})),
        'deformation.json':canonical_bytes(dict(skeleton_sha256=digest,
            records=[dict(slot='mesh',animation='walk',passed=False)]))}


class FeasibilityTests(unittest.TestCase):
    def test_fixed_compression_cannot_be_changed_by_mixed_vertex_repair(self):
        files=evidence();before=dict(files)
        report=inspect(files,'candidate');row=report['rows'][0]
        self.assertEqual(row['status'],'fixed_vertex_counterexample')
        self.assertEqual(row['counterexample_count'],1)
        self.assertEqual(row['single_bone_triangles'],1)
        self.assertEqual(row['failed_times'],1)
        self.assertAlmostEqual(row['worst']['setup_ratio'],.4)
        self.assertEqual(row['worst']['time'],1)
        shape=row['worst']['shape_evidence']
        self.assertEqual(shape['reference_kind'],'single_bone_affine')
        self.assertAlmostEqual(shape['bone_compensated']['signed_area_ratio'],1)
        self.assertAlmostEqual(shape['actual']['signed_area_ratio'],.4)
        self.assertEqual(files,before)
        self.assertFalse(report['selected'])

    def test_mixed_failure_is_not_claimed_infeasible(self):
        row=inspect(evidence(False),'candidate')['rows'][0]
        self.assertEqual(row['status'],'no_fixed_vertex_counterexample')
        self.assertFalse(row['complete_repair_impossible_under_policy'])

    def test_stale_evidence_rejected(self):
        for key in ('numeric-reference.json','rig-setup-reference.json','deformation.json'):
            files=evidence();files[key]=files[key].replace(b'"skeleton_sha256":"',b'"skeleton_sha256":"bad')
            with self.subTest(key=key),self.assertRaisesRegex(ValueError,'identity'):
                inspect(files,'candidate')


if __name__=='__main__':unittest.main()
