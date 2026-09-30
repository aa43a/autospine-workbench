import tempfile
import unittest
from pathlib import Path
from autospine_workbench.automation.sleeve_workflow import checkpoint,steps,code_identity


class SleeveWorkflowTests(unittest.TestCase):
    def test_launch_helper_change_changes_workflow_identity_and_rejects_old_checkpoint(self):
        names=('build-sleeve-weights.py','build-sleeve-helpers.py','export-sleeve-spine.py',
            'run-sleeve-workflow.py','verify-sleeve-core.mjs','check-sleeve-contacts.py',
            'check-sleeve-overlap.py','capture-sleeve-runtime.mjs','capture-process-options.mjs',
            'sleeve-framebuffer.js','sleeve-overlap-framebuffer.js','review-sleeve-framebuffer.py',
            'repair-sleeve-candidate.py','solve-retained-sleeve.py','build-ordinary-sleeve-stage.py',
            'export-ordinary-sleeve-workflow.py')
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);repo=root/'repo';tools=repo/'tools';tools.mkdir(parents=True)
            for name in names:(tools/name).write_text(name)
            signature=code_identity(repo);out=root/'outputs';calls=[]
            def execute():calls.append(1);out.mkdir();(out/'artifact.json').write_text('{}')
            checkpoint(root,'framebuffer',signature,out,execute)
            (tools/'capture-process-options.mjs').write_text('changed launch implementation')
            changed=code_identity(repo)
            self.assertNotEqual(changed,signature)
            with self.assertRaisesRegex(ValueError,'cached_output_changed'):
                checkpoint(root,'framebuffer',changed,out,execute)
            self.assertEqual(calls,[1])
    def test_ordinary_plan_skips_inapplicable_cloth_helper_stages(self):
        plan=steps(Path('/repo'),Path('/drafts'),Path('/run'),'fixture',Path('/state'),Path('/workspace'),ordinary_only=True)
        self.assertEqual([p[0] for p in plan],['weights','ordinary-repair','ordinary-deform','ordinary-interpolation','spine','contacts','overlap'])
        self.assertEqual(plan[1][2][plan[1][2].index('--input')+1],str(Path('/run/weights')))
        self.assertEqual(plan[4][2][plan[4][2].index('--input')+1],str(Path('/run/ordinary-interpolation')))
        self.assertIn('export-ordinary-sleeve-workflow.py',str(plan[4][2]))

    def test_resume_verifies_bytes_and_rejects_tampering(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);out=root/'outputs';calls=[]
            def execute():
                calls.append(1);out.mkdir();(out/'artifact.json').write_text('{}')
            self.assertFalse(checkpoint(root,'mesh','a'*64,out,execute)['cached'])
            self.assertTrue(checkpoint(root,'mesh','a'*64,out,execute)['cached'])
            self.assertEqual(len(calls),1)
            (out/'artifact.json').write_text('{"changed":true}')
            with self.assertRaisesRegex(ValueError,'cached_output_changed'):checkpoint(root,'mesh','a'*64,out,execute)
            self.assertEqual(len(calls),1)

    def test_failed_stage_has_no_success_receipt_and_can_resume(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);out=root/'output'
            def fail():raise ValueError('simulated_failure')
            with self.assertRaises(ValueError):checkpoint(root,'mesh','a'*64,out,fail)
            self.assertFalse((root/'receipts/mesh.json').exists())
            def succeed():out.mkdir();(out/'data').write_bytes(b'recovered')
            self.assertFalse(checkpoint(root,'mesh','a'*64,out,succeed)['cached'])

    def test_plan_has_retained_chain_and_no_experimental_weight_changes(self):
        plan=steps(Path('/repo'),Path('/drafts'),Path('/run'),'fixture',Path('/state'),Path('/workspace'))
        self.assertEqual([p[0] for p in plan],['weights','root','interface','anchors','motion','connection','boundary','cuff','repair','spine','contacts','overlap'])
        self.assertIn('--boundary-budget',plan[7][2])
        self.assertIn('--cuff-harmonic',plan[7][2])
        self.assertIn('--edge-budget',plan[7][2])
        self.assertEqual(plan[8][2][plan[8][2].index('--input')+1],str(Path('/run/cuff')))
        self.assertEqual(plan[9][2][plan[9][2].index('--input')+1],str(Path('/run/repair')))
        self.assertEqual(plan[10][2][plan[10][2].index('--input')+1],str(Path('/run/spine')))
        self.assertTrue(all('--rigid-hand' not in p[2] and '--joint-solver' not in p[2] for p in plan))
