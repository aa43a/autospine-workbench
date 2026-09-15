from hashlib import sha256
import json
from types import SimpleNamespace
import unittest
from tests.test_character_region_replay import RegionReplayTests
from autospine_workbench.automation.character_final_regions import binding_edit_decisions
from autospine_workbench.automation.storage_io import canonical_bytes
from autospine_workbench.resolved_project import canonical_sha256
from autospine_workbench.targets.character43.region_exclusion import apply


class FinalBindingEditReplayTests(unittest.TestCase):
    setUp=RegionReplayTests.setUp

    def test_existing_exclusion_remains_traceable_across_other_binding_edits(self):
        store=SimpleNamespace(read=self.store.read,
            publish=lambda f:canonical_sha256({n:sha256(b).hexdigest() for n,b in f.items()}))
        decisions=binding_edit_decisions(store,self.current,[self.decision])
        proof=decisions[0]['scope_replay']
        self.assertEqual(proof['original_decision'],self.decision)
        self.assertFalse(proof['new_human_confirmation'])
        output=apply(self.current,decisions[0])
        self.assertEqual(json.loads(output['skeleton.json'])['slots'],[{'name':'leg'}])
        self.assertEqual(output['images/rest.png'],self.original['images/rest.png'])

    def test_source_or_excluded_region_changes_still_block(self):
        for mutate in (lambda m:m['source_addresses'].update(resolved_project_sha256='c'*64),
                       lambda m:m['layers'][0].update(state='weighted_candidate')):
            changed=dict(self.current);manifest=json.loads(changed['character-manifest.json'])
            mutate(manifest);changed['character-manifest.json']=canonical_bytes(manifest)
            with self.assertRaises(ValueError):binding_edit_decisions(self.store,changed,[self.decision])
        with self.assertRaises(ValueError):
            binding_edit_decisions(self.store,{**self.current,'images/rest.png':b'changed'},[self.decision])
