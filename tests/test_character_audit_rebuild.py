"""Real job submission/worker/restart with fixture composition and Runtime stubs."""
from copy import deepcopy
import unittest
from unittest.mock import patch
from tests import test_character_jobs as job_fixtures
from autospine_workbench.automation.character_auto_audit import overview, save


class AuditRebuildTests(unittest.TestCase):
    def test_completed_job_rebuild_retains_exception_after_manager_restart(self):
        fixture=job_fixtures.CharacterJobsTests();fixture.setUp();self.addCleanup(fixture.doCleanups)
        def builder(*args, **kwargs):
            result=fixture.builder(*args, **kwargs)
            result['manifest']['layers']=[dict(layer_id='eye',name='eye',state='rigid_reviewed',
                binding_decision=dict(action='bind',option_id='rigid:head',decision_source='policy_auto',
                    evidence_current=True,decision_sha256='b'*64,policy_id='fixture-v1'))]
            return result
        manager=fixture.manager(builder)
        def submit():
            return manager.submit('sample','a'*64,'b'*64,'sleeve-job',residual_auto_profile='preserve')
        with patch('autospine_workbench.automation.character_auto_audit.context',side_effect=lambda m,p,j:m.get(p,j)), \
             patch('autospine_workbench.automation.character_stage_defaults.publish'):
            first=fixture.terminal(manager,submit())
            self.assertEqual(first['status'],'needs_review',first)
            receipt=save(manager,'sample',first['job_id'],dict(expected_artifact_sha256=first['artifact_sha256'],
                expected_review_sha256=None,reviews={'eye':'incorrect'}))
            second=fixture.terminal(manager,submit())
            self.assertNotEqual(first['job_id'],second['job_id'])
            self.assertEqual(first['artifact_sha256'],second['artifact_sha256'])
            manager.close();resumed=fixture.manager(builder)
            value=overview(resumed,'sample',second['job_id'])
            self.assertEqual(value['metrics']['carried_exception_layers'],1)
            self.assertEqual(value['metrics']['assessed_bindings'],0)
            self.assertEqual(value['exception_continuity']['exceptions'][0]['source_review_sha256'],receipt['review_sha256'])
            before=deepcopy(value)
            self.assertEqual(overview(resumed,'sample',second['job_id']),before)
