from copy import deepcopy
import unittest
from autospine_workbench.motion_builtin import build_builtin_motion
from autospine_workbench.targets.character43.motionir_candidate import build, sample


def fixture():
    bones = [dict(name='root', x=0, y=0, rotation=0)]
    for side in ('l', 'r'):
        for chain in [('thigh', 'calf', 'foot'), ('upperarm', 'forearm', 'hand')]:
            parent = 'root'
            for name in chain:
                name += '_'+side
                bones.append(dict(name=name, parent=parent, x=10, y=0, rotation=0))
                parent = name
    return dict(bones=bones, animations={'existing': {'bones': {}}},
                skins=[dict(attachments={'point': {'point': {'vertices': [1, 0, 0, 0, 1]}}})])


def motion():
    m = build_builtin_motion('idle').document
    m['loop'] = False
    m['tracks'] = [dict(target_kind='bone_role', target='humanoid.root', property=p,
                        interpolation='linear', keys=[dict(tick=0, value=a),
                        dict(tick=m['duration_ticks'], value=b)])
                   for p, a, b in [('rotation', 0, 90), ('translation', [0, 0], [1, 1])]]
    m['markers'] = []
    return m


class CandidateTests(unittest.TestCase):
    def test_coordinate_signs_and_root_translation(self):
        source = fixture()
        before = deepcopy(source)
        candidate, evidence = build(source, motion(), 'walk')
        points, bones = sample(candidate, 'walk', 2)
        self.assertEqual(source, before)
        self.assertEqual(candidate['animations']['existing'], source['animations']['existing'])
        self.assertEqual(evidence['reference_length_px'], 20)
        self.assertEqual(points['point'][0], [20, -20])
        self.assertEqual(bones['root'], (20, -20, -90))
        self.assertEqual(evidence['status'], 'preview_only')

    def test_wrong_leg_topology_and_duplicate_clip_fail(self):
        source = fixture()
        source['bones'][2]['parent'] = 'root'
        with self.assertRaisesRegex(ValueError, 'topology'):
            build(source, motion(), 'walk')
        with self.assertRaisesRegex(ValueError, 'name_conflict'):
            build(fixture(), motion(), 'existing')

    def test_unsupported_ik_is_not_silently_dropped(self):
        with self.assertRaisesRegex(ValueError, 'unsupported'):
            build(fixture(), build_builtin_motion('wave.left').document, 'wave')
