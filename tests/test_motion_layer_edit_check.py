import json
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
from test_motion_layer_edits import fixture, edits
from autospine_workbench.targets.character43.rig_edit_operations import apply_operations, empty
from autospine_workbench.automation.motion_layer_edit_check import check, verify
from autospine_workbench.automation.pipeline_run import PipelineRunError
from autospine_workbench.resolved_project import canonical_sha256


class EditOperationsTests(unittest.TestCase):
    def test_browser_and_headless_operations_agree(self):
        import subprocess
        doc=fixture(); slots=[row['name'] for row in doc['slots']]
        cases=[[dict(op='transform',slot='arm',values={'dx':3,'rotation':22})],
               [dict(op='order',slots=slots[::-1])], [dict(op='reset',slot='arm')],
               [dict(op='replace',value=None)], [dict(op='reset',slot='missing')]]
        for field, values in {'scaleX':[0,.05,20,21,True], 'rotation':[-3601,3600], 'dx':[-4096,4097]}.items():
            for value in values:cases.append([dict(op='transform',slot='arm',values={field:value})])
        script="""
import {applyRigEditOperations} from './web/modules/rig-edit-operations.js';
let input='';for await(const chunk of process.stdin)input+=chunk;
const {before,cases,layers}=JSON.parse(input);
console.log(JSON.stringify(cases.map(ops=>{const r=applyRigEditOperations(before,ops,{layers});return {ok:r.ok,value:r.value};})));
"""
        result=subprocess.run(['node','--input-type=module','-e',script],
            cwd=Path(__file__).resolve().parents[1],capture_output=True,text=True,check=True,
            input=json.dumps(dict(before=edits(),cases=cases,layers=[dict(slot=s,supported=True) for s in slots])))
        browser=json.loads(result.stdout)
        for ops, expected in zip(cases,browser):
            with self.subTest(ops=ops):
                actual=apply_operations(edits(),ops,doc)
                self.assertEqual(dict(ok=actual['ok'],value=actual['value']),expected)

    def test_atomic_failure_inverse_and_unknown(self):
        before=edits(); saved=deepcopy(before); doc=fixture()
        ops=[dict(op='transform',slot='arm',values={'dx':17}),dict(op='transform',slot='arm',values={'scaleX':0})]
        result=apply_operations(before,ops,doc)
        self.assertFalse(result['ok']);self.assertEqual(result['value'],saved);self.assertEqual(before,saved)
        self.assertEqual(result['diagnostics'][0]['operation'],1)
        ops[1]['values']['scaleX']=1.2
        result=apply_operations(before,ops,doc)
        self.assertTrue(result['ok'])
        self.assertEqual(apply_operations(result['value'],result['inverse'],doc)['value'],before)
        for op in [dict(op='delete'),dict(op='transform',slot='missing',values={}),
                   dict(op='transform',slot='arm',values={'dx':True}),dict(op='order',slots=['arm'])]:
            self.assertFalse(apply_operations(before,[op],doc)['ok'])


class EditCheckTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);(self.root/'motion-source').mkdir()
        self.source=dict(job_id='motion-source',kind='import',status='succeeded',result={'motion_status':'compiled'})
        self.character=dict(artifact_sha256='a'*64)
        chars=Mock();chars.verified_snapshot.return_value=(self.character,{})
        self.manager=SimpleNamespace(state_root=self.root,get=lambda job:deepcopy(self.source),
            folder=lambda job:self.root/job,character_manager=lambda:chars)
        self.body=dict(project_id='alice',character_job_id='job-character',baseline=None,
                       operations=[dict(op='replace',value=edits())])
        self.reader=patch('autospine_workbench.automation.animated_store.AnimatedStore.read',
                          return_value={'skeleton.json':json.dumps(fixture()).encode()})
        self.reader.start();self.addCleanup(self.reader.stop)

    def request(self):
        return dict(source_job_id='motion-source',source_job_sha256=canonical_sha256(self.source),
            project_id='alice',character_job_id='job-character',character_sha256='a'*64,layer_edits=edits())

    def test_receipt_reuses_exact_input_and_binds_all_dependencies(self):
        result=check(self.manager,'motion-source',self.body)
        self.assertEqual(result,check(self.manager,'motion-source',self.body))
        receipt=verify(self.manager,self.request(),result['receipt_sha256'])
        self.assertEqual(receipt['authority'],'none')
        self.assertEqual(receipt['result']['inverse'],[dict(op='replace',value=empty())])
        for field in ('source_job_sha256','character_job_id','character_sha256','project_id'):
            request=self.request();request[field]='changed'
            with self.assertRaisesRegex(PipelineRunError,'stale'):verify(self.manager,request,result['receipt_sha256'])
        request=self.request();request['layer_edits']['transforms'][0]['dx']=123
        with self.assertRaisesRegex(PipelineRunError,'edits_changed'):verify(self.manager,request,result['receipt_sha256'])

    def test_failed_batch_does_not_publish_and_tampered_receipt_rejected(self):
        self.body['operations'].append(dict(op='order',slots=['absent']))
        self.assertFalse(check(self.manager,'motion-source',self.body)['ok'])
        self.assertFalse((self.root/'motion-source'/'layer-edit-checks').exists())
        self.body['operations'].pop();result=check(self.manager,'motion-source',self.body)
        path=self.root/'motion-source'/'layer-edit-checks'/f"{result['receipt_sha256']}.json"
        path.write_text('{}',encoding='utf-8')
        with self.assertRaises(PipelineRunError):verify(self.manager,self.request(),result['receipt_sha256'])

    def test_route_uses_explicit_post_and_preflight_returns_200(self):
        from test_motion_adapt_route_body import handler_for
        from autospine_workbench.automation.motion_intake_routes import dispatch_motions
        handler=handler_for(json.dumps(self.body).encode())
        with patch('autospine_workbench.automation.motion_layer_edit_check.check',return_value={'ok':True}) as run:
            self.assertTrue(dispatch_motions(['api','motions','motion-source','layer-edit-check'],handler,'POST'))
            self.assertEqual(run.call_args.args[2],self.body)
            handler._send_visual_json.assert_called_once_with(200,{'ok':True})
