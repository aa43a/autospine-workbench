"""Parity and resource-bound checks for the faster joint build path."""
from copy import deepcopy
from hashlib import sha256
import json
import random
import unittest
from unittest.mock import patch

from autospine_workbench.automation.storage_io import canonical_bytes
from autospine_workbench.targets.character43 import affine_pose, numeric_reference
from autospine_workbench.targets.character43.deformation_qa import inspect, inspect_reference
from autospine_workbench.targets.character43.reference_chunk_codec import encode
from autospine_workbench.targets.spine43.continuous_pose import interpolate as linear_interpolate


class JointBuildPerformanceTests(unittest.TestCase):
    def test_binary_lookup_matches_linear_for_reverse_and_random_seeks(self):
        rng = random.Random(370)
        keys = [dict(time=i/60, value=rng.uniform(-90, 90),
                     vertices=[rng.uniform(-10, 10) for _ in range(4)]) for i in range(600)]
        keys[17]['curve'] = 'stepped'
        keys[90]['time'] = keys[89]['time']
        times = [-1, 0, 17/60, 89/60, 90/60, 599/60, 12]
        times += [rng.uniform(-1, 11) for _ in range(100)]
        for sequence in (times, list(reversed(times))):
            for t in sequence:
                for field in ('value', 'vertices'):
                    self.assertEqual(affine_pose.interpolate(keys, t, field),
                                     linear_interpolate(keys, t, field))
        self.assertEqual(affine_pose.interpolate([dict(time=2, value=4)], -1, 'value'), 4)

    def test_long_timeline_lookup_is_bounded_without_stateful_seek_cursor(self):
        reads = []
        class Key(dict):
            def __getitem__(self, name):
                if name == 'time': reads.append(1)
                return super().__getitem__(name)
        keys = [Key(time=i, value=i) for i in range(4097)]
        self.assertEqual(affine_pose.interpolate(keys, 4090.25, 'value'), 4090.25)
        self.assertLess(len(reads), 30)

    def test_compressed_writer_preserves_exact_legacy_chunk_bytes(self):
        ref = dict(skeleton_sha256='a'*64, note='中文', animations={
            name: [dict(time=i/60, vertices={'m': [[i*.5, -0.0]]}) for i in range(n)]
            for name, n in [('long', 260), ('短', 129)]})
        expected = {}; chunks = []
        for name, frames in sorted(ref['animations'].items()):
            for part, start in enumerate(range(0, len(frames), 128)):
                raw = encode(canonical_bytes(frames[start:start+128]))
                digest = sha256(raw).hexdigest(); path = 'numeric-reference/'+digest+'.json'
                expected[path] = raw
                chunks.append(dict(animation=name, part=part, file=path, sha256=digest))
        expected['numeric-reference.json'] = canonical_bytes(dict(
            schema=numeric_reference.COMPRESSED_SCHEMA, skeleton_sha256=ref['skeleton_sha256'], chunks=chunks))
        self.assertEqual(numeric_reference.write({}, ref, compressed=True), expected)
        exact = len(canonical_bytes(ref))
        with patch.object(numeric_reference, 'DECODED_LIMIT', exact):
            self.assertEqual(numeric_reference.write({}, ref, compressed=True), expected)
        with patch.object(numeric_reference, 'DECODED_LIMIT', exact-1):
            with self.assertRaisesRegex(ValueError, 'decoded_limit'):
                numeric_reference.write({}, ref, compressed=True)

    def test_in_memory_qa_keeps_file_validation_and_failure_details(self):
        doc = dict(animations={'move': {}}, skins=[dict(attachments={
            'body': {'body': dict(triangles=[0, 1, 2])}})])
        raw = canonical_bytes(doc); digest = sha256(raw).hexdigest()
        ref = dict(skeleton_sha256=digest, animations={'move': [
            dict(time=0, vertices={'body': [[0, 0], [1, 0], [0, 1]]}),
            dict(time=1, vertices={'body': [[0, 0], [1, 0], [0, -1]]})]})
        files = numeric_reference.write({'skeleton.json': raw}, ref, compressed=True)
        report = inspect_reference(doc, ref, digest)
        self.assertEqual(report, inspect(files))
        self.assertFalse(report['passed'])
        self.assertEqual(report['records'][0]['first_failure']['time'], 1)
        with self.assertRaisesRegex(ValueError, 'source_mismatch'):
            inspect_reference(doc, ref, '0'*64)
        broken = deepcopy(ref); broken['animations']['move'][1]['vertices']['body'][0][0] = float('inf')
        with self.assertRaisesRegex(ValueError, 'nonfinite'):
            inspect_reference(doc, broken, digest)
        index = json.loads(files['numeric-reference.json'])
        files[index['chunks'][0]['file']] += b' '
        with self.assertRaisesRegex(ValueError, 'chunk_identity'):
            inspect(files)
