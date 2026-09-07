"""Synthetic annotation requests test explicit consent and benchmark isolation."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from autospine_workbench.benchmark.joint_draft import build_joint_draft
from autospine_workbench.benchmark.joint_reference import (
    build_joint_reference, validate_joint_reference, validate_joint_reference_request,
)
from autospine_workbench.resolved_project import canonical_sha256
from tests.test_benchmark_joint_draft import candidate


def fixture():
    source = candidate()
    draft = build_joint_draft(source)
    draft['records'][0].update(status='observed', position=[100, 50], notes='synthetic test annotation')
    draft['records'][1].update(status='unobservable', notes='synthetic occlusion')
    request = {'schema': 'autospine.benchmark-joint-reference-request/v1', 'authority': 'none',
               'candidate_sha256': canonical_sha256(source), 'draft_sha256': canonical_sha256(draft),
               'reviewer': 'test-only-reviewer', 'decision': 'accept', 'independent_annotation': True}
    return source, draft, request


class JointReferenceTests(unittest.TestCase):
    def test_records_preserved_pure_and_explicit_benchmark_scope(self):
        args = fixture()
        before = deepcopy(args)
        document = build_joint_reference(*args)
        self.assertEqual(validate_joint_reference(*args, document), document)
        self.assertEqual(args, before)
        self.assertEqual(document['records'], args[1]['records'])
        self.assertEqual(document['authority'], 'none')
        self.assertEqual(document['scope'], 'benchmark_only')
        document['records'][0]['position'][0] = 9
        self.assertEqual(args[1]['records'][0]['position'][0], 100)

    def test_blank_draft_or_unobservable_only_cannot_be_reference(self):
        source, draft, request = fixture()
        draft['records'][0].update(status='unmarked', position=None)
        request['draft_sha256'] = canonical_sha256(draft)
        with self.assertRaisesRegex(ValueError, 'observation_required'):
            build_joint_reference(source, draft, request)

    def test_request_identity_authority_independence_strict(self):
        for key, value in (('candidate_sha256', '0'*64), ('draft_sha256', '0'*64),
                           ('authority', 'human'), ('independent_annotation', 1),
                           ('independent_annotation', False), ('decision', 'reject'), ('extra', None)):
            source, draft, request = fixture()
            request[key] = value
            with self.assertRaisesRegex(ValueError, 'request_invalid'):
                validate_joint_reference_request(source, draft, request)

    def test_reviewer_no_silent_trim_or_control_characters(self):
        for value in ('', '   ', ' reviewer', 'reviewer ', 'a'*121, 'reviewer\nname', 'reviewer\u200bname', 7):
            source, draft, request = fixture()
            request['reviewer'] = value
            with self.assertRaisesRegex(ValueError, 'reviewer_invalid'):
                build_joint_reference(source, draft, request)

    def test_bad_draft_numeric_and_reference_tamper(self):
        source, draft, request = fixture()
        draft['records'][0]['position'] = [10**1000, 1]
        request['draft_sha256'] = canonical_sha256(draft)
        with self.assertRaises(ValueError):
            build_joint_reference(source, draft, request)
        for mutate in (lambda d: d.update(reviewer='changed'), lambda d: d.update(scope='production'),
                       lambda d: d['records'][0].update(position=[5, 5]), lambda d: d.update(extra=True)):
            args = fixture()
            document = build_joint_reference(*args)
            mutate(document)
            with self.assertRaisesRegex(ValueError, 'mismatch'):
                validate_joint_reference(*args, document)

    def test_both_schemas(self):
        try:
            from jsonschema import Draft202012Validator
        except ImportError:
            self.skipTest('jsonschema unavailable')
        args = fixture()
        for name, document in (('benchmark-joint-reference-request-v1', args[2]),
                               ('benchmark-joint-reference-v1', build_joint_reference(*args))):
            schema = json.loads((Path(__file__).resolve().parents[1] / 'schemas' / f'{name}.schema.json').read_text('utf-8'))
            Draft202012Validator.check_schema(schema)
            Draft202012Validator(schema).validate(document)


if __name__ == '__main__':
    unittest.main()
