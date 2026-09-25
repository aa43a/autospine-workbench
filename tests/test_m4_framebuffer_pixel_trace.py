from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from PIL import Image
from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.automation.storage_io import canonical_bytes
from m4_framebuffer_pixel_trace import run


class FramebufferTraceTests(unittest.TestCase):
    def fixture(self,root):
        image=Image.new('RGBA',(2,2),(255,128,255,2));stream=BytesIO();image.save(stream,format='PNG');raw=stream.getvalue()
        mesh={'uvs':[0,0,1,0,0,1],'triangles':[0,1,2]}
        doc={'skins':[{'attachments':{'cloth':{'cloth':mesh}}}]}
        files={'skeleton.json':canonical_bytes(doc),'images/cloth.png':raw,
            'numeric-reference.json':canonical_bytes({'animations':{'external-motion':[
                {'time':0,'vertices':{'cloth':[[0,0],[2,0],[0,2]]}}]}})}
        digest=AnimatedStore(root/'isolated-store').publish(files)
        (root/'report.json').write_bytes(canonical_bytes({'candidate_bundle_sha256':digest}))
        (root/'runtime').mkdir();(root/'runtime/frame.png').write_bytes(raw)
        runtime={'bundle_sha256':digest,'results':[{'animation':'external-motion','time':0,'draw_order':['cloth']}],
            'screenshots':[{'animation':'external-motion','index':0,'file':'frame.png','sha256':sha256(raw).hexdigest()}],
            'info':{'left':0,'bottom':0,'width':2,'height':2}}
        (root/'runtime/report.json').write_bytes(canonical_bytes(runtime))

    def test_low_alpha_source_is_not_a_new_mesh_hole(self):
        with TemporaryDirectory() as folder:
            root=Path(folder);self.fixture(root);run(root,0,[(0,1)],root/'trace.json')
            row=json.loads((root/'trace.json').read_bytes())['rows'][0]
            self.assertEqual(row['framebuffer_rgba'],[255,128,255,2])
            self.assertEqual(row['hits'][0]['bilinear_source_rgba'],[255,128,255,2])
            self.assertTrue(all(abs(v-32)<2 for v in row['display_over_dark']))

    def test_altered_screenshot_is_rejected(self):
        with TemporaryDirectory() as folder:
            root=Path(folder);self.fixture(root);(root/'runtime/frame.png').write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError,'framebuffer_trace_image'):run(root,0,[(0,1)],root/'trace.json')


if __name__=='__main__':unittest.main()
