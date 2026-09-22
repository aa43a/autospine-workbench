from copy import deepcopy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from autospine_workbench.automation.character_ordinary import route_source
from autospine_workbench.automation.storage_io import canonical_bytes
from autospine_workbench.targets.character43.ordinary_package import build_package
from test_character_sleeve_composition import fixture


class OrdinaryCharacterTests(unittest.TestCase):
    def test_explicit_current_route_only_and_never_skip_existing_repair(self):
        with TemporaryDirectory() as root:
            projects=SimpleNamespace(state_root=Path(root),get_project=lambda _:dict(resolved=dict(sha256='a'*64,layers=[])));sleeves=Mock()
            sleeves.has_job.return_value=False
            with self.assertRaisesRegex(RuntimeError,'confirmation_required'):route_source(projects,sleeves,'sample','a'*64)
            folder=Path(root)/'project-route-v1/sample';folder.mkdir(parents=True)
            value=dict(schema='autospine.project-route-choice/v1',project_id='sample',source_sha256='a'*64,
                       choice='ordinary',revision=1,authority='none')
            (folder/'revision-000000000001.json').write_bytes(canonical_bytes(value))
            self.assertEqual(len(route_source(projects,sleeves,'sample','a'*64)),64)
            with self.assertRaisesRegex(RuntimeError,'confirmation_required'):route_source(projects,sleeves,'sample','b'*64)
            sleeves.has_job.return_value=True
            with self.assertRaisesRegex(RuntimeError,'resolution_required'):route_source(projects,sleeves,'sample','a'*64)

    def test_package_keeps_original_scene_and_all_unbound_statuses(self):
        doc,*_=fixture();doc['animations']={'limb-flex-15':{'bones':{'root':{'rotate':[
            {'time':0,'value':0},{'time':1,'value':15},{'time':2,'value':0}]}}}}
        base={'skeleton.json':canonical_bytes(doc),'motion.json':canonical_bytes({'clip':'limb-flex-15','duration':2})}
        coverage={'layers':[{'layer_id':'arm','state':'static_reference','regions':[{'region_id':'arm','state':'static_reference'}]}]}
        before=deepcopy(base);files=build_package(base,coverage,{'route_choice_sha256':'a'*64})
        self.assertEqual(base,before);self.assertEqual(files['skeleton.json'],before['skeleton.json'])
        manifest=json.loads(files['character-manifest.json']);self.assertFalse(manifest['full_character_animation'])
        self.assertEqual(manifest['layers'],coverage['layers'])
        frames=json.loads(files['numeric-reference.json'])['animations']['limb-flex-15']
        self.assertEqual(len(frames),129);self.assertNotEqual(frames[0]['vertices'],frames[64]['vertices'])
        coverage['layers']=[]
        with self.assertRaisesRegex(ValueError,'coverage_inventory'):build_package(base,coverage,{})
