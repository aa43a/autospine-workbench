import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from test_limb_transverse_repair import fixture
from autospine_workbench.automation.storage_io import canonical_bytes
from autospine_workbench.targets.character43.limb_transverse_repair import build as compensate
from m4_joint_boundary_animation import run


class BoundaryMarginWorkflowTests(unittest.TestCase):
    def test_accumulation_reaches_solver_and_retains_each_source_time(self):
        parent=fixture();parent['animations']['external-motion']=parent['animations'].pop('motion')
        candidate,_=compensate(parent,'external-motion',['leg'])
        captured={}
        def bake(parent,candidate,name,slot,times,**kwargs):
            captured.update(times=times,margins=kwargs['solver_margins'])
            return candidate,dict(local_constraints_passed=False,key_count=2,times=times,failures=[1])
        with TemporaryDirectory() as directory:
            root=Path(directory)
            for name,t in [('source',.1),('old',.3),('increment',.7)]:
                path=root/name;path.mkdir()
                (path/'report.json').write_bytes(canonical_bytes(dict(parent_artifact_sha256='parent',times=[0.,t,1.])))
                (path/'skeleton.json').write_bytes(canonical_bytes(candidate))
            (root/'source/validation-times.json').write_bytes(canonical_bytes([0.,.1,1.]))
            measurements=[({0.:[.019],1.:[.01]},{}),({0.:[.002],1.:[0.]},{})]
            with patch('m4_joint_boundary_animation.validate_times'), \
                 patch('m4_joint_boundary_animation.AnimatedStore') as store, \
                 patch('m4_joint_boundary_animation.compensate',return_value=(candidate,{})), \
                 patch('m4_joint_boundary_animation.build',side_effect=bake), \
                 patch('autospine_workbench.targets.character43.joint_boundary_margin.measure',side_effect=measurements):
                store.return_value.read.return_value={'skeleton.json':canonical_bytes(parent)}
                run(root,'parent','leg',root/'source',root/'out',margin_source=root/'old',margin_increments=[root/'increment'])
            self.assertEqual(captured['times'],[0.,.1,.3,.7,1.])
            self.assertEqual(captured['margins'][0.],[.02])
            self.assertEqual(captured['margins'][1.],[.01])
            self.assertTrue(all(v==[0.] for t,v in captured['margins'].items() if t not in (0.,1.)))
            report=json.loads((root/'out/report.json').read_bytes())
            self.assertEqual(report['margin_increments'][0]['accumulation']['capped_entries'],1)
            self.assertFalse(report['local_constraints_passed'])
