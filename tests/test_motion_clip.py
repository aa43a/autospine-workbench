"""Selection preserves pose values, clipping contacts without new source authority."""
from copy import deepcopy
from io import BytesIO
import json
from pathlib import Path
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from autospine_workbench.targets.character43.motion_clip import (
    validate, boundaries, clip_motion, clip_animation, selected_ratios)
from autospine_workbench.targets.character43.motionir_candidate import build, sample
from autospine_workbench.automation.motion_target_worker import build_candidate
from autospine_workbench.automation.motion_intake_jobs import MotionIntakeJobs
from autospine_workbench.automation.motion_reproject import submit
from autospine_workbench.automation.pipeline_run import PipelineRunError
from test_motion_target_intake import inputs
from test_mixamo_map import source


class MotionClipTests(unittest.TestCase):
    def test_frame_selection_is_bounded_and_never_coerces_boolean(self):
        for value in (dict(start_frame=True, end_frame=2), dict(start_frame=1, end_frame=1),
                      dict(start_frame=-1, end_frame=2), dict(start_frame=0, end_frame=3), {}):
            with self.assertRaisesRegex(ValueError, 'motion_clip_range_invalid'):
                validate(value, 3)
        self.assertEqual(boundaries(dict(start_frame=1, end_frame=2), [0, 33333, 66667]), (33333, 66667))

    def test_nonzero_clip_start_preserves_pose_and_intersects_contacts(self):
        files, motion, _, _ = inputs()
        motion = deepcopy(motion)
        duration = motion['duration_ticks']
        start, end = duration//4, duration*3//4
        motion['markers'] = [dict(kind='contact', limb='leg.left', start_tick=0, end_tick=duration, mode='annotation_only')]
        before = deepcopy(motion)
        clipped = clip_motion(motion, (start, end))
        self.assertEqual(motion, before)
        self.assertEqual(clipped['markers'][0]['start_tick'], 0)
        self.assertEqual(clipped['markers'][0]['end_tick'], end-start)
        doc = json.loads(files['skeleton.json']); doc['animations'] = {}
        original, _ = build(doc, motion, 'test')
        selected = clip_animation(original, 'test', (start, end))
        for tick in (0, (end-start)//2, end-start):
            actual = sample(selected, 'test', tick/1e6)[0]
            expected = sample(original, 'test', (start+tick)/1e6)[0]
            for layer, points in actual.items():
                for a, b in zip(points, expected[layer]):
                    for x, y in zip(a, b): self.assertAlmostEqual(x, y, places=7)
        from_motion, _ = build(doc, clipped, 'test')
        self.assertEqual(from_motion['animations'], selected['animations'])

    def test_outside_projection_failure_is_not_in_selected_range_but_baseline_must_work(self):
        values, times = selected_ratios([.8, .8, .7, .01], [0, 1, 2, 3], (1, 2))
        self.assertEqual(times, [1, 2])
        self.assertEqual(values, [1., .7/.8])
        with self.assertRaisesRegex(ValueError, 'character_length_projection_collapsed'):
            selected_ratios([.01, .8, .7], [0, 1, 2], (1, 2))

    def test_inverted_first_clip_frame_cannot_become_geometry_baseline(self):
        from autospine_workbench.targets.character43.numeric_reference import read, write
        from autospine_workbench.targets.character43.deformation_qa import inspect
        files, _, _ = build_candidate(*inputs(), character_digest='a'*64, motion_digest='b'*64)
        reference = read(files)
        frames = reference['animations']['external-motion']
        setup = deepcopy(frames[0]['vertices'])
        for frame in frames:
            frame['vertices'] = {name: [[-x, y] for x, y in points] for name, points in setup.items()}
        inverted = write(files, reference)
        self.assertTrue(inspect(inverted)['passed'])
        checked = inspect(inverted, setup_vertices=setup)
        self.assertFalse(checked['passed'])
        self.assertGreater(checked['records'][0]['inversion_samples'], 0)

    def test_target_clip_keeps_rig_and_produces_a_shorter_validated_candidate(self):
        data = inputs()
        duration = data[1]['duration_ticks']
        files, evidence, geometry = build_candidate(*data, character_digest='a'*64, motion_digest='b'*64,
            clip_bounds=(duration//4, duration*3//4))
        source_doc = json.loads(data[0]['skeleton.json'])
        doc = json.loads(files['skeleton.json'])
        self.assertEqual({k:v for k,v in doc.items() if k!='animations'},
                         {k:v for k,v in source_doc.items() if k!='animations'})
        self.assertEqual(json.loads(files['motion-ir.json'])['duration_ticks'], duration//2)
        self.assertEqual(evidence['clip']['pose_policy'], 'preserve_original_setup_relative_values')
        self.assertTrue(geometry['passed'])

    def test_reprojection_creates_distinct_task_and_rejects_changed_source(self):
        with tempfile.TemporaryDirectory() as temp:
            jobs = MotionIntakeJobs(SimpleNamespace(state_root=Path(temp)))
            self.addCleanup(jobs.close)
            raw = source()
            first = jobs.upload(BytesIO(raw), len(raw), 'test.bvh', 'front')
            deadline = time.monotonic()+15
            while jobs.get(first['job_id'])['status'] in ('pending','running') and time.monotonic()<deadline:
                time.sleep(.03)
            self.assertEqual(jobs.get(first['job_id'])['status'], 'succeeded')
            with patch.object(jobs._pool, 'submit'):
                second = submit(jobs, first['job_id'], dict(view='side'))
            self.assertNotEqual(first['job_id'], second['job_id'])
            self.assertEqual(second['derivation']['parent_job_id'], first['job_id'])
            self.assertEqual((jobs.folder(second['job_id'])/'source.bvh').read_bytes(), raw)
            (jobs.folder(first['job_id'])/'source.bvh').write_bytes(b'changed')
            with self.assertRaisesRegex(PipelineRunError, 'motion_source_changed'):
                submit(jobs, first['job_id'], dict(view='front'))


if __name__ == '__main__':
    unittest.main()
