from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import json
import unittest
from test_character_motion_composition import package
from autospine_workbench.automation.character_motion_catalog import register, choices, append_selected, read
from autospine_workbench.automation.storage_io import canonical_bytes
from hashlib import sha256


class MotionCatalogTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.sources = dict(resolved_project_sha256='c'*64, input_identity_sha256='d'*64)
        base = package('idle'); manifest = json.loads(base['character-manifest.json'])
        manifest['source_addresses'] = self.sources; base['character-manifest.json'] = canonical_bytes(manifest)
        self.packages = {'a'*64: base, 'b'*64: package('walk')}
        def publish(files):
            digest = sha256(canonical_bytes({n: sha256(v).hexdigest() for n, v in files.items()})).hexdigest()
            self.packages[digest] = files; return digest
        self.manager = SimpleNamespace(root=Path(self.temp.name), application=SimpleNamespace(
            store=SimpleNamespace(read=self.packages.__getitem__, publish=publish)))

    def test_registered_choice_is_idempotent_and_merges_only_exact_base(self):
        choice = register(self.manager, 'project', 'a'*64, 'b'*64, self.sources)
        self.assertEqual(register(self.manager, 'project', 'a'*64, 'b'*64, self.sources), choice)
        self.assertTrue(choices(self.manager, 'project', self.sources)[0]['available'])
        request = dict(project_id='project', expected_resolved_sha256='c'*64, expected_input_sha256='d'*64,
                       region_decisions_sha256=None, motion_choice_id=choice)
        result = append_selected(self.manager, request, dict(artifact_sha256='a'*64))
        self.assertEqual(result['manifest']['animations'], ['idle', 'walk'])
        with self.assertRaisesRegex(RuntimeError, 'source_changed'):
            append_selected(self.manager, request, dict(artifact_sha256='e'*64))

    def test_changed_input_is_unavailable_and_cannot_be_used(self):
        choice = register(self.manager, 'project', 'a'*64, 'b'*64, self.sources)
        changed = {**self.sources, 'input_identity_sha256': 'e'*64}
        self.assertFalse(choices(self.manager, 'project', changed)[0]['available'])
        request = dict(project_id='project', expected_resolved_sha256='c'*64, expected_input_sha256='e'*64,
                       region_decisions_sha256=None, motion_choice_id=choice)
        with self.assertRaisesRegex(RuntimeError, 'source_changed'):
            append_selected(self.manager, request, {})

    def test_catalog_identity_tampering_is_rejected(self):
        choice = register(self.manager, 'project', 'a'*64, 'b'*64, self.sources)
        path = self.manager.root/'motion-catalog/project'/(choice+'.json')
        doc = json.loads(path.read_bytes()); doc['animations'] = ['invented']; path.write_bytes(canonical_bytes(doc))
        with self.assertRaisesRegex(RuntimeError, 'catalog_invalid'):
            read(self.manager, 'project', choice)

    def test_post_exclusion_base_is_not_an_available_upstream_motion(self):
        choice=register(self.manager,'project','a'*64,'b'*64,self.sources)
        # Simulate a historically registered post-exclusion package without changing its catalog bytes.
        self.packages['a'*64]['final-region-exclusion.json']=b'{}'
        value=choices(self.manager,'project',self.sources)[0]
        self.assertFalse(value['available'])
        self.assertEqual(value['reason_code'],'character_motion_base_stage_unsupported')
        with self.assertRaisesRegex(RuntimeError,'base_stage_unsupported'):
            register(self.manager,'project','a'*64,'b'*64,self.sources)
        with self.assertRaisesRegex(RuntimeError,'base_stage_unsupported'):
            append_selected(self.manager,dict(project_id='project',motion_choice_id=choice),{})
