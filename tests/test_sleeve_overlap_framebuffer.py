import unittest
from copy import deepcopy
from autospine_workbench.targets.spine43.sleeve_overlap_framebuffer import summaries, render, MODES


class OverlapFramebufferTests(unittest.TestCase):
    def fixture(self):
        peak=dict(time=.5,triangles=[2,7]);source=dict(tracks=[dict(animation='hand',visible_peak=peak)])
        captures=[]
        for phase,count in [('setup',0),('peak',1)]:
            captures.append(dict(animation='hand',phase=phase,pair=[2,7],software_peak=peak,time=0 if phase=='setup' else .5,
                index=0 if phase=='setup' else 64,dual_alpha8_pixels=count,max_alpha_increase=10 if count else 0,
                roi=dict(x=0,y=0,width=10,height=10),
                dual_samples=[dict(first_alpha=30,second_alpha=10,alpha_increase=10,world_xy=[.5,.5])] if count else [],
                images=[dict(mode=m) for m in MODES]))
        return dict(scope='software_visible_peak_pairs_setup_and_same_frame',status='needs_review',captures=captures),source

    def test_real_double_coverage_is_not_automatically_admitted(self):
        row=summaries(*self.fixture())[0]
        self.assertEqual(row['excess_pixels'],1);self.assertEqual(row['status'],'needs_review')
        self.assertFalse(row['production_authorized'])

    def test_wrong_phase_pose_pair_counts_or_missing_images_rejected(self):
        capture,source=self.fixture()
        changes=[lambda c:c['captures'].pop(),lambda c:c['captures'].append(c['captures'][0]),
            lambda c:c['captures'][1].update(pair=[2,3]),lambda c:c['captures'][1].update(index=65),
            lambda c:c['captures'][1].update(dual_alpha8_pixels=0),lambda c:c['captures'][1].update(images=[]),
            lambda c:c['captures'][1].update(max_alpha_increase=0)]
        for change in changes:
            value=deepcopy(capture);change(value)
            with self.assertRaises(ValueError):summaries(value,source)

    def test_overlay_rejects_nonfinite_and_outside_coordinates(self):
        for xy in ([float('nan'), 1], [10, 1], [1, -1]):
            capture, source = self.fixture()
            capture['captures'][1]['dual_samples'][0]['world_xy'] = xy
            with self.assertRaisesRegex(ValueError, 'overlap_capture_location'):
                summaries(capture, source)
        capture, source = self.fixture()
        capture['captures'][1]['roi']['width'] = 0
        with self.assertRaisesRegex(ValueError, 'overlap_capture_roi'):
            summaries(capture, source)

    def test_context_and_pixel_marks_use_same_frame_y_up_conversion(self):
        capture, source = self.fixture()
        for sample in capture['captures']:
            sample['context'] = {'file': 'context.png'}
            for image in sample['images']: image['file'] = image['mode']+'.png'
        html = render(capture, summaries(capture, source), lambda p:p,
                      dict(width=30, height=40, left=-5, bottom=-2))
        self.assertIn('rect x="5" y="28" width="10" height="10"', html)
        self.assertIn('rect x="0.0" y="9.0" width="1" height="1"', html)
        self.assertEqual(html.count('src="context.png"'), 1)
