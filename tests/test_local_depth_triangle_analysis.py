import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch
import unittest

from autospine_workbench.targets.character43.local_depth_analysis import analyze

MODULE='autospine_workbench.targets.character43.local_depth_analysis.'


class TriangleAnalysisTests(unittest.TestCase):
    def test_trace_accumulates_tiles_and_marks_partial_failure(self):
        with TemporaryDirectory() as temp:
            root=Path(temp);(root/'map.json').write_text('{}')
            bundle=SimpleNamespace(path=root,source_kind='kimodo_npz',raw_npz=b'',kimodo_source={})
            files={'skeleton.json':b'{"bones":[]}', 'motion-depth.json':json.dumps(dict(pairs=[dict(
                arm_slot='arm',torso_slot='body',samples=[dict(tick=0,source_tick=0)])])).encode()}
            with (patch(MODULE+'verify_source'),patch(MODULE+'KimodoDepthSampler') as sampler,
                  patch(MODULE+'Probe') as probe,patch(MODULE+'Checker') as checker):
                sampler.return_value.identity={};sampler.return_value.interpolation='source_samples_only'
                probe.return_value.remaining=64000000;checker.return_value.axes={}
                def measured(*args,**kwargs):
                    callback=kwargs.get('on_triangle')
                    if callback:
                        callback(2,dict(front=2,back=1));callback(2,dict(front=1))
                    return dict(status='requires_partition_or_more_depth',time=0,
                                overlap_pixels=4,counts=dict(front=3,back=1,ambiguous=0,unknown=0))
                checker.return_value.check.side_effect=measured
                normal=analyze(files,'artifact',bundle,{'job_id':'job'})
                traced=analyze(files,'artifact',bundle,{'job_id':'job'},triangle_traces=True)
                self.assertEqual(normal['counts'],traced['counts'])
                self.assertEqual(normal['causes'],traced['causes'])
                self.assertNotIn('triangle_observations',normal['records'][0])
                row=traced['records'][0]
                self.assertEqual(row['triangle_observations'],[dict(triangle=2,counts=dict(front=3,back=1))])
                self.assertTrue(row['trace_complete'])
                self.assertIn('may_overlap',row['triangle_scope'])
                def failed(*args,**kwargs):
                    kwargs['on_triangle'](2,dict(front=1))
                    raise ValueError('pixel_budget')
                checker.return_value.check.side_effect=failed
                row=analyze(files,'artifact',bundle,{'job_id':'job'},triangle_traces=True)['records'][0]
                self.assertFalse(row['trace_complete'])
                self.assertEqual(row['check']['status'],'unmeasured')

    def test_traces_require_pixel_classification(self):
        for options in (dict(triangle_traces=True,pixelwise=False),dict(triangle_traces='yes')):
            with self.assertRaisesRegex(ValueError,'requires_pixels'):
                analyze({},'',None,{},**options)
