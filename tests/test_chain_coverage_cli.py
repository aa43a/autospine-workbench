"""Source replay and draft provenance at the coverage CLI boundary."""
import json
import unittest

from tests import test_region_binding_cli as fixtures
from autospine_workbench.benchmark.__main__ import parser, _execute
from autospine_workbench.benchmark.chain_coverage_cli import read_chain_coverage
from autospine_workbench.resolved_project import canonical_sha256


class ChainCoverageCliTests(unittest.TestCase):
    def test_exact_replay_and_changed_source(self):
        f=fixtures.RegionBindingCliTests();f.setUp();self.addCleanup(f.doCleanups)
        f.build()
        base=['--state-root',f.f.state,'build-layer-bindings','--manifest',f.f.root/'manifest.json',
              '--workspace',f.f.root,'--skeleton',f.f.root/'skeleton.json','--html',f.f.root/'layer-v2.html',
              '--draft-output',f.f.root/'draft-v2.json']
        bindings=_execute(parser().parse_args(list(map(str,base))))[0]
        path=f.f.root/'bindings.json';path.write_text(json.dumps(bindings),encoding='utf-8')
        args=['--state-root',f.f.state,'analyze-chain-coverage','--manifest',f.f.root/'manifest.json',
              '--workspace',f.f.root,'--bindings',path,'--draft',f.f.root/'draft-v2.json','--html',f.f.root/'coverage.html']
        parsed=parser().parse_args(list(map(str,args)))
        doc=_execute(parsed)[0]
        self.assertEqual(_execute(parsed)[0],doc)
        self.assertEqual(read_chain_coverage(f.f.state,f.f.manifest,canonical_sha256(doc),workspace=f.f.root),doc)
        self.assertNotIn(str(f.f.root),(f.f.root/'coverage.html').read_text('utf-8'))
        (f.f.root/'layer-0.png').write_bytes(b'changed')
        with self.assertRaises(ValueError):
            read_chain_coverage(f.f.state,f.f.manifest,canonical_sha256(doc),workspace=f.f.root)
