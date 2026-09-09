"""Conservative readiness never promotes an option or disconnected component."""
from copy import deepcopy
import json
from pathlib import Path
import unittest

from autospine_workbench.asset.planning.rig_readiness import build, validate
from autospine_workbench.resolved_project import canonical_sha256


def fixture():
    binding = {'layer_id': 'arm', 'image_sha256': 'a' * 64, 'options': [
        {'id': 'chain', 'mode': 'mesh_chain', 'bone_ids': ['upper', 'lower', 'hand']}]}
    bindings = {'bindings': [binding]}
    plan = {'authority': 'none', 'production_authorized': False,
            'scope': ['arm'], 'source_bindings_sha256': canonical_sha256(bindings),
            'layers': [{'layer_id': 'arm', 'image_sha256': 'a' * 64,
                        'strategy': 'weighted_mesh', 'semantic': 'body.arm',
                        'evidence': {'component_count': 1, 'bone_alpha_samples': [
                            {'bone_id': bone, 'opaque_samples': 2, 'samples': 21}
                            for bone in ['upper', 'lower', 'hand']]}}]}
    return plan, bindings


def inspect(plan, bindings):
    return build(plan, bindings, 'b' * 64, canonical_sha256(plan))


class RigReadinessTests(unittest.TestCase):
    def test_determinism_schema_and_no_mutation(self):
        plan, bindings = fixture(); before = deepcopy((plan, bindings))
        result = inspect(plan, bindings)
        self.assertEqual((plan, bindings), before)
        self.assertEqual(result, validate(plan, bindings, 'b' * 64, canonical_sha256(plan), result))
        self.assertEqual(result['layers'][0]['status'], 'needs_review')
        self.assertEqual(result['layers'][0]['mesh_option_ids'], ['chain'])
        self.assertFalse(result['production_authorized'])
        import jsonschema
        schema = json.loads(Path('schemas/rig-plan-readiness-v1.schema.json').read_text('utf-8'))
        jsonschema.validate(result, schema)

    def test_missing_semantics_and_partitions_fail_closed(self):
        for kind, semantic, reason in [
                ('weighted_mesh', None, 'garment_semantics_review_required'),
                ('semantic_review', 'wear.skirt', 'garment_semantics_review_required'),
                ('partition_mesh', 'body.leg', 'reviewed_partition_artifact_required')]:
            plan, bindings = fixture()
            plan['layers'][0].update(strategy=kind, semantic=semantic)
            row = inspect(plan, bindings)['layers'][0]
            self.assertEqual(row['status'], 'blocked')
            self.assertIn(reason, row['reason_codes'])

    def test_disconnected_or_partial_support_does_not_pass(self):
        for mutate, reason in [
                (lambda e: e.update(component_count=2), 'disconnected_alpha_ownership_review_required'),
                (lambda e: e['bone_alpha_samples'].pop(), 'supported_mesh_chain_evidence_missing'),
                (lambda e: e.update(component_count=0), 'no_opaque_alpha_support')]:
            plan, bindings = fixture(); mutate(plan['layers'][0]['evidence'])
            row = inspect(plan, bindings)['layers'][0]
            self.assertEqual(row['status'], 'blocked'); self.assertIn(reason, row['reason_codes'])

    def test_stale_tampered_and_nonfinite_evidence_rejected(self):
        plan, bindings = fixture(); digest = canonical_sha256(plan)
        plan['layers'][0]['semantic'] = None
        with self.assertRaisesRegex(ValueError, 'source_mismatch'):
            build(plan, bindings, 'b' * 64, digest)
        plan, bindings = fixture()
        plan['layers'][0]['evidence']['bone_alpha_samples'][0]['opaque_samples'] = float('nan')
        with self.assertRaises(ValueError): inspect(plan, bindings)
        plan, bindings = fixture(); doc = inspect(plan, bindings)
        doc['production_authorized'] = True
        with self.assertRaisesRegex(ValueError, 'replay_mismatch'):
            validate(plan, bindings, 'b' * 64, canonical_sha256(plan), doc)

    def test_ambiguous_options_and_duplicate_ids(self):
        plan, bindings = fixture()
        options = bindings['bindings'][0]['options']
        options.append({**options[0], 'id': 'alternative'})
        plan['source_bindings_sha256'] = canonical_sha256(bindings)
        row = inspect(plan, bindings)['layers'][0]
        self.assertEqual(row['status'], 'blocked')
        self.assertEqual(row['reason_codes'], ['mesh_chain_ambiguous'])
        options[-1]['id'] = 'chain'
        plan['source_bindings_sha256'] = canonical_sha256(bindings)
        with self.assertRaisesRegex(ValueError, 'duplicate_option'):
            inspect(plan, bindings)
