from copy import deepcopy
import unittest
from autospine_workbench.targets.character43.attachment_root_bake import build
from autospine_workbench.targets.character43.affine_pose import sample


def fixture():
    bones = [dict(name='root'), dict(name='chest', parent='root', x=10, y=20),
             dict(name='cloth', parent='root', x=14, y=22), dict(name='tip', parent='cloth', y=10)]
    bones = [dict(x=0, y=0, rotation=0, length=1) | bone for bone in bones]
    mesh = dict(type='mesh', uvs=[0, 0, 1, 0, 0, 1], triangles=[0, 1, 2],
                vertices=[1, 2, 0, 0, 1, 1, 3, 0, 0, 1, 1, 2, 3, 0, 1])
    body = dict(type='mesh', uvs=[0, 0, 1, 0, 0, 1], triangles=[0, 1, 2],
                vertices=[1, 1, 0, 0, 1, 1, 1, 2, 0, 1, 1, 1, 0, 2, 1])
    doc = dict(bones=bones, slots=[dict(name=s, bone='root') for s in ('garment', 'body')],
        skins=[dict(name='default', attachments={'garment': {'garment': mesh}, 'body': {'body': body}})],
        animations={'motion': dict(bones={}, attachments={'default': {'garment': {'garment':
            {'deform': [dict(time=t, vertices=[.2, .3]*3) for t in (0, 1)],
             'sequence': [dict(time=0, index=0)]}}}})})
    torso = dict(applied=True, profile='reference-torso-plane-compensated-deform-v1-experiment',
        source=dict(records=[dict(time=t, longitudinal=1, shear=0, transverse=scale)
                             for t, scale in ((0, 1), (1, .5))]))
    return doc, torso


class RootBakeTests(unittest.TestCase):
    def test_only_declared_material_moves_and_other_channels_are_preserved(self):
        doc, torso = fixture(); before = deepcopy(doc)
        fixed, report = build(doc, 'motion', torso, ['cloth'], [0, .5, 1])
        self.assertEqual(doc, before)
        self.assertEqual(fixed['bones'], doc['bones'])
        self.assertEqual(fixed['skins'], doc['skins'])
        self.assertEqual(fixed['animations']['motion']['bones'], doc['animations']['motion']['bones'])
        self.assertEqual(fixed['animations']['motion']['attachments']['default']['garment']['garment']['sequence'],
                         doc['animations']['motion']['attachments']['default']['garment']['garment']['sequence'])
        original, _ = sample(doc, 'motion', 1); actual, _ = sample(fixed, 'motion', 1)
        self.assertEqual(original['body'], actual['body'])
        for a, b in zip(original['garment'], actual['garment']):
            self.assertAlmostEqual(a[0], b[0]); self.assertAlmostEqual(a[1]-1, b[1])
        self.assertEqual(report['maximum_root_shift_px'], 1)
        self.assertFalse(report['selected'])

    def test_float32_collisions_are_recomputed_not_duplicate_keys(self):
        doc, torso = fixture()
        fixed, report = build(doc, 'motion', torso, ['cloth'], [0, .5, .500000001, 1])
        keys = fixed['animations']['motion']['attachments']['default']['garment']['garment']['deform']
        self.assertEqual([k['time'] for k in keys], [0, .5, 1])
        self.assertEqual(report['original_reference_samples'], 4)

    def test_no_matching_weights_invalid_scope_and_owner_descendant_rejected(self):
        doc, torso = fixture()
        for times in ([0, .5], [0, 1, 1], [float('nan'), 1]):
            with self.assertRaisesRegex(ValueError, 'times_invalid'):
                build(doc, 'motion', torso, ['cloth'], times)
        with self.assertRaisesRegex(ValueError, 'ancestry'):
            build(doc, 'motion', torso, ['cloth', 'tip'], [0, 1])
        doc['bones'].append(dict(name='unused', parent='root', x=0, y=0, rotation=0, length=1))
        with self.assertRaisesRegex(ValueError, 'no_affected_vertices'):
            build(doc, 'motion', torso, ['unused'], [0, 1])
        torso['applied'] = False
        with self.assertRaisesRegex(ValueError, 'baked_torso'):
            build(doc, 'motion', torso, ['cloth'], [0, 1])

    def test_declared_applied_report_cannot_override_source_limits(self):
        doc, torso = fixture()
        torso['source']['records'][1]['transverse'] = .2
        with self.assertRaisesRegex(ValueError, 'source_limits'):
            build(doc, 'motion', torso, ['cloth'], [0, 1])


if __name__ == '__main__':
    unittest.main()
