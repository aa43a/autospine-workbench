"""Observed visibility changes new previews without reinterpreting old manifests."""
from copy import deepcopy
import json
import unittest

from autospine_workbench.targets.spine43.source_visibility import normalize, PROFILE
from autospine_workbench.automation.animated_compile import prepare_mesh, compile_preview
from autospine_workbench.automation.animated_package import package_preview
from autospine_workbench.automation.character_coverage import build_coverage
from tests.test_animated_application import source_fixture


class SourceVisibilityTests(unittest.TestCase):
    def test_explicit_flags_win_and_legacy_is_unchanged(self):
        row={'observed':{'empty':True,'visible':False},'empty':False,'visible':True}
        original=deepcopy(row)
        self.assertIs(normalize(row),row)
        self.assertTrue(normalize(row,PROFILE)['visible'])
        self.assertFalse(normalize(row,PROFILE)['empty'])
        self.assertEqual(row,original)
        with self.assertRaisesRegex(ValueError,'profile'):normalize(row,'future')
        with self.assertRaisesRegex(ValueError,'flag'):normalize({'observed':{'visible':1}},PROFILE)

    def test_hidden_weighted_layer_is_absent_from_document_package_and_coverage(self):
        inputs=source_fixture();mesh=prepare_mesh(inputs)
        hidden=next(row for row in mesh['mesh']['layers'] if row.get('weights'))['layer_id']
        source=next(row for row in inputs.candidate['layers'] if row['layer_id']==hidden)
        source.pop('visible',None);source.pop('empty',None)
        source['observed']={'empty':False,'visible':False}
        compiled=compile_preview(inputs,mesh,'limb-flex-15')
        self.assertNotIn(hidden,{s['name'] for s in compiled['document']['slots']})
        files=package_preview(inputs,compiled)
        self.assertNotIn('images/'+hidden+'.png',files)
        scope=json.loads(files['preview-manifest.json'])
        self.assertEqual(scope['visibility_profile'],PROFILE)
        ledger=build_coverage(inputs.candidate,inputs.draft,inputs.bindings,
                              compiled['expanded_inputs'].candidate['layers'],scope,'a'*64)
        row=next(r for r in ledger['layers'] if r['layer_id']==hidden)
        self.assertEqual(row['state'],'not_visible')
        self.assertEqual(row['regions'],[])
        legacy=deepcopy(scope);legacy.pop('visibility_profile')
        old=build_coverage(inputs.candidate,inputs.draft,inputs.bindings,
                          compiled['expanded_inputs'].candidate['layers'],legacy,'a'*64)
        self.assertEqual(next(r for r in old['layers'] if r['layer_id']==hidden)['state'],'missing')

    def test_observed_empty_is_normalized_without_changing_source(self):
        source={'observed':{'empty':True,'visible':False}}
        result=normalize(source,PROFILE)
        self.assertTrue(result['empty']);self.assertFalse(result['visible'])
        self.assertNotIn('empty',source)


if __name__=='__main__':unittest.main()
