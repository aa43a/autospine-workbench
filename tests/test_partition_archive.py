"""Portable archive identity, semantic reader replay, and schema validation."""
import hashlib
from io import BytesIO
import json
from pathlib import Path
import unittest
from unittest.mock import patch
from zipfile import ZipFile

from tests.test_partition_pixels import fixture
from autospine_workbench.benchmark import partition_cli
from autospine_workbench.resolved_project import canonical_sha256


class PartitionArchiveTests(unittest.TestCase):
    def test_archive_source_pixels_schema_and_reader(self):
        raw,source,proposal,_=fixture();source['layer_id']='layer-001';source['name']='footwear'
        structure={'source_draft_sha256':'1'*64,'layers':[dict(proposal,layer_id='layer-001',proposal={'kind':'component_partition'})]}
        candidate={'layers':[source]}
        args=(candidate,None,None,None,None,b'',{'layer-001':raw})
        with patch.object(partition_cli,'read_structure',return_value=structure),patch.object(partition_cli,'inputs',return_value=args):
            report,data,_=partition_cli.build(None,{},'2'*64,None)
            self.assertEqual(hashlib.sha256(data).hexdigest(),report['zip_sha256'])
            with ZipFile(BytesIO(data)) as zipped:
                self.assertEqual(zipped.read('layer-001/source.png'),raw)
                for name,digest in report['files'].items():
                    self.assertEqual(hashlib.sha256(zipped.read(name)).hexdigest(),digest)
            self.assertEqual(partition_cli.build(None,{},'2'*64,None)[1],data)
            with patch.object(partition_cli,'read_report',return_value=report):
                self.assertEqual(partition_cli.read_partitions(None,{'dataset_id':'test'},canonical_sha256(report),workspace=None),report)
                report['layers'][0]['qa']['visible_pixel_counts']['1']+=1
                with self.assertRaisesRegex(ValueError,'report_mismatch'):
                    partition_cli.read_partitions(None,{'dataset_id':'test'},canonical_sha256(report),workspace=None)
            report,_,_=partition_cli.build(None,{},'2'*64,None)
        try:
            from jsonschema import Draft202012Validator
        except ImportError:
            self.skipTest('jsonschema unavailable')
        schema=Path(__file__).resolve().parents[1]/'schemas/layer-partitions-v1.schema.json'
        Draft202012Validator(json.loads(schema.read_text('utf-8'))).validate(report)
