from copy import deepcopy
import json
from unittest import TestCase
from autospine_workbench.targets.character43.animation_compatibility import signature, compare


class CompatibilityTests(TestCase):
    def fixture(self):
        rig = dict(skeleton=dict(spine='4.3.26', hash='one'), bones=[dict(name='root', x=0)],
            slots=[dict(name='arm', bone='root')], skins=[dict(name='default', attachments={
                'arm': {'arm': dict(type='mesh', vertices=[1, 0, 1, 2, 1], uvs=[0, 1], triangles=[0, 1, 2])}})],
            animations={'wave': {'bones': {'root': {'rotate': [{'time': 0, 'value': 1}]}}}})
        files = {'skeleton.json': json.dumps(rig).encode(), 'skeleton.atlas': b'textures/a.png',
                 'textures/a.png': b'original texture'}
        return rig, files

    def test_different_animation_and_descriptive_hash_preserve_compatibility(self):
        rig, files = self.fixture()
        before = signature(files)
        rig['skeleton']['hash'] = 'two'
        rig['animations'] = {'idle': {}}
        changed = dict(files, **{'skeleton.json': json.dumps(rig).encode()})
        self.assertEqual(compare(before, signature(changed)), [])
        self.assertTrue(signature(changed)['runtime_recheck_required'])

    def test_setup_weights_uvs_and_slot_order_are_not_assumed_compatible(self):
        rig, files = self.fixture()
        baseline = signature(files)
        for section in ('bones', 'slots', 'skins'):
            changed = deepcopy(rig)
            if section == 'bones':
                changed['bones'][0]['x'] = 5
            elif section == 'slots':
                changed['slots'].append(dict(name='other', bone='root'))
            else:
                changed['skins'][0]['attachments']['arm']['arm']['vertices'][-1] = .5
            result = signature(dict(files, **{'skeleton.json': json.dumps(changed).encode()}))
            self.assertIn(section, compare(baseline, result))
        changed = deepcopy(rig)
        changed['skins'][0]['attachments']['arm']['arm']['uvs'][0] = .2
        self.assertIn('skins', compare(baseline, signature(dict(files, **{'skeleton.json': json.dumps(changed).encode()}))))

    def test_same_filename_changed_texture_is_incompatible(self):
        _, files = self.fixture()
        changed = dict(files, **{'textures/a.png': b'other texture'})
        self.assertEqual(compare(signature(files), signature(changed)), ['texture_assets'])
