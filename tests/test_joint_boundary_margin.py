from copy import deepcopy
from hashlib import sha256
import unittest
from test_limb_transverse_repair import fixture
from autospine_workbench.automation.storage_io import canonical_bytes
from autospine_workbench.targets.character43.joint_boundary_margin import measure
from autospine_workbench.targets.character43.interpolation_area_margin import LIMIT


def case(mixed):
    parent=fixture()
    parent['animations']['motion']['bones']['thigh_l']['scale'][1].update(x=1,y=1)
    if mixed:
        parent['skins'][0]['attachments']['leg']['leg']['vertices']=[v for x,y in ((0,0),(0,10),(10,0))
            for v in (2,1,x,y,.5,2,x,y,.5)]
    candidate=deepcopy(parent)
    offsets=[0.,0.,0.,0.,-8.,0.] if not mixed else [0.,0.]*4+[-8.,0.]*2
    candidate['animations']['motion']['attachments']={'default':{'leg':{'leg':{'deform':[
        {'time':0.,'vertices':offsets},{'time':1.,'vertices':offsets}]}}}}
    report=dict(slot='leg',skeleton_sha256=sha256(canonical_bytes(candidate)).hexdigest(),
        failures=[dict(time=.5,at_key=False,triangles=[0])])
    return parent,candidate,report


class BoundaryMarginTests(unittest.TestCase):
    def test_measures_both_endpoints_with_cap_without_mutating_source(self):
        parent,candidate,report=case(True);before=deepcopy((parent,candidate,report))
        margins,evidence=measure(parent,candidate,report,'motion','leg')
        self.assertEqual(margins,{0.:[LIMIT],1.:[LIMIT]})
        self.assertEqual(evidence['capped_observations'],1)
        self.assertEqual(evidence['fixed_unresolved'],[])
        self.assertFalse(evidence['selected']);self.assertEqual((parent,candidate,report),before)

    def test_fixed_failure_is_preserved_not_given_unachievable_margin(self):
        margins,evidence=measure(*case(False),'motion','leg')
        self.assertEqual(margins,{})
        self.assertEqual(len(evidence['fixed_unresolved']),1)

    def test_identity_mismatch_rejected(self):
        parent,candidate,report=case(True);candidate['bones'][0]['x']=7
        with self.assertRaisesRegex(ValueError,'identity'):measure(parent,candidate,report,'motion','leg')
