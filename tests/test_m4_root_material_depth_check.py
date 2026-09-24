import base64
from io import BytesIO
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from PIL import Image
from m4_root_material_depth_check import inspect, body_overlap


class MaterialDepthTests(unittest.TestCase):
    def test_body_overlap_respects_transparent_texels_and_outside_points(self):
        image=Image.new('RGBA',(2,2),(0,0,0,0))
        image.putpixel((0,0),(255,255,255,255))
        output=BytesIO();image.save(output,format='PNG')
        attachment=dict(uvs=[0,0,1,0,1,1,0,1],triangles=[0,1,2,0,2,3])
        scene=dict(skeleton=dict(skins=[dict(attachments={'body':{'body':attachment}})]),
                   textures={'images/body.png':'data:image/png;base64,'+base64.b64encode(output.getvalue()).decode()})
        points=[[.25,.25],[.75,.25],[2,2]]
        mappings=[(np.array([0,1,2]),np.array([0,1,2]),np.eye(3))]
        with patch('m4_root_material_depth_check.sample',return_value=({'body':[[0,0],[1,0],[1,1],[0,1]]},{})):
            result=body_overlap(scene,'body',dict(time=0,vertices=points),mappings,3)
        self.assertEqual(result.tolist(),[True,False,False])

    def test_front_back_unknown_and_identity(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            image=Image.new('RGBA',(2,2),(255,255,255,255))
            output=BytesIO(); image.save(output,format='PNG')
            mesh=dict(uvs=[0,0,1,0,1,1,0,1],triangles=[0,1,2,0,2,3],vertices=[])
            source=dict(artifact_sha256='parent',skeleton=dict(skins=[dict(attachments={'arm':{'arm':mesh}})]))
            target=dict(artifact_sha256='candidate',skeleton=dict(
                slots=[dict(name='m4-root-material'),dict(name='body')],
                skins=[dict(attachments={'m4-root-material':{'m4-root-material':mesh}})]),
                textures={'images/m4-root-material.png':'data:image/png;base64,'+base64.b64encode(output.getvalue()).decode()})
            for side,value in [('before',source),('after',target)]:
                p=root/side/'runtime/player-assets';p.mkdir(parents=True)
                (p/'scene.json').write_text(json.dumps(value))
            (root/'report.json').write_text(json.dumps(dict(parent='parent',candidate='candidate')))
            field=dict(candidate='parent',arm='arm',body='body',rows=[
                dict(time=0,depth_values=[1]*4),dict(time=1,depth_values=[-1]*4),
                dict(time=2,depth_values=[None]*4)])
            path=root/'field.json';path.write_text(json.dumps(field))
            result=inspect(root,path)
            self.assertEqual(result['visible_material_texels'],4)
            self.assertEqual(result['rows'][0]['front_proxy_texels'],4)
            self.assertEqual(result['rows'][1]['back_or_margin_texels'],4)
            self.assertEqual(result['rows'][2]['unknown_texels'],4)
            self.assertEqual(result['unmapped_texels'],0)
            field['candidate']='stale';path.write_text(json.dumps(field))
            with self.assertRaisesRegex(ValueError,'identity_mismatch'):inspect(root,path)


if __name__=='__main__':unittest.main()
