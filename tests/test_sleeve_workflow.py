import tempfile
import unittest
from pathlib import Path
from autospine_workbench.automation.sleeve_workflow import checkpoint,steps


class SleeveWorkflowTests(unittest.TestCase):
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
        self.assertEqual([p[0] for p in plan],['weights','root','interface','anchors','motion','connection','boundary','cuff','spine','contacts','overlap'])
        self.assertIn('--boundary-budget',plan[7][2])
        self.assertIn('--cuff-harmonic',plan[7][2])
        self.assertIn('--edge-budget',plan[7][2])
        self.assertEqual(plan[8][2][plan[8][2].index('--input')+1],str(Path('/run/cuff')))
        self.assertEqual(plan[9][2][plan[9][2].index('--input')+1],str(Path('/run/spine')))
        self.assertTrue(all('--rigid-hand' not in p[2] and '--joint-solver' not in p[2] for p in plan))
