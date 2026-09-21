from copy import deepcopy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest

from test_mixamo_map import source
from autospine_workbench.bvh_parser import parse_bvh
from autospine_workbench.bvh_motion_compiler import compile_bvh_motion
from autospine_workbench.motion2d.mixamo_map import build_map
from autospine_workbench.targets.character43.motion_rotation_status import build
from autospine_workbench.targets.character43.motionir_candidate import ROLES
from autospine_workbench.targets.character43.oblique_target import prepare
from autospine_workbench.targets.character43.motion_clip import clip_motion


class RotationStatusTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        raw = source().replace(b'Frames: 2', b'Frames: 3')
        raw += raw.splitlines()[-1]+b'\n'
        bvh = parse_bvh(raw)
        mapping = build_map(bvh, clip_id='rotation.status', reference_length=10,
                            screen_x='+X', screen_y='-Y', depth='+Z')
        path = Path(self.temp.name); (path/'map.json').write_text(json.dumps(mapping))
        self.bundle = SimpleNamespace(path=path, source_kind='bvh', raw_bvh=raw,
            motion=compile_bvh_motion(raw, mapping).document)
        self.request = dict(source_job_id='source', character_sha256='character',
            motion_identity=dict(clip_sha256='clip', bundle_sha256='bundle'))

    def files(self, motion):
        bones = {ROLES[t['target']]: {'rotate': [dict(time=k['tick']/motion['ticks_per_second'],
                 value=-k['value']) for k in t['keys']]}
                 for t in motion['tracks'] if t['property']=='rotation'}
        return {name: json.dumps(value).encode() for name, value in {
            'character-manifest.json': dict(source_motion_bundle_sha256='bundle',
                source_character_sha256='character', animations=['test']),
            'motion-ir.json': motion, 'skeleton.json': {'animations': {'test': {'bones': bones}}}}.items()}

    def test_exact_candidate_unchanged_and_extra_turn_detected(self):
        files = self.files(self.bundle.motion); before = deepcopy(files)
        report = build(files, 'artifact', self.bundle, self.request)
        self.assertEqual(files, before)
        self.assertTrue(all(not r['extra_turn_suspected'] for r in report['target']['records']))
        skeleton = json.loads(files['skeleton.json'])
        skeleton['animations']['test']['bones']['upperarm_l']['rotate'][-1]['value'] += 360
        files['skeleton.json'] = json.dumps(skeleton).encode()
        changed = build(files, 'new-artifact', self.bundle, self.request)
        self.assertTrue(next(r for r in changed['target']['records'] if r['bone']=='upperarm_l')['extra_turn_suspected'])

    def test_oblique_direction_and_motion_must_use_same_view(self):
        self.request['projection'] = dict(profile='constant-yaw-source-motion-v1', yaw_degrees=30)
        motion, _ = prepare(self.bundle, self.request['projection'])
        report = build(self.files(motion), 'artifact', self.bundle, self.request)
        self.assertEqual(report['projection']['yaw_degrees'], 30)
        self.assertTrue(all(r['maximum_transfer_difference_deg']==0 for r in report['target']['records']))
        with self.assertRaisesRegex(ValueError, 'motion_identity_mismatch'):
            build(self.files(self.bundle.motion), 'artifact', self.bundle, self.request)

    def test_wrong_source_rejected(self):
        self.request['character_sha256'] = 'other'
        with self.assertRaisesRegex(ValueError, 'source_identity_mismatch'):
            build(self.files(self.bundle.motion), 'artifact', self.bundle, self.request)

    def test_clipped_events_use_player_time_not_source_time(self):
        self.request['clip'] = dict(start_frame=1, end_frame=2)
        motion = clip_motion(self.bundle.motion, (500000, 1000000))
        report = build(self.files(motion), 'artifact', self.bundle, self.request)
        self.assertEqual(report['source']['times'], [0, .5])
        self.assertTrue(all(r['maximum_transfer_difference_deg']==0 for r in report['target']['records']))


if __name__ == '__main__': unittest.main()
