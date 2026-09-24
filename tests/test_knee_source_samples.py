from copy import deepcopy
from unittest.mock import patch
import json

from test_motion_rotation_status import RotationStatusTests
from autospine_workbench.targets.character43.knee_source_samples import read
from autospine_workbench.targets.character43.knee_projection import build
from autospine_workbench.targets.character43.motion_clip import clip_motion
from autospine_workbench.targets.character43.oblique_target import prepare


class KneeSourceTests(RotationStatusTests):
    def test_clipped_knees_use_player_times_and_keep_source_times(self):
        self.request['clip'] = dict(start_frame=1, end_frame=2)
        motion = clip_motion(self.bundle.motion, (500000, 1000000))
        files = self.files(motion); original = deepcopy(files)
        name,vectors,times,source_times = read(files,self.bundle,self.request)
        self.assertEqual((name,times,source_times), ('test',[0,.5],[.5,1]))
        self.assertTrue(all(len(v)==2 for v in vectors.values()))
        with patch('autospine_workbench.targets.character43.knee_projection.inspect',
                   return_value=dict(rows=[dict(time=0),dict(time=.5)])) as inspect:
            report=build(files,'artifact',self.bundle,self.request)
        self.assertEqual([r['source_time'] for r in report['rows']],[.5,1])
        self.assertEqual(inspect.call_args.args[1],'test')
        self.assertEqual(files,original)

    def test_knee_candidate_identity_view_and_clip_are_verified(self):
        files=self.files(self.bundle.motion)
        self.request['projection']=dict(profile='constant-yaw-source-motion-v1',yaw_degrees=30)
        with self.assertRaisesRegex(ValueError,'motion_identity_mismatch'):
            read(files,self.bundle,self.request)
        motion,_=prepare(self.bundle,self.request['projection'])
        read(self.files(motion),self.bundle,self.request)
        self.request['character_sha256']='wrong'
        with self.assertRaisesRegex(ValueError,'source_identity_mismatch'):
            read(self.files(motion),self.bundle,self.request)

    def test_explicit_null_projection_and_ambiguous_animation(self):
        self.request['projection']=None
        files=self.files(self.bundle.motion)
        read(files,self.bundle,self.request)
        manifest=json.loads(files['character-manifest.json']);manifest['animations']=['a','b']
        files['character-manifest.json']=json.dumps(manifest).encode()
        with self.assertRaisesRegex(ValueError,'animation_ambiguous'):
            read(files,self.bundle,self.request)
