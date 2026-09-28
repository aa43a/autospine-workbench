from copy import deepcopy
from hashlib import sha256
from io import BytesIO
import json
import unittest
from zipfile import ZipFile

from autospine_workbench.automation.storage_io import canonical_bytes
from check_joint_delivery import check_bundle, unpack
from check_joint_isolation import inspect
from test_joint_face import fixture
from test_joint_secondary import scene
from autospine_workbench.targets.character43 import joint_face, joint_secondary


def export_fixture():
    files, document = fixture()
    files['skeleton.json'] = canonical_bytes(document)
    for slot in document['slots']:
        files['images/'+slot['name']+'.png'] = b'\x89PNG\r\n\x1a\nfixture'
    files['skeleton.atlas'] = b'images/layer-000.png\nsize: 20,10\n'
    source = deepcopy(files)
    files['editor/skeleton.json'] = files['skeleton.json']
    for name, raw in list(files.items()):
        if name.startswith('images/'): files['editor/'+name] = raw
    digest = sha256(files['skeleton.json']).hexdigest()
    files['joint-animation.json'] = canonical_bytes(dict(animation='body', duration=2.,
        skeleton_sha256=digest, parent_skeleton_sha256=digest, face={}, secondary={}))
    return files, source


class JointDeliveryTests(unittest.TestCase):
    def test_roundtrip_accepts_identity_and_rejects_editor_drift(self):
        files, source = export_fixture()
        self.assertTrue(check_bundle(files, source)['passed'])
        document = json.loads(files['editor/skeleton.json']); document['bones'][0]['x'] += 1
        files['editor/skeleton.json'] = canonical_bytes(document)
        with self.assertRaisesRegex(ValueError, 'editor_identity_bones'): check_bundle(files, source)

    def test_original_and_editor_png_identity_are_not_optional(self):
        files, source = export_fixture(); files['editor/images/layer-000.png'] += b'x'
        with self.assertRaisesRegex(ValueError, 'editor_png_identity'): check_bundle(files, source)
        files, source = export_fixture(); files['images/layer-000.png'] += b'x'
        files['editor/images/layer-000.png'] = files['images/layer-000.png']
        with self.assertRaisesRegex(ValueError, 'source_png_changed'): check_bundle(files, source)

    def test_download_rejects_duplicate_or_escaping_entries(self):
        for names in (['x', 'x'], ['../x'], ['/x']):
            stream = BytesIO()
            with ZipFile(stream, 'w') as archive:
                for n in names: archive.writestr(n, b'fake')
            with self.assertRaises(ValueError): unpack(stream.getvalue())

    def test_all_off_and_single_off_preserve_other_channels(self):
        files, document = scene(); face_files, face = fixture()
        manifest = json.loads(files['character-manifest.json'])
        manifest['layers'].extend(json.loads(face_files['character-manifest.json'])['layers'])
        index = next(i for i,b in enumerate(document['bones']) if b['name']=='head')
        for slot in face['slots']:
            document['slots'].append(slot)
            mesh = deepcopy(face['skins'][0]['attachments'][slot['name']])
            values = mesh[slot['name']]['vertices']
            for i in range(0, len(values), 5): values[i+1] = index
            document['skins'][0]['attachments'][slot['name']] = mesh
        files['skeleton.json'] = canonical_bytes(document)
        files['character-manifest.json'] = canonical_bytes(manifest)
        config = dict(face=joint_face.defaults(), **joint_secondary.defaults())
        for kind in ('face', 'hair', 'cloth'): config[kind]['enabled'] = True
        config['face']['gaze']['x'] = .3
        result = inspect(files, config, 'idle', 2.)
        self.assertTrue(result['passed']); self.assertEqual(len(result['variants']), 5)
        self.assertTrue(result['surviving_helper_tracks_identical'])


if __name__ == '__main__': unittest.main()
