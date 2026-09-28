from base64 import b64encode
from copy import deepcopy
from hashlib import sha256
import binascii
import json
import struct
import unittest
import zlib

from test_joint_face import fixture
from autospine_workbench.png_rgba import RgbaImage, encode_rgba_png, decode_rgba_png
from autospine_workbench.targets.character43.joint_face import apply, defaults
from autospine_workbench.targets.character43.joint_face_mouth_upload import normalize


def payload(data):
    return dict(png_base64=b64encode(data).decode(), sha256=sha256(data).hexdigest())


def custom_png(width=64, height=48, alpha=None):
    pixels = bytes(v for y in range(height) for x in range(width)
        for v in (172, 25, 74, alpha if alpha is not None else (145 if 8 < x < 56 and 8 < y < 40 else 0)))
    return encode_rgba_png(RgbaImage(width, height, pixels))


def chunk(kind, value):
    return struct.pack('>I', len(value))+kind+value+struct.pack('>I', binascii.crc32(kind+value) & 0xffffffff)


class JointFaceMouthUploadTests(unittest.TestCase):
    def test_custom_rgba_png_keeps_exact_bytes_and_content_identity_in_every_target(self):
        files, document = fixture(); files['skeleton.atlas'] = b'original atlas\n'
        files['images/character-source.png'] = b'original source bytes'
        before = deepcopy(files); png = custom_png(); upload = payload(png)
        config = defaults(); config['enabled'] = True
        config['mouth'].update(template_enabled=True, template_image=upload, open=.5)
        result, updates, report = apply(files, document, 'body', config, [0, 1, 2])
        template = report['generated_templates'][0]; slot = template['slot']
        for prefix in ('textures/', 'images/', 'editor/images/'):
            self.assertEqual(updates[prefix+slot+'.png'], png)
        self.assertEqual(files, before)
        self.assertEqual(normalize(upload), upload)
        self.assertEqual(template['source'], 'user_provided_template')
        self.assertFalse(template['generated_template'])
        self.assertTrue(template['user_provided_template'])
        self.assertIn(upload['sha256'], template['template_id'])
        self.assertNotIn('svg_sha256', template)
        metadata = json.loads(updates['generated/'+slot+'.json'])
        self.assertEqual(metadata['png_sha256'], upload['sha256'])
        self.assertEqual(metadata['provenance'], 'user_provided_template')
        self.assertNotIn('source', metadata)
        self.assertEqual(set(decode_rgba_png(updates['textures/'+slot+'.png']).pixels[3::4]), {0, 145})
        self.assertEqual(next(s for s in result['slots'] if s['name'] == slot)['color'], 'ffffff00')

    def test_disabled_custom_asset_stays_unbundled_and_reset_restores_procedural_template(self):
        files, document = fixture(); files['skeleton.atlas'] = b'original atlas\n'
        config = defaults(); config['mouth'].update(template_enabled=True, template_image=payload(custom_png()))
        result, updates, _ = apply(files, document, 'body', config, [0, 2])
        self.assertEqual(result, document); self.assertEqual(updates, {})
        config['enabled'] = True; config['mouth']['template_enabled'] = False
        result, updates, report = apply(files, document, 'body', config, [0, 2])
        self.assertEqual(updates, {}); self.assertEqual(report['generated_templates'], [])
        config['mouth'].update(template_enabled=True, template_image=None)
        _, _, report = apply(files, document, 'body', config, [0, 2])
        self.assertEqual(report['generated_templates'][0]['template_id'], 'procedural-mouth-interior-v1')

    def test_rejects_paths_bad_base64_hash_and_oversize_before_decode(self):
        valid = payload(custom_png())
        for value in [dict(path='C:/mouth.png'), {**valid, 'path':'mouth.png'},
                      {**valid, 'sha256':'0'*64}, {**valid, 'sha256': valid['sha256'].upper()},
                      {**valid, 'png_base64': 'data:image/png;base64,'+valid['png_base64']},
                      {**valid, 'png_base64': valid['png_base64']+'='}, payload(b'x'*32769)]:
            with self.subTest(value=str(value)[:60]), self.assertRaisesRegex(ValueError, 'joint_face_mouth_template_image_'):
                normalize(value)

    def test_rejects_wrong_dimensions_no_transparency_and_no_visible_pixels(self):
        for data in [custom_png(128, 48), custom_png(64, 49), custom_png(alpha=255), custom_png(alpha=0)]:
            with self.subTest(size=len(data)), self.assertRaisesRegex(ValueError, 'dimensions|transparency'):
                normalize(payload(data))

    def test_rejects_crc_trailing_bytes_animation_and_unbounded_deflate(self):
        png = custom_png()
        corrupt = png[:50]+bytes([png[50] ^ 1])+png[51:]
        apng = png[:33]+chunk(b'acTL', struct.pack('>II', 2, 0))+png[33:]
        bomb = png[:33]+chunk(b'IDAT', zlib.compress(b'\0'*1000000))+chunk(b'IEND', b'')
        for data in [corrupt, png+b'trailing', apng, bomb]:
            with self.subTest(size=len(data)), self.assertRaisesRegex(ValueError, 'joint_face_mouth_template_image_'):
                normalize(payload(data))


if __name__ == '__main__':
    unittest.main()
