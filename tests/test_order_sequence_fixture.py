from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import tempfile
import unittest
from PIL import Image
from m4_order_sequence_fixture import expand


class OrderSequenceFixtureTests(unittest.TestCase):
    def inputs(self, root):
        buf = BytesIO(); Image.new('RGBA',(2,2),(50,80,90,255)).save(buf,format='PNG')
        raw = buf.getvalue(); (root/'image.png').write_bytes(raw)
        info = dict(width=2,height=2,left=0,bottom=0)
        report = dict(bundle_sha256='bundle',info=info,passed=True,
            results=[dict(animation='external-motion',index=i,time=t,draw_order=['hand','leg','front']) for i,t in enumerate([0,.5,1])],
            screenshots=[dict(animation='external-motion',index=i,file='image.png',sha256=sha256(raw).hexdigest()) for i in range(3)])
        report_raw = json.dumps(report).encode(); (root/'report.json').write_bytes(report_raw)
        fixture = dict(runtime_report_sha256=sha256(report_raw).hexdigest(),bundle_sha256='bundle',info=info,
                       rows=[dict(region='hand',body='front')])
        path = root/'base.json'; path.write_text(json.dumps(fixture))
        return path

    def test_complete_schedule_and_whole_frame_requirement_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); path=self.inputs(root); expand(path,root,root/'out.json')
            out=json.loads((root/'out.json').read_bytes())
            self.assertEqual([r['time'] for r in out['rows']],[0,.5,1])
            self.assertTrue(out['whole_frame_trial'])
            self.assertEqual(out['rows'][1]['points'][0]['kind'],'frame_reference_anchor')
            self.assertEqual(out['parent_fixture_sha256'],sha256(path.read_bytes()).hexdigest())

    def test_missing_shot_or_modified_image_cannot_shrink_schedule(self):
        for kind in ('missing','changed'):
            with self.subTest(kind=kind),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp); path=self.inputs(root)
                if kind=='changed': (root/'image.png').write_bytes(b'changed')
                else:
                    value=json.loads((root/'report.json').read_bytes());value['screenshots'].pop()
                    raw=json.dumps(value).encode();(root/'report.json').write_bytes(raw)
                    base=json.loads(path.read_bytes());base['runtime_report_sha256']=sha256(raw).hexdigest();path.write_text(json.dumps(base))
                with self.assertRaises((ValueError,KeyError)):expand(path,root,root/'out.json')
                self.assertFalse((root/'out.json').exists())
