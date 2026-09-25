from copy import deepcopy
from hashlib import sha256
from types import SimpleNamespace
import unittest

from autospine_workbench.automation.storage_io import canonical_bytes
from m4_isolated_contact_audit import audit
from test_final_motion_contact import fixture


class IsolatedContactTests(unittest.TestCase):
    def setUp(self):
        doc, motion = fixture()
        doc['animations']['external-motion'] = doc['animations'].pop('a')
        doc['bones'] += [dict(name=n, parent='root', x=10, y=0, rotation=0)
                         for n in ('calf_l', 'calf_r', 'foot_r')]
        raw = canonical_bytes(doc)
        identity = dict(clip_sha256='b'*64, bundle_sha256='c'*64)
        self.bundle = SimpleNamespace(**identity, motion=motion, source_kind='bvh')
        self.files = {'skeleton.json': raw,
                      'motion-torso-reference.json': canonical_bytes(dict(source_identity=identity)),
                      'numeric-reference.json': canonical_bytes(dict(
                          skeleton_sha256=sha256(raw).hexdigest(), animations={'external-motion': [
                              dict(time=t, vertices={}) for t in (0, .5, 1)]}))}
        self.runtime = dict(bundle_sha256='a'*64, passed=True, results=[
            dict(animation='external-motion', time=t) for t in (0, .5, 1)])

    def test_detects_midpoint_drift_without_mutating_candidate(self):
        before = deepcopy(self.files)
        result = audit(self.files, 'a'*64, self.runtime, self.bundle)
        self.assertEqual(result['status'], 'needs_changes')
        self.assertEqual(result['after']['max_drift_px'], 20)
        self.assertFalse(result['correction_applied'])
        self.assertEqual(self.files, before)

    def test_source_and_runtime_identity_required(self):
        self.bundle.clip_sha256 = 'd'*64
        with self.assertRaisesRegex(ValueError, 'source_mismatch'):
            audit(self.files, 'a'*64, self.runtime, self.bundle)
        self.bundle.clip_sha256 = 'b'*64
        with self.assertRaisesRegex(ValueError, 'runtime_mismatch'):
            audit(self.files, 'd'*64, self.runtime, self.bundle)

    def test_partial_runtime_and_cropped_motion_rejected(self):
        original = deepcopy(self.runtime)
        self.runtime['results'].pop(1)
        with self.assertRaisesRegex(ValueError, 'times_mismatch'):
            audit(self.files, 'a'*64, self.runtime, self.bundle)
        self.bundle.motion['duration_ticks'] = 200
        with self.assertRaisesRegex(ValueError, 'times_invalid'):
            audit(self.files, 'a'*64, original, self.bundle)
