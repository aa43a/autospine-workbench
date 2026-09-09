"""Cohort aggregation must not turn diagnostic previews into character acceptance."""
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from autospine_workbench.automation.animated_cohort_report import build_report, publish_report, read_report, validate_report
from autospine_workbench.automation.animated_cohort_cli import LocalWorkbench, build_case


def row(clip='limb-flex-15'):
    return dict(project_id='fixture', clip=clip, expected_resolved_sha256='a'*64,
                status='needs_review', preview_available=True, run_id='run-'+'b'*64,
                bundle_sha256='c'*64, source_addresses={'resolved_project_sha256':'a'*64},
                summary={'mesh_layers':2, 'context_layers':4, 'rejected_mesh_layers':[]}, reason_code=None,
                review_items=[{'layer_id':'sleeve', 'reason_code':'mesh_review_required'}])


class AnimatedCohortTests(unittest.TestCase):
    def test_cross_clip_dedup_is_per_project_layer_not_preview_count(self):
        value = build_report([row(), row('limb-flex-30')])
        self.assertEqual(value['summary']['previews'], 2)
        self.assertEqual(value['summary']['reasons'][0]['affected_project_layer_pairs'], 1)
        self.assertFalse(value['production_authorized'])
        self.assertEqual(value['runtime_status'], 'not_evaluated')
        with self.assertRaisesRegex(ValueError, 'duplicate'):
            build_report([row(), row()])

    def test_addressed_report_roundtrip_and_tamper_rejection(self):
        with TemporaryDirectory() as temp:
            value=build_report([row()]); digest, folder=publish_report(temp,value)
            self.assertEqual(read_report(folder/'report.json'), value)
            self.assertEqual(publish_report(temp,value)[0],digest)
            forged=deepcopy(value); forged['production_authorized']=True
            with self.assertRaisesRegex(ValueError,'report_invalid'):
                validate_report(forged)
            changed=row(); changed['source_addresses']['resolved_project_sha256']='d'*64
            with self.assertRaisesRegex(ValueError,'source_mismatch'):
                build_report([changed])

    def test_only_local_service_and_no_wrong_project_or_source_receipt(self):
        for url in ['https://example.com', 'http://localhost@evil.test', 'http://127.0.0.1/a']:
            with self.assertRaises(ValueError): LocalWorkbench(url)
        class Client:
            def request(self, *args):
                return {'job_id':'job-'+'a'*32,'project_id':'other','authority':'none','status':'needs_review'}
        with self.assertRaisesRegex(ValueError,'job_mismatch'):
            build_case(Client(),'fixture','limb-flex-15','a'*64)

    def test_unavailable_case_is_not_counted_as_preview(self):
        case=row(); case.update(status='blocked',preview_available=False,reason_code='cohort_source_changed')
        report=build_report([case])
        self.assertEqual(report['summary']['previews'],0)
        self.assertEqual(report['summary']['unavailable'],1)

    def test_schema_accepts_report_and_rejects_runtime_approval_claim(self):
        import json
        import jsonschema
        schema=json.loads((Path(__file__).resolve().parents[1]/'schemas/animated-cohort-v1.schema.json').read_bytes())
        jsonschema.Draft202012Validator.check_schema(schema)
        value=build_report([row()]); jsonschema.validate(value,schema)
        value['runtime_status']='passed'
        with self.assertRaises(jsonschema.ValidationError): jsonschema.validate(value,schema)
