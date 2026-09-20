"""Capture admission must not accept unrelated edits under an ordering report."""
import json
from hashlib import sha256
from pathlib import Path
import sys
import tempfile
import unittest
from test_motion_depth_overlap import fixture

TOOLS=Path(__file__).resolve().parents[1]/'tools'
sys.path.insert(0,str(TOOLS))
from m4_depth_order_capture import verify


class CaptureIdentityTests(unittest.TestCase):
    def test_only_reported_order_can_change(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); doc,_=fixture()
            doc['animations']['external-motion']=doc['animations'].pop('test')
            raw=json.dumps(doc).encode(); (root/'skeleton.json').write_bytes(raw)
            partition=dict(skeleton_sha256=sha256(raw).hexdigest(),source_artifact_sha256='a'*64)
            (root/'report.json').write_text(json.dumps(partition))
            report=dict(artifact_sha256='a'*64,candidate_available=True,order=dict(failures=[],frames=[
                dict(time=.1,order=['b','a'])]),cloth_constraints=None)
            order=root/'ordering.json'; order.write_text(json.dumps(report))
            doc['animations']['external-motion']['drawOrder']=[dict(time=.1,offsets=[
                dict(slot='a',offset=1),dict(slot='b',offset=-1)])]
            candidate=order.with_suffix('.skeleton.json'); candidate.write_text(json.dumps(doc))
            self.assertEqual(json.loads(verify(root,order)[0]),doc)
            doc['bones'][0]['x']=1; candidate.write_text(json.dumps(doc))
            with self.assertRaisesRegex(ValueError,'unexpected_edit'): verify(root,order)
            doc['bones'][0]['x']=0; candidate.write_text(json.dumps(doc))
            report['limb_constraints']=dict(unmeasured_samples=1); order.write_text(json.dumps(report))
            with self.assertRaisesRegex(ValueError,'unmeasured'): verify(root,order)
            report['artifact_sha256']='b'*64; order.write_text(json.dumps(report))
            with self.assertRaisesRegex(ValueError,'identity'): verify(root,order)


if __name__=='__main__': unittest.main()
