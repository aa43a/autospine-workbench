from copy import deepcopy
import unittest
from test_limb_transverse_repair import fixture
from autospine_workbench.targets.character43.limb_transverse_repair import build
from autospine_workbench.targets.character43.deform_time_aliases import normalize
from autospine_workbench.targets.character43.runtime_storage_reference import stored_document
from m4_boundary_curve_audit import represent


class CurveRepresentationTests(unittest.TestCase):
    def test_storage_representation_converts_all_three_documents_without_mutation(self):
        parent=fixture();parent['animations']['external-motion']=parent['animations'].pop('motion')
        compensation,_=build(parent,'external-motion',['leg'])
        result=deepcopy(compensation)
        keys=result['animations']['external-motion']['attachments']['default']['leg']['leg']['deform']
        keys[-1]['vertices'][0]+=.123456789
        before=deepcopy((parent,compensation,result))
        p,c,r,e=represent(parent,compensation,result,'leg','runtime-storage')
        normalized,_=normalize(compensation,parent,'external-motion','leg')
        self.assertEqual(p,stored_document(parent));self.assertEqual(c,stored_document(normalized))
        self.assertEqual(r,stored_document(result));self.assertEqual((parent,compensation,result),before)
        self.assertFalse(e['selected']);self.assertNotEqual(c,r)

    def test_source_origin_does_not_silently_convert_or_accept_unknown_mode(self):
        parent=fixture()
        p,c,r,e=represent(parent,parent,parent,'leg','source-origin')
        self.assertIs(p,parent);self.assertIs(c,parent);self.assertIs(r,parent);self.assertIsNone(e)
        with self.assertRaisesRegex(ValueError,'representation'):represent(parent,parent,parent,'leg','relax')
