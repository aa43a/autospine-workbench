import importlib.util
from hashlib import sha256
import unittest
from autospine_workbench.automation.storage_io import canonical_bytes
from autospine_workbench.targets.character43.cloth_strain_report import inspect


@unittest.skipUnless(importlib.util.find_spec('numpy'), 'optional strain analysis')
class StrainReportTests(unittest.TestCase):
    def test_flags_shear_and_checks_reference_identity(self):
        doc = dict(bones=[dict(name='cloth-fabric')], skins=[dict(attachments={'fabric': {'fabric':
            dict(vertices=[1, 0, 0, 0, 1, 1, 0, 1, 0, 1, 1, 0, 0, 1, 1], triangles=[0, 1, 2])}})])
        raw = canonical_bytes(doc)
        reference = dict(skeleton_sha256=sha256(raw).hexdigest(), animations={'wave': [
            dict(time=0, vertices={'fabric': [[0, 0], [1, 0], [0, 1]]}),
            dict(time=1, vertices={'fabric': [[0, 0], [1, 0], [1.2, 1]]})]})
        files = {'skeleton.json': raw, 'numeric-reference.json': canonical_bytes(reference)}
        report = inspect(files, 'cloth-fabric')
        self.assertFalse(report['passed']); self.assertFalse(report['selected'])
        self.assertTrue(report['records'][0]['passed'])
        self.assertFalse(report['records'][1]['passed'])
        reference['skeleton_sha256'] = '0'*64
        files['numeric-reference.json'] = canonical_bytes(reference)
        with self.assertRaisesRegex(ValueError, 'reference_mismatch'): inspect(files, 'cloth-fabric')
