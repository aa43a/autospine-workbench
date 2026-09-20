import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from autospine_workbench.automation.motion_intake_worker import compile_source
from autospine_workbench.automation.motion_target_worker import execute
from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.automation.storage_io import canonical_bytes,publish_document,read_document
from autospine_workbench.targets.character43.oblique_motion import PROFILE
from autospine_workbench.targets.character43.oblique_target import validate
from autospine_workbench.targets.character43.motion_depth import _source
from test_motion_target_intake import inputs
from test_mixamo_map import source


class ObliqueTargetTests(unittest.TestCase):
    def test_depth_uses_same_yaw_as_motion(self):
        point=SimpleNamespace(depth=5,screen_xy=(3,4))
        projected=SimpleNamespace(frames=[SimpleNamespace(tick=0,joints=[('joint',point)])])
        with patch('autospine_workbench.targets.character43.motion_depth.project_bvh_frames',return_value=projected):
            legacy=_source(SimpleNamespace(source_sha256='a'),{'root':{'reference_length_source_units':10}},None)
            side=_source(SimpleNamespace(source_sha256='a'),{'root':{'reference_length_source_units':10}},None,90)
        self.assertEqual(legacy[0][0][1]['joint'],5)
        self.assertAlmostEqual(side[0][0][1]['joint'],3)

    def test_projection_contract_rejects_silent_fallback(self):
        for value in (None,{},dict(profile=PROFILE,yaw_degrees=True),dict(profile=PROFILE,yaw_degrees=91)):
            with self.assertRaises(ValueError): validate(value)

    def test_worker_publishes_oblique_motion_lengths_depth_and_preserves_rig(self):
        with TemporaryDirectory() as temp:
            root=Path(temp); intake=root/'intake'; target=root/'target'
            intake.mkdir(); target.mkdir(); (intake/'source.bvh').write_bytes(source())
            identity=compile_source(source(),'front',intake,root)['motion']
            files,_,_,_=inputs(); doc=json.loads(files['skeleton.json'])
            for name,parent in [('spine','root'),('chest','spine'),('neck','chest')]:
                doc['bones'].append(dict(name=name,parent=parent,x=0,y=10,rotation=0))
            doc['slots']=[dict(name='point',attachment='point',bone='root')]
            files['skeleton.json']=canonical_bytes(doc)
            store=AnimatedStore(root); original=store.publish(files)
            selection=dict(profile=PROFILE,yaw_degrees=30)
            publish_document(target/'request.json',dict(motion_identity=identity,character_sha256=original,
                projection=selection,depth_review_profile='external-arm-torso-depth-review-v1'),staging=target/'staging')
            with patch('autospine_workbench.automation.motion_target_worker.capture',return_value={'status':'unavailable'}):
                execute(target,root,root)
            result=read_document(target/'worker-result.json'); output=store.read(result['artifact_sha256'])
            self.assertEqual(result['projection'],selection)
            self.assertEqual(json.loads(output['motion-depth.json'])['yaw_degrees'],30)
            review=json.loads(output['motion-review.json'])
            self.assertEqual(review['projected_lengths']['yaw_degrees'],30)
            receipt=json.loads(output['motion-projection.json'])
            self.assertEqual(receipt['yaw_degrees'],30)
            self.assertTrue(json.loads(output['motion-ir.json'])['clip_id'].startswith('oblique.'))
            self.assertEqual(store.read(original),files)


if __name__=='__main__': unittest.main()
