import json
import unittest
from types import SimpleNamespace
from autospine_workbench.automation.character_texture_trial import enrich_existing


class ResidualSummaryTests(unittest.TestCase):
    def test_old_job_reads_exact_report_without_mutating_history(self):
        report={'rows':[{'layer_id':'layer-1','region_id':'rest','counts':{'transferred':5,'outside_mesh':3}}]}
        reads=[]
        def read(digest):
            reads.append(digest)
            return {'residual-transfer.json':json.dumps(report).encode()}
        source={'artifact_sha256':'a'*64,'texture_trial':{'profile':'aligned-low-alpha-v1'}}
        result=enrich_existing(SimpleNamespace(read=read),source)
        self.assertEqual(reads,['a'*64])
        self.assertNotIn('regions',source['texture_trial'])
        self.assertEqual(result['texture_trial']['regions'][0]['remaining_pixels'],3)
        self.assertIs(enrich_existing(SimpleNamespace(read=read),result),result)
        self.assertEqual(len(reads),1)
