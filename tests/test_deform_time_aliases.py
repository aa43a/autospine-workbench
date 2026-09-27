from copy import deepcopy
import unittest
from autospine_workbench.targets.character43.deform_time_aliases import normalize
from autospine_workbench.targets.character43.runtime_storage_reference import stored_document
from test_limb_transverse_repair import fixture


class DeformTimeAliasesTests(unittest.TestCase):
    def source(self):
        original = fixture(); changed = deepcopy(original)
        keys = [dict(time=t,vertices=[t*1e-4,0.]*3) for t in (0,.5,.50000001,1)]
        changed['animations']['motion']['attachments'] = {'default':{'leg':{'leg':{'deform':keys}}}}
        return original, changed

    def test_resolves_generated_aliases_without_changing_bind_or_bones(self):
        original, doc = self.source(); before = deepcopy(doc)
        output, report = normalize(doc,original,'motion','leg')
        stored_document(output)
        self.assertEqual(report['collisions'],1); self.assertEqual(doc,before)
        for key in ('bones','slots','skins'):self.assertEqual(output[key],doc[key])
        self.assertEqual(output['animations']['motion']['bones'],doc['animations']['motion']['bones'])
        self.assertLessEqual(report['maximum_local_error'],1e-4)

    def test_large_collapsed_excursion_and_curved_tracks_are_rejected(self):
        original, doc = self.source()
        doc['animations']['motion']['attachments']['default']['leg']['leg']['deform'][2]['vertices']=[1.,0.]*3
        with self.assertRaisesRegex(ValueError,'error_limit'):normalize(doc,original,'motion','leg')
        original, doc = self.source()
        doc['animations']['motion']['attachments']['default']['leg']['leg']['deform'][0]['curve']='stepped'
        with self.assertRaisesRegex(ValueError,'dense_linear'):normalize(doc,original,'motion','leg')

    def test_existing_source_breakpoint_and_unselected_tracks_remain_exact(self):
        original, doc = self.source()
        prior=[dict(time=t,vertices=[0.]*6) for t in (0,.50000001,1)]
        original['animations']['motion']['attachments']={'default':{'leg':{'leg':{'deform':prior}}}}
        doc['animations']['motion']['attachments']['default']['other']={'other':{'deform':deepcopy(prior)}}
        output, report=normalize(doc,original,'motion','leg')
        self.assertEqual(report['rows'][0]['output_time'],.50000001)
        self.assertEqual(output['animations']['motion']['attachments']['default']['other'],
                         doc['animations']['motion']['attachments']['default']['other'])
