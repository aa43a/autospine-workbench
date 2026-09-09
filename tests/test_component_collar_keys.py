from copy import deepcopy
import unittest
from tests.test_component_weight_transition import limb_fixture
from autospine_workbench.asset.planning.component_mesh import build as mesh_build
from autospine_workbench.asset.planning.component_weight_transition import build as transition_build
from autospine_workbench.asset.planning.component_local_correction import build as correction_build
from autospine_workbench.asset.planning.component_collar import build as collar_build
from autospine_workbench.asset.planning.component_collar_keys import build,score


class ComponentCollarKeyTests(unittest.TestCase):
    def test_deterministic_keys_and_unchanged_source(self):
        args=limb_fixture();source=transition_build(mesh_build(*args),args[1],args[0])
        correction=correction_build(source,args[1]);collar=collar_build(source,correction,args[1]);original=deepcopy(collar)
        result=build(source,collar,args[1])
        self.assertEqual(result,build(source,collar,args[1]));self.assertEqual(original,collar)
        for c in result['comparisons']:
            self.assertTrue(all(a<=b for a,b in zip(score(c['after']),score(c['before']))))
            for trial in c['trials']:
                if trial['selected']:
                    self.assertEqual(trial['new_failure_times'],[]);self.assertEqual(trial['new_inversion_times'],[])
        collar['source_sha256']='0'*64
        with self.assertRaises(ValueError):build(source,collar,args[1])
