from copy import deepcopy
import unittest
from tests.test_rig_readiness import fixture
from autospine_workbench.automation.planning_semantics import collect
from autospine_workbench.asset.planning.rig_readiness_v2 import build
from autospine_workbench.resolved_project import canonical_sha256


class PlanningSemanticTests(unittest.TestCase):
    def test_saved_override_not_generated_role_is_imported(self):
        candidate = {'layers': [{'layer_id': 'layer-001', 'name': 'sleeve'}]}
        project = {'layers': [{'id': 'layer-001-sleeve', 'name': 'sleeve', 'semantic': {'role': 'body.arm'}}],
                   'overrides': {'layer_overrides': {}}}
        self.assertIsNone(collect(project, candidate, 'a' * 64)['layers'][0]['role'])
        project['overrides']['layer_overrides']['layer-001-sleeve'] = {'canonical_role': 'wear.sleeve'}
        self.assertEqual(collect(project, candidate, 'a' * 64)['layers'][0]['role'], 'wear.sleeve')
        project['layers'].append(deepcopy(project['layers'][0]))
        with self.assertRaises(ValueError):
            collect(project, candidate, 'a' * 64)

    def test_overlay_advances_only_geometry_review_preserves_plan(self):
        plan, bindings = fixture(); plan['layers'][0]['semantic'] = None
        before = deepcopy(plan)
        evidence = dict(resolved_project_sha256='a' * 64, layers=[dict(layer_id='arm',
                        authoring_layer_id='arm', role='wear.sleeve', source='saved_override')])
        result = build(plan, bindings, 'b' * 64, canonical_sha256(plan), evidence)
        self.assertEqual(result['layers'][0]['status'], 'needs_review')
        self.assertFalse(result['production_authorized']); self.assertEqual(plan, before)
        evidence['layers'][0]['role'] = None; evidence['layers'][0]['source'] = 'not_authored'
        self.assertEqual(build(plan, bindings, 'b' * 64, canonical_sha256(plan), evidence)['layers'][0]['status'], 'blocked')
        evidence['layers'][0]['layer_id'] = 'other'
        with self.assertRaises(ValueError):
            build(plan, bindings, 'b' * 64, canonical_sha256(plan), evidence)
