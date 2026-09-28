from copy import deepcopy
import json
from pathlib import Path
import struct
import unittest

from autospine_workbench.targets.character43.joint_animation_qa import geometry_report
from autospine_workbench.targets.character43.joint_face_config import defaults, sample_times
from autospine_workbench.targets.character43.joint_spring import grid


class JointFaceGeometryBoundsTests(unittest.TestCase):
    def fixture(self):
        row = dict(animation='body', slot='eye', passed=False, min_area_ratio=.08,
                   max_area_ratio=1., max_edge_stretch=1., inversion_samples=0)
        raw = dict(records=[row], passed=False)
        inventory = dict(parts=[dict(slot='eye', role='white')])
        face = dict(channels={'eye': dict(min_scale_x=1., min_scale_y=.08)})
        baseline = dict(records=[dict(row, passed=True, min_area_ratio=1.)])
        return raw, inventory, face, baseline

    def test_smaller_positive_eye_than_declared_scale_is_not_accepted(self):
        raw, inventory, face, baseline = self.fixture()
        self.assertTrue(geometry_report(raw, inventory, True, face_report=face, source_geometry=baseline)['passed'])
        raw['records'][0]['min_area_ratio'] = .01
        result = geometry_report(raw, inventory, True, face_report=face, source_geometry=baseline)
        self.assertFalse(result['passed'])
        self.assertEqual(result['records'][0]['controlled_compression_limits']['min_area_ratio'], .08)

    def test_baseline_compression_is_combined_without_erasing_old_failure(self):
        raw, inventory, face, baseline = self.fixture()
        baseline['records'][0]['min_area_ratio'] = .8
        raw['records'][0]['min_area_ratio'] = .064
        self.assertTrue(geometry_report(raw, inventory, True, face_report=face, source_geometry=baseline)['passed'])
        baseline['records'][0]['passed'] = False
        self.assertFalse(geometry_report(raw, inventory, True, face_report=face, source_geometry=baseline)['passed'])

    def test_missing_or_invalid_evidence_never_relaxes_generic_failures(self):
        raw, inventory, face, baseline = self.fixture()
        self.assertFalse(geometry_report(raw, inventory, True)['passed'])
        for bad in [0, -1, float('nan'), float('inf')]:
            face['channels']['eye']['min_scale_y'] = bad
            self.assertFalse(geometry_report(raw, inventory, True, face_report=face, source_geometry=baseline)['passed'])

    def test_template_accounts_for_parent_mouth_scale_and_never_relaxes_stretch(self):
        raw, _, _, baseline = self.fixture()
        baseline['records'][0]['slot'] = 'mouth'
        row = raw['records'][0]; row.update(slot='template', min_area_ratio=.85*.12)
        inventory = dict(parts=[dict(slot='template', role='mouth')])
        face = dict(channels={'mouth': dict(min_scale_x=.85, min_scale_y=1),
                              'template': dict(min_scale_x=1, min_scale_y=.12)},
                    generated_templates=[dict(slot='template', parent_slot='mouth')])
        self.assertTrue(geometry_report(raw, inventory, True, face_report=face, source_geometry=baseline)['passed'])
        row['max_edge_stretch'] = 2.001
        self.assertFalse(geometry_report(raw, inventory, True, face_report=face, source_geometry=baseline)['passed'])

    def test_real_alice_passes_but_out_of_bound_eye_is_rejected(self):
        root = Path('workspace/builds/animated-preview-v1')
        source = root/'8b1a2c9f30d9d341828fd8931faa3e1d2d2f15c7109cec7574d98764e89f3d7b'
        result = root/'04a612d4798dc38814ad58e6081e1b85fa5c1f7029856ce97bd35727c8df26a1'
        if not result.is_dir(): self.skipTest('local M5 Alice artifact unavailable')
        read = lambda p: json.loads(p.read_bytes())
        raw = read(result/'generic-deformation.json'); joint = read(result/'joint-animation.json')
        kwargs = dict(face_report=joint['face'], source_geometry=read(source/'deformation.json'))
        self.assertTrue(geometry_report(raw, joint['inventory']['face'], True, **kwargs)['passed'])
        damaged = deepcopy(raw)
        eye = next(r for r in damaged['records'] if r['slot'] == 'layer-015')
        eye['min_area_ratio'] = .01
        self.assertFalse(geometry_report(damaged, joint['inventory']['face'], True, **kwargs)['passed'])

    def test_face_secondary_grids_share_exact_samples_for_stored_durations(self):
        for duration in [9.933333, 19.966667, 30.]:
            config = defaults(); config['blink']['enabled'] = False
            facial = sample_times(config, [0., duration])
            secondary = grid(duration)[::2]
            self.assertEqual(facial, secondary)
            combined = sorted(set(facial)|{(a+b)/2 for a,b in zip(facial,facial[1:])})
            unique = {struct.pack('<f',t) for t in combined}
            self.assertEqual(len(unique), len(grid(duration)))
            if duration == 19.966667:
                self.assertEqual(len(unique), 2397)


if __name__ == '__main__':
    unittest.main()
