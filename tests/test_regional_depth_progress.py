from contextlib import ExitStack
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from autospine_workbench.targets.character43.regional_depth_candidate import build
from autospine_workbench.automation.motion_intake_process import progress, read_progress


class RegionalProgressTests(unittest.TestCase):
    def test_worker_progress_round_trip_and_unknown_step_rejection(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            for stage in ('torso_projection', 'depth_partition', 'depth_refinement', 'depth_cloth_constraints',
                          'depth_limb_constraints', 'depth_ordering'):
                progress(root, stage)
                self.assertEqual(read_progress(root), stage)
            with self.assertRaisesRegex(ValueError, 'motion_progress_invalid'):
                progress(root, 'arbitrary_step')
            self.assertEqual(read_progress(root), 'depth_ordering')

    def test_progress_describes_stages_without_changing_result(self):
        stages = []
        depth = dict(profile='test', pairs=[dict(samples=[dict(source_tick=0), dict(source_tick=1)])])
        partition = dict(regions=[])
        module = 'autospine_workbench.targets.character43.'
        with ExitStack() as stack:
            stack.enter_context(patch(module+'depth_region_partition.build', return_value=({}, partition)))
            stack.enter_context(patch(module+'motion_depth.build', return_value=depth))
            stack.enter_context(patch(module+'regional_depth_candidate.SegmentDepthSampler'))
            stack.enter_context(patch(module+'regional_depth_candidate.Probe'))
            stack.enter_context(patch(module+'regional_depth_candidate.refine', return_value=(depth, {})))
            for name in ('cloth_depth_constraints', 'limb_depth_constraints'):
                stack.enter_context(patch(module+name+'.build', return_value=(depth, dict(unmeasured_samples=0))))
            stack.enter_context(patch(module+'regional_depth_candidate.order_build', return_value=(None, dict(status='blocked'))))
            args = dict(partition_slots=['a'], cloth_constraints=True, limb_constraints=True)
            plain = build({}, {}, 'test', depth, None, {}, **args)
            tracked = build({}, {}, 'test', depth, None, {}, on_stage=stages.append, **args)
        self.assertEqual(plain, tracked)
        self.assertEqual(stages, ['depth_partition', 'depth_refinement', 'depth_cloth_constraints',
                                  'depth_limb_constraints', 'depth_ordering'])
