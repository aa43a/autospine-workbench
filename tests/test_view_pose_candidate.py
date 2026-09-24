from copy import deepcopy
from hashlib import sha256
from io import BytesIO
import json
import unittest
from PIL import Image

import test_view_pose_variant as fixtures
from autospine_workbench.resolved_project import canonical_sha256
from autospine_workbench.automation.storage_io import canonical_bytes
from autospine_workbench.targets.character43.affine_pose import sample
from autospine_workbench.targets.character43.numeric_reference import read
from autospine_workbench.targets.character43.view_pose_candidate import build


class ViewPoseCandidateTests(unittest.TestCase):
    def fixture(self):
        doc, request = fixtures.ViewPoseVariantTests().fixture()
        raw = canonical_bytes(doc)
        stream = BytesIO(); Image.new('RGBA', (128, 256), (20, 80, 120, 255)).save(stream, format='PNG')
        png = stream.getvalue(); request['texture_sha256'] = sha256(png).hexdigest()
        files = {'skeleton.json': raw, 'skeleton.atlas': b'original atlas',
                 'images/leg.png': b'preserved-original', 'runtime.json': b'old-success',
                 'motion-depth.json': b'old-success', 'motion-contact.json': b'old-success',
                 'motion-review.json': canonical_bytes(dict(status='accepted', selected=True, reference_length_px=10,
                     issues=[dict(stage='projection', reason_code='retained')])),
                 'character-manifest.json': b'{"selected":true,"production_authorized":true}',
                 'numeric-reference.json': canonical_bytes(dict(skeleton_sha256=sha256(raw).hexdigest(),
                     animations={'move': [dict(time=t, vertices=sample(doc, 'move', t)[0]) for t in (0, .37, 1, 2)]}))}
        return files, request, png

    def test_package_active_reference_and_reset_acceptance(self):
        files, request, png = self.fixture(); before = deepcopy(files)
        output, review, geometry = build(files, request, png)
        self.assertEqual(files, before)
        texture = 'view-'+sha256(png).hexdigest()
        self.assertEqual(output['images/'+texture+'.png'], png)
        with Image.open(BytesIO(output['textures/'+texture+'.png'])) as page:
            self.assertEqual(page.size, (132, 260))
            self.assertEqual(page.getpixel((2, 2)), (20, 80, 120, 255))
        self.assertIn(texture.encode(), output['skeleton.atlas'])
        frames = read(output)['animations']['move']
        self.assertIn(.37, [r['time'] for r in frames])
        self.assertEqual(next(r for r in frames if r['time'] == 1.5)['attachments']['leg'], 'leg')
        self.assertNotEqual(next(r for r in frames if r['time'] == 1)['attachments']['leg'], 'leg')
        self.assertEqual(review['contact_status'], 'not_evaluated')
        self.assertFalse(review['selected'])
        for old in ('runtime.json', 'motion-depth.json'):
            self.assertNotIn(old, output)
        self.assertNotEqual(output['motion-contact.json'], files['motion-contact.json'])
        manifest = json.loads(output['character-manifest.json'])
        self.assertFalse(manifest['production_authorized'])
        for path, digest in manifest['files'].items():
            self.assertEqual(sha256(output[path]).hexdigest(), digest)
        self.assertEqual({r['slot'] for r in geometry['records']}, {'leg', 'other'})

    def test_actual_texture_hash_and_size_required(self):
        files, request, png = self.fixture()
        with self.assertRaisesRegex(ValueError, 'texture_changed'):
            build(files, request, png+b'changed')
        request['texture_size'] = [128, 128]
        with self.assertRaisesRegex(RuntimeError, 'png_invalid'):
            build(files, request, png)

    def test_other_region_failure_remains(self):
        files, request, png = self.fixture()
        doc = json.loads(files['skeleton.json'])
        channels = doc['animations']['move']['attachments']['default']
        channels['other'] = {'other': deepcopy(channels['leg']['leg'])}
        files['skeleton.json'] = canonical_bytes(doc)
        request['document_sha256'] = canonical_sha256(doc)
        reference = read(files)
        reference['skeleton_sha256'] = sha256(files['skeleton.json']).hexdigest()
        files['numeric-reference.json'] = canonical_bytes(reference)
        _, review, geometry = build(files, request, png)
        self.assertFalse(geometry['passed'])
        self.assertFalse(next(r for r in geometry['records'] if r['slot'] == 'other')['passed'])
        self.assertEqual(review['status'], 'needs_changes')
