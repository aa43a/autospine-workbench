from copy import deepcopy
import json
import unittest
from unittest.mock import patch
from test_torso_projection import observations
from test_torso_warp_depth_plane import WarpedPlaneTests
from autospine_workbench.targets.character43.torso_projection_source import reference_shapes
from autospine_workbench.targets.character43.torso_projection_candidate import build
from m4_torso_reference_reader import load


class Folder:
    def __init__(self,value):self.value=value
    def __truediv__(self,other):return self
    def read_bytes(self):return json.dumps(self.value).encode()


class TorsoReferenceReaderTests(unittest.TestCase):
    def setUp(self):
        fixture=WarpedPlaneTests();fixture.setUp()
        self.parent=deepcopy(fixture.doc);self.parent['animations']['move'].pop('attachments')
        self.parent['animations']['external-motion']=self.parent['animations'].pop('move')
        self.frames=[observations(45)]*2;self.reference=[observations(0)]*2
        source=reference_shapes(self.frames,[0,1],self.reference[0])
        self.document,self.receipt=build(self.parent,'external-motion',source)
        self.receipt.update(source_candidate_sha256='parent',source_identity={'clip':'exact'},yaw_degrees=45,
                            reference_source_yaw=0,candidate_bundle_sha256='candidate')

    def read(self):
        with patch('m4_torso_reference_reader.AnimatedStore') as store,patch('m4_torso_reference_reader.anchors',
                side_effect=[(self.frames,[0,1000000]),(self.reference,[0,1000000])]):
            store.return_value.read.return_value={'skeleton.json':json.dumps(self.document).encode()}
            return load(Folder(self.receipt),'parent',self.parent,object(),{'clip':'exact'},45)

    def test_reproduced_candidate_can_supply_baked_plane(self):
        files,doc,digest,plane=self.read()
        self.assertEqual(digest,'candidate')
        self.assertIs(plane.document,doc)
        self.assertEqual(doc,self.document)

    def test_view_and_parent_mismatch_fail(self):
        for field,value in [('yaw_degrees',0),('source_candidate_sha256','other')]:
            original=self.receipt[field];self.receipt[field]=value
            with self.assertRaisesRegex(ValueError,'source_mismatch'):self.read()
            self.receipt[field]=original

    def test_deform_tampering_fails_reproduction(self):
        tracks=self.document['animations']['external-motion']['attachments']['default']
        slot=next(iter(tracks));tracks[slot][slot]['deform'][0]['vertices'][0]+=.25
        with self.assertRaisesRegex(ValueError,'bake_mismatch'):self.read()
