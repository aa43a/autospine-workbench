import json
import base64
from pathlib import Path
import unittest

from autospine_workbench.automation.storage_io import canonical_bytes
from autospine_workbench.targets.character43.numeric_reference import read, write, COMPRESSED_SCHEMA
from autospine_workbench.targets.character43.reference_chunk_codec import decode, encode, LIMIT


class ReferenceCodecTests(unittest.TestCase):
    def test_lossless_deterministic_roundtrip_and_legacy_formats_remain_readable(self):
        reference=dict(skeleton_sha256='a'*64,animations={'motion':[
            dict(time=i/3712,vertices={'body':[[1e-12,-.0],[123.123456789123,-5.7890012345]]*40})
            for i in range(260)]})
        packed=write({},reference,compressed=True)
        self.assertEqual(packed,write({},reference,compressed=True))
        self.assertEqual(canonical_bytes(read(packed)),canonical_bytes(reference))
        self.assertEqual(json.loads(packed['numeric-reference.json'])['schema'],COMPRESSED_SCHEMA)
        self.assertLess(sum(map(len,packed.values())),len(canonical_bytes(reference))/4)
        for limit in (1,64<<20):
            self.assertEqual(read(write({},reference,limit=limit)),reference)
        stale=dict(packed,**{'numeric-reference/stale.json':b'old'})
        self.assertNotIn('numeric-reference/stale.json',write(stale,reference,compressed=True))

    def test_tampering_size_lies_and_excessive_expansion_are_rejected(self):
        raw=canonical_bytes([{'data':'x'*10000}]);wrapped=json.loads(encode(raw))
        for key,value in [('codec','other'),('bytes',True),('bytes',LIMIT+1),('bytes',1),('sha256','0'*64),('data','%%%')]:
            bad=dict(wrapped);bad[key]=value
            with self.assertRaisesRegex(ValueError,'compressed_chunk_invalid'):
                decode(canonical_bytes(bad))
        files=write({},dict(skeleton_sha256='a'*64,animations={'motion':[dict(time=0)]}),compressed=True)
        manifest=json.loads(files['numeric-reference.json']);name=manifest['chunks'][0]['file']
        files[name]=files[name]+b' '
        with self.assertRaisesRegex(ValueError,'chunk_identity'):read(files)

    def test_corrupt_deflate_is_reported_as_invalid_chunk(self):
        wrapped=json.loads(encode(b'[1]'))
        compressed=bytearray(base64.b64decode(wrapped['data']))
        compressed[10]=7  # Reserved DEFLATE block type, inside a valid gzip header.
        wrapped['data']=base64.b64encode(compressed).decode('ascii')
        with self.assertRaisesRegex(ValueError,'compressed_chunk_invalid'):
            decode(canonical_bytes(wrapped))

    def test_published_contracts_match_actual_chunks(self):
        from jsonschema import Draft202012Validator, ValidationError
        root=Path(__file__).resolve().parents[1]/'schemas'
        files=write({},dict(skeleton_sha256='a'*64,animations={'motion':[dict(time=0)]}),compressed=True)
        index=json.loads(files['numeric-reference.json'])
        payload=json.loads(files[index['chunks'][0]['file']])
        for name,value in [('character-reference-chunks-v2',index),('reference-chunk-envelope-v1',payload)]:
            schema=json.loads((root/(name+'.schema.json')).read_bytes())
            Draft202012Validator.check_schema(schema);validator=Draft202012Validator(schema)
            validator.validate(value)
            with self.assertRaises(ValidationError):validator.validate(dict(value,extra=True))
