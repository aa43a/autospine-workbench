from copy import deepcopy
from pathlib import Path
import unittest
from unittest.mock import patch

from test_sleeve_onboarding_source import inputs
from autospine_workbench.automation.sleeve_onboarding_source import build_inputs
from autospine_workbench.automation.sleeve_stale_save import recover
from autospine_workbench.resolved_project import canonical_sha256 as sha


class StaleSaveTests(unittest.TestCase):
    def test_exact_surface_retains_edits_but_saved_or_changed_surface_refuses(self):
        _,candidate,draft,_=build_inputs(inputs(),'fresh')
        newer=deepcopy(candidate); newer['source_sha256']='b'*64
        newdraft=deepcopy(draft);newdraft['candidate_sha256']=sha(newer)
        docs={sha(candidate):candidate,sha(newer):newer,sha(draft):draft,sha(newdraft):newdraft}
        old=dict(project_id='fresh',revision=1,source_sha256='a'*64,saved=False,
                 candidate_sha256=sha(candidate),draft_sha256=sha(draft))
        current=dict(old,revision=2,candidate_sha256=sha(newer),draft_sha256=sha(newdraft))
        edited=deepcopy(draft);edited['records'][0]['assignments'][0].update(role='hanging_cloth',origin='manual_edit')
        body=dict(expected_revision=1,expected_resolved_sha256='a'*64,draft=edited)
        with patch('autospine_workbench.automation.sleeve_stale_save.read_document',
                   side_effect=lambda path:old if path.name.endswith('001.json') else current):
            result,receipt=recover(Path('.'),'fresh',current,body,docs.__getitem__)
            self.assertEqual(result['records'],edited['records'])
            self.assertEqual(result['candidate_sha256'],sha(newer))
            self.assertEqual(receipt['submitted_draft_sha256'],sha(edited))
            current['saved']=True
            with self.assertRaisesRegex(RuntimeError,'conflict'):recover(Path('.'),'fresh',current,body,docs.__getitem__)
            current['saved']=False
            newer['records'][0]['source_image_sha256']='e'*64
            with self.assertRaises((RuntimeError,ValueError)):recover(Path('.'),'fresh',current,body,docs.__getitem__)

    def test_revision_bounds_refuse(self):
        for start in (True,0,3,-1):
            with self.assertRaisesRegex(RuntimeError,'conflict'):
                recover(Path('.'),'fresh',{'revision':2},{'expected_revision':start},lambda _:None)
