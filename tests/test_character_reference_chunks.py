import json
import unittest
from autospine_workbench.targets.character43.numeric_reference import read, write
from autospine_workbench.automation.storage_io import canonical_bytes


class ReferenceChunksTests(unittest.TestCase):
    def reference(self):
        return dict(skeleton_sha256='a'*64, animations={'walk': [dict(time=i/128,
            vertices={'leg': [[.123456789012345, i]]}) for i in range(300)]})

    def test_lossless_roundtrip_and_legacy_bytes(self):
        reference=self.reference(); files=write({},reference,limit=1)
        self.assertEqual(read(files),reference)
        self.assertEqual(len(json.loads(files['numeric-reference.json'])['chunks']),3)
        self.assertEqual(write({},reference)['numeric-reference.json'],canonical_bytes(reference))
        self.assertEqual(write(files,reference),write({},reference))

    def test_missing_tampered_and_reordered_chunks_fail(self):
        files=write({},self.reference(),limit=1)
        index=json.loads(files['numeric-reference.json']); path=index['chunks'][0]['file']
        with self.assertRaises(ValueError):read({**files,path:b'[]'})
        missing=dict(files);del missing[path]
        with self.assertRaises(KeyError):read(missing)
        index['chunks'].reverse()
        with self.assertRaises(ValueError):read({**files,'numeric-reference.json':canonical_bytes(index)})
