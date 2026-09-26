from copy import deepcopy
from hashlib import sha256
import json
import unittest
from unittest.mock import patch

import test_motion_rotation_status as fixtures
from autospine_workbench.automation import motion_related_pose as pose
from autospine_workbench.automation.storage_io import canonical_bytes
from autospine_workbench.resolved_project import canonical_sha256
from autospine_workbench.targets.character43.oblique_target import prepare
from autospine_workbench.targets.character43.motion_clip import clip_motion


class RelatedPoseTests(unittest.TestCase):
    def setUp(self):
        self.f = fixtures.RotationStatusTests(); self.f.setUp(); self.addCleanup(self.f.doCleanups)
        self.request = self.f.request; self.bundle = self.f.bundle
        self.request['projection'] = dict(profile='constant-yaw-source-motion-v1', yaw_degrees=30)
        self.request['clip'] = dict(start_frame=1, end_frame=2)
        motion, _ = prepare(self.bundle, self.request['projection'])
        self.files = self.f.files(clip_motion(motion, (500000, 1000000)))
        skeleton = json.loads(self.files['skeleton.json'])
        bones = [dict(name='root', x=0, y=0, rotation=0)]
        for first, second, last in [('upperarm', 'forearm', 'hand'), ('thigh', 'calf', 'foot')]:
            for side in ('l', 'r'):
                a, b, c = [n+'_'+side for n in (first, second, last)]
                bones.extend([dict(name=a, parent='root', x=10 if side=='l' else -10, y=20, rotation=0),
                    dict(name=b, parent=a, x=10, y=0, rotation=0),
                    dict(name=c, parent=b, x=10, y=0, rotation=0)])
        skeleton['bones'] = bones
        self.files['skeleton.json'] = canonical_bytes(skeleton)

    def measure(self):
        return pose.measure(self.files, 'candidate', self.bundle, self.request)

    def receipt(self, audit):
        return dict(pose_audit=audit, source_identity=self.request['motion_identity'],
            candidate_bundle_sha256='candidate', source_request_sha256=canonical_sha256(self.request))

    def test_corrective_without_motionir_uses_own_view_clip_and_exact_final_bones(self):
        before = deepcopy(self.files); with_ir = self.measure()
        self.assertEqual(self.files, before)
        self.assertEqual(with_ir['times'], [0, .5]); self.assertEqual(with_ir['source_times'], [.5, 1])
        self.assertEqual(with_ir['yaw'], 30)
        self.assertEqual(len(with_ir['rows']), 8)
        del self.files['motion-ir.json']
        self.assertEqual(self.measure(), with_ir)
        skeleton = json.loads(self.files['skeleton.json'])
        skeleton['bones'][1]['rotation'] += 90
        self.files['skeleton.json'] = canonical_bytes(skeleton)
        changed = self.measure()
        self.assertNotEqual(changed['rows'], with_ir['rows'])
        self.assertNotEqual(changed['skeleton_sha256'], with_ir['skeleton_sha256'])
        self.assertFalse(changed['animation_modified'])

    def test_wrong_source_view_and_existing_motionir_are_rejected(self):
        self.request['projection']['yaw_degrees'] = -30
        with self.assertRaisesRegex(ValueError, 'motion_identity_mismatch'): self.measure()
        self.request['character_sha256'] = 'other'
        with self.assertRaisesRegex(ValueError, 'source_identity_mismatch'): self.measure()

    def test_saved_audit_is_recomputed_and_tampering_rejected(self):
        audit = self.measure(); receipt = self.receipt(audit)
        with patch.object(pose.VerifiedMotionBundleReader, 'load', return_value=self.bundle) as loader:
            pose.verify(self.files, receipt, self.f.bundle.path)
            self.assertEqual(loader.call_args.args, ('clip', 'bundle'))
            audit['rows'][0]['endpoint_error_ratio'] = 0
            with self.assertRaisesRegex(ValueError, 'measurement_changed'):
                pose.verify(self.files, receipt, self.f.bundle.path)
        receipt['source_request_sha256'] = 'different'
        with self.assertRaisesRegex(ValueError, 'source_identity'):
            pose.verify(self.files, receipt, self.f.bundle.path)

    def test_summary_keeps_worst_player_time_and_unknowns_without_admission(self):
        audit = self.measure()
        result = pose.summary(audit, 'candidate', sha256(self.files['skeleton.json']).hexdigest(),
            self.request['motion_identity'], canonical_sha256(self.request))
        self.assertEqual(result['samples'], 2)
        self.assertEqual(len(result['limbs']), 4)
        self.assertEqual(result['status'], 'requires_review')
        self.assertFalse(result['interpolated_frames_checked'])
        self.assertIn('no_depth_occlusion_or_visual_admission', result['limitations'])
        for row in result['limbs']:
            self.assertIn(row['worst_time'], [0, .5])
            self.assertAlmostEqual(row['source_time'], row['worst_time']+.5)
        with self.assertRaisesRegex(ValueError, 'pose_identity'):
            pose.summary(audit, 'other', audit['skeleton_sha256'], self.request['motion_identity'], audit['source_request_sha256'])
