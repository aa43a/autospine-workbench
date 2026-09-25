import json
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.automation.storage_io import canonical_bytes
from m4_runtime_batch_audit import audit
from m4_runtime_batch_coverage import render_identity,verify


class BatchAuditTests(unittest.TestCase):
    def build(self,root):
        skeleton=b'{}';digest=sha256(skeleton).hexdigest();records=[];batches=[]
        for index,times in enumerate(([0,.5],[0,1])):
            folder=root/f'batch-{index:03d}';folder.mkdir();(folder/'runtime').mkdir()
            files={'skeleton.json':skeleton,'skeleton.atlas':b'atlas',
                'numeric-reference.json':canonical_bytes({'skeleton_sha256':digest,
                    'animations':{'external-motion':[{'time':t,'vertices':{}} for t in times]}})}
            bundle=AnimatedStore(folder/'isolated-store').publish(files);identity=render_identity(files)
            report=dict(bundle_sha256=bundle,passed=True,authority='none',production_authorized=False,
                results=[dict(time=t,animation='external-motion') for t in times],
                runtime_sha256='runtime',runtime_version='4.3.13',profile='official',browser_sha256='browser')
            raw=canonical_bytes(report);(folder/'runtime/report.json').write_bytes(raw)
            (folder/'runtime/deformation.json').write_bytes(canonical_bytes(dict(skeleton_sha256=digest,passed=True)))
            records.append(dict(folder=folder.name,bundle_sha256=bundle,render_identity=identity,
                runtime_report_sha256=sha256(raw).hexdigest()))
            batches.append(dict(bundle_sha256=bundle,times=times,render_identity=identity,runtime=report,geometry_passed=True))
        manifest=dict(status='complete',batch_records=records,batch_sizes=[2,2],required_times=[0,.5,1],
            skeleton_sha256=digest,coverage=verify([0,.5,1],batches))
        (root/'report.json').write_bytes(canonical_bytes(manifest))

    def test_reconstructs_saved_coverage_and_rejects_changed_report(self):
        with TemporaryDirectory() as directory:
            root=Path(directory);self.build(root)
            self.assertEqual(audit(root)['frames'],3)
            (root/'batch-001/runtime/report.json').write_bytes(b'{}')
            with self.assertRaisesRegex(ValueError,'report_hash'):audit(root)

    def test_running_manifest_cannot_claim_complete(self):
        with TemporaryDirectory() as directory:
            root=Path(directory);self.build(root)
            manifest=json.loads((root/'report.json').read_bytes());manifest['status']='running'
            (root/'report.json').write_bytes(canonical_bytes(manifest))
            with self.assertRaisesRegex(ValueError,'incomplete'):audit(root)


if __name__=='__main__':unittest.main()
