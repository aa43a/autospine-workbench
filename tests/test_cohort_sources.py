"""Byte verification rejects replaced PSDs, stale audits, and escaped paths."""
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from autospine_workbench.automation.cohort_sources import verify
from autospine_workbench.automation.cohort_intake import assess
import test_cohort_intake


class SourceTests(unittest.TestCase):
    def test_local_audit_and_psd_must_both_match(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            psd = root / 'a.psd'; psd.write_bytes(b'example source bytes')
            digest = sha256(psd.read_bytes()).hexdigest()
            audit = root / 'tmp/psd_audit/results/a/audit.json'
            audit.parent.mkdir(parents=True)
            audit.write_text(json.dumps(dict(sha256=digest)))
            manifest = dict(characters=[dict(dataset_split='visible', psd_candidates=[
                dict(source=dict(path='a.psd', sha256=digest))])])
            documents = dict(a=dict(id='a', source=dict(sha256=digest, audit_id='a',
                audit_sha256=sha256(audit.read_bytes()).hexdigest())))
            result = verify(root, manifest, documents)
            self.assertEqual(result['projects']['a']['status'], 'verified')
            psd.write_bytes(b'replaced')
            self.assertEqual(verify(root, manifest, documents)['projects']['a']['status'], 'psd_identity_unverified')
            psd.write_bytes(b'example source bytes')
            audit.write_text('{}')
            self.assertEqual(verify(root, manifest, documents)['projects']['a']['status'], 'audit_identity_changed')
            documents['a']['source']['audit_id'] = '../escape'
            self.assertEqual(verify(root, manifest, documents)['projects']['a']['status'], 'audit_source_unverified')

    def test_verified_audit_can_match_without_a_matching_name(self):
        fixture = test_cohort_intake.IntakeTests(); fixture.setUp()
        fixture.catalog['projects'] = [fixture.project('renamed', dict(kind='audit'))]
        checks = dict(schema='autospine.cohort-source-check/v1', authority='none', projects={
            'renamed': dict(status='verified', source_sha256=f'{0:064x}')})
        result = assess(fixture.manifest, fixture.catalog, checks)
        self.assertEqual(result['schema'], 'autospine.cohort-intake/v2')
        self.assertEqual(result['exact_active_single_source'], 1)
        checks['projects']['renamed']['status'] = 'audit_identity_changed'
        self.assertEqual(assess(fixture.manifest, fixture.catalog, checks)['exact_active_single_source'], 0)
        checks['files'] = {f'{0:064x}': dict(status='source_bytes_changed')}
        self.assertEqual(assess(fixture.manifest, fixture.catalog, checks)['characters'][0]['reason_code'],
                         'frozen_psd_bytes_changed')
