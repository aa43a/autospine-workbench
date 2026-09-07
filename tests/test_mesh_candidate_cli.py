"""Immutable source-bound mesh report entry point, including no-selected-mesh case."""
import unittest
from tests import test_region_binding_cli as fixtures
from autospine_workbench.benchmark.__main__ import parser,_execute
from autospine_workbench.benchmark.mesh_candidate_cli import read_mesh_candidate
from autospine_workbench.resolved_project import canonical_sha256


class MeshCandidateCliTests(unittest.TestCase):
    def test_source_bound_unselected_draft_and_replay(self):
        f=fixtures.RegionBindingCliTests();f.setUp();self.addCleanup(f.doCleanups);f.build()
        base=['--state-root',f.f.state,'build-layer-bindings','--manifest',f.f.root/'manifest.json',
              '--workspace',f.f.root,'--skeleton',f.f.root/'skeleton.json','--html',f.f.root/'v2.html',
              '--draft-output',f.f.root/'draft.json']
        _execute(parser().parse_args(list(map(str,base))))
        args=['--state-root',f.f.state,'build-weighted-mesh','--manifest',f.f.root/'manifest.json',
              '--workspace',f.f.root,'--draft',f.f.root/'draft.json','--html',f.f.root/'mesh.html']
        parsed=parser().parse_args(list(map(str,args)))
        doc=_execute(parsed)[0];self.assertEqual(_execute(parsed)[0],doc)
        self.assertTrue(all(not r['weights'] for r in doc['layers']))
        self.assertTrue(all(r['status']=='blocked' for r in doc['layers']))
        self.assertEqual(read_mesh_candidate(f.f.state,f.f.manifest,canonical_sha256(doc),workspace=f.f.root),doc)
        (f.f.root/'layer-0.png').write_bytes(b'changed')
        with self.assertRaises(ValueError):
            read_mesh_candidate(f.f.state,f.f.manifest,canonical_sha256(doc),workspace=f.f.root)
