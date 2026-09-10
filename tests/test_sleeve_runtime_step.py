import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from copy import deepcopy
from autospine_workbench.automation.sleeve_runtime_step import validate


class SleeveRuntimeStepTests(unittest.TestCase):
    def fixture(self,root):
        data={'skeleton.json':b'{}','skeleton.atlas':b'test',
              'numeric-reference.json':json.dumps({'animations':{'motion':[{},{}]}}).encode()}
        for name,raw in data.items():(root/name).write_bytes(raw)
        digest=lambda name:hashlib.sha256(data[name]).hexdigest()
        expected=dict(package='@esotericsoftware/spine-core',version='4.3.13',files={'dist/index.js':'a'*64})
        report=dict(runtime_package=expected['package'],runtime_version=expected['version'],scope='official_core_vertices_only',authority='none',
            production_authorized=False,runtime_files=expected['files'],skeleton_sha256=digest('skeleton.json'),atlas_sha256=digest('skeleton.atlas'),
            reference_sha256=digest('numeric-reference.json'),results=[dict(animation='motion',frames=2,max_error_px=.0001,passed=True)],passed=True)
        return report,expected

    def test_exact_source_and_runtime_versions_required(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);report,expected=self.fixture(root)
            self.assertTrue(validate(report,root,expected))
            altered=deepcopy(report);altered['runtime_version']='4.3.14'
            with self.assertRaises(ValueError):validate(altered,root,expected)
            (root/'skeleton.json').write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError,'source_changed'):validate(report,root,expected)

    def test_claimed_pass_is_recomputed_and_inventory_checked(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);report,expected=self.fixture(root)
            report['results'][0]['max_error_px']=.1
            with self.assertRaisesRegex(ValueError,'result_mismatch'):validate(report,root,expected)
            report['results'][0]['passed']=False;report['passed']=False
            self.assertFalse(validate(report,root,expected))
            report['results'][0]['frames']=1
            with self.assertRaisesRegex(ValueError,'samples'):validate(report,root,expected)
