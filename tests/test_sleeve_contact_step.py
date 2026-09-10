import tempfile
import unittest
from pathlib import Path
from copy import deepcopy
from autospine_workbench.automation.sleeve_contact_step import summaries
from autospine_workbench.automation.storage_io import publish_document
from autospine_workbench.resolved_project import canonical_sha256
from autospine_workbench.asset.planning.sleeve_motion_envelope import MOTIONS


class ContactStepTests(unittest.TestCase):
    def fixture(self):
        export=dict(records=[dict(layer_id='sleeve',component_id='part',status='candidate_exported',files={'image':'a'*64})])
        row=dict(layer_id='sleeve',component_id='part',asset_sha256={'image':'a'*64},authority='none',production_authorized=False,
            framebuffer_status='not_evaluated',tested_samples=1799,failed_samples=0,unobservable_interfaces=1,
            interfaces=[dict(samples=[1]),dict(samples=[])],tracks=[dict(animation=name,frames=257,failed_samples=0) for name,_ in MOTIONS],status='needs_review')
        report=dict(schema='autospine.sleeve-contact-coverage/v1',project_id='fixture',source_sha256=canonical_sha256(export),
            authority='none',production_authorized=False,framebuffer_status='not_evaluated',records=[row])
        return export,report

    def read(self,export,report):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);path=root/'contacts/fixture';path.mkdir(parents=True)
            publish_document(path/(canonical_sha256(report)+'.json'),report,staging=root/'.staging')
            return summaries(root,'fixture',export)

    def test_unobservable_is_preserved_and_not_promoted_to_gpu(self):
        export,report=self.fixture();row=self.read(export,report)['sleeve','part']
        self.assertEqual(row['status'],'needs_review');self.assertEqual(row['unobservable_interfaces'],1)
        self.assertEqual(row['framebuffer_status'],'not_evaluated')

    def test_forged_pass_counts_source_or_inventory_rejected(self):
        export,report=self.fixture()
        for field,value in [('status','cpu_coverage_passed'),('tested_samples',4),('framebuffer_status','passed')]:
            changed=deepcopy(report);changed['records'][0][field]=value
            with self.assertRaises(ValueError):self.read(export,changed)
        changed=deepcopy(report);changed['source_sha256']='0'*64
        with self.assertRaises(ValueError):self.read(export,changed)
        changed=deepcopy(report);changed['records']=[]
        with self.assertRaises(ValueError):self.read(export,changed)
        changed=deepcopy(report);changed['records'][0]['tracks'][0]['frames']=1
        with self.assertRaisesRegex(ValueError,'motion_inventory'):self.read(export,changed)
