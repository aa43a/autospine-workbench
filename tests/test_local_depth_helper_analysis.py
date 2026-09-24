import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from autospine_workbench.targets.character43.local_depth_analysis import analyze, PROFILE, HELPER_PROFILE

MODULE='autospine_workbench.targets.character43.local_depth_analysis.'


class HelperAnalysisTests(unittest.TestCase):
    def test_explicit_model_identity_and_default_isolation(self):
        with TemporaryDirectory() as temp:
            folder=Path(temp);(folder/'map.json').write_text('{}')
            bundle=SimpleNamespace(path=folder,source_kind='kimodo_npz',raw_npz=b'',kimodo_source={})
            files={'skeleton.json':json.dumps({'bones':[{'name':'cloth','parent':'forearm_l'}]}).encode(),
                   'motion-depth.json':json.dumps({'pairs':[{'arm_slot':'arm','torso_slot':'body',
                     'samples':[{'tick':0,'source_tick':0}]}]}).encode()}
            with (patch(MODULE+'verify_source'),patch(MODULE+'KimodoDepthSampler') as sampler,
                  patch(MODULE+'Probe') as probe,patch(MODULE+'Checker') as checker):
                sampler.return_value.identity={'source':'verified'}
                sampler.return_value.interpolation='source_samples_only'
                probe.return_value.remaining=64000000
                checker.return_value.axes={}
                checker.return_value.check.return_value={'status':'no_overlap','time':0}
                default=analyze(files,'artifact',bundle,{'job_id':'job'})
                self.assertEqual(default['profile'],PROFILE)
                self.assertNotIn('sleeve_helpers',default)
                selected=analyze(files,'artifact',bundle,{'job_id':'job'},sleeve_helpers={'cloth':'forearm_l'})
                self.assertEqual(selected['profile'],HELPER_PROFILE)
                self.assertEqual(checker.call_args.kwargs['sleeve_helpers'],{'cloth':'forearm_l'})
                self.assertIn('not_observed',selected['helper_model_scope'])
                self.assertFalse(selected['selected'])
                for mapping in ({'cloth':'forearm_r'},{'missing':'forearm_l'},{'cloth':'chest'}):
                    with self.assertRaisesRegex(ValueError,'mapping_invalid'):
                        analyze(files,'artifact',bundle,{'job_id':'job'},sleeve_helpers=mapping)


if __name__=='__main__':unittest.main()
