"""Small geometric fixtures; capture is explicitly mocked, not browser evidence."""
from copy import deepcopy
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from zipfile import ZipFile

from autospine_workbench.automation import motion_target_jobs as jobs
from autospine_workbench.automation import motion_transverse_repair as api
from autospine_workbench.automation import motion_repair_worker as worker
from autospine_workbench.automation.storage_io import canonical_bytes
from autospine_workbench.resolved_project import canonical_sha256
from autospine_workbench.targets.character43.affine_pose import sample
from autospine_workbench.targets.character43.limb_transverse_scope import PROFILE, resolve
from autospine_workbench.targets.character43.selected_transverse_candidate import build, summary
from test_limb_transverse_repair import fixture

CONTACT = 'autospine_workbench.targets.character43.limb_transverse_candidate.recheck'


def bundle(scale=.7):
    doc = fixture(); doc['animations']['motion']['bones']['thigh_l']['scale'][-1]['x'] = scale
    raw = canonical_bytes(doc); digest = sha256(raw).hexdigest()
    rest = deepcopy(doc); rest['animations']['motion'] = {'bones': {}}
    setup = sample(rest, 'motion', 0)[0]
    frames = [dict(time=t, vertices=sample(doc, 'motion', t)[0]) for t in (0, .5, 1)]
    files = {'skeleton.json':raw, 'numeric-reference.json':canonical_bytes(dict(skeleton_sha256=digest, animations={'motion':frames})),
        'rig-setup-reference.json':canonical_bytes(dict(skeleton_sha256=digest, vertices=setup)),
        'motion-review.json':canonical_bytes(dict(reference_length_px=20, issues=[],
            source_pose_fit={'profile':'source-absolute-limb-projection-v1'})),
        'motion-ir.json':b'{}', 'motion-contact.json':b'{}', 'skeleton.atlas':b'exact atlas',
        'motion-torso-projection.json':b'exact torso', 'images/leg.png':b'exact texture',
        'motion-depth.json':b'old depth', 'character-manifest.json':b'{}'}
    return files, {'skeleton.json':raw}


def plan_for(files, character):
    return dict(action='transverse_repair', slot='leg', animation='motion', artifact_sha256='parent',
        transverse_repair=dict(resolve(files, character, 'leg', 'motion'), character_sha256='character'))


class TransverseWorkflowTests(unittest.TestCase):
    def test_scope_is_leg_only_and_checks_references_bind_and_linear_tracks(self):
        files, character = bundle(); original = deepcopy(files)
        scope = resolve(files, character, 'leg', 'motion')
        self.assertEqual(scope['bones'], ['calf_l']); self.assertEqual(scope['vertex_count'], 3)
        self.assertEqual(files, original)
        cases = [('rig-setup-reference.json', {'skeleton_sha256':'changed'}, 'reference_changed'),
                 ('motion-review.json', {}, 'projection_required')]
        for key, value, reason in cases:
            changed = dict(files, **{key:canonical_bytes(value)})
            with self.assertRaisesRegex(ValueError, reason):resolve(changed, character, 'leg', 'motion')
        changed = json.loads(character['skeleton.json']); changed['bones'][1]['x'] = 100
        with self.assertRaisesRegex(ValueError, 'bind_changed'):
            resolve(files, {'skeleton.json':canonical_bytes(changed)}, 'leg', 'motion')
        arms = {k:raw.replace(b'thigh_l',b'upperarm_l').replace(b'calf_l',b'forearm_l').replace(b'foot_l',b'hand_l')
                for k,raw in files.items()}
        digest = sha256(arms['skeleton.json']).hexdigest()
        for key in ('numeric-reference.json','rig-setup-reference.json'):
            value = json.loads(arms[key]); value['skeleton_sha256'] = digest; arms[key] = canonical_bytes(value)
        with self.assertRaisesRegex(ValueError, 'leg_required'):
            resolve(arms, {'skeleton.json':arms['skeleton.json']}, 'leg', 'motion')

    def test_candidate_keeps_channels_and_refreshes_same_grid_qa_and_manifest(self):
        files, character = bundle(); original = deepcopy(files); stages = []
        with patch(CONTACT, return_value={'status':'unavailable_no_labels'}):
            output, evidence, geometry = build(files, character, plan_for(files, character), stages.append)
        self.assertEqual(files, original)
        before, after = (json.loads(p['skeleton.json']) for p in (files,output))
        for key in ('bones','slots','skins'):self.assertEqual(before[key],after[key])
        self.assertEqual(before['animations']['motion']['bones'], after['animations']['motion']['bones'])
        for name in ('images/leg.png','skeleton.atlas','motion-ir.json','motion-torso-projection.json'):
            self.assertEqual(files[name],output[name])
        self.assertNotIn('motion-depth.json',output)
        report = json.loads(output['motion-repair.json']); compact = report['transverse_repair']
        self.assertEqual(report['profile'],PROFILE); self.assertTrue(compact['geometry_passed'])
        self.assertEqual([r['sample_count'] for r in report['parent_geometry']['records']],
                         [r['sample_count'] for r in geometry['records']])
        self.assertFalse(evidence['selected']); self.assertEqual(evidence['runtime_status'],'not_evaluated')
        self.assertTrue({'compensate_transverse','correct_joints','validate'} <= {r['stage'] for r in stages})
        manifest = json.loads(output['character-manifest.json'])
        self.assertEqual(manifest['files'], {k:sha256(v).hexdigest() for k,v in output.items() if k!='character-manifest.json'})
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'request.json').write_bytes(canonical_bytes({'character_sha256':'character'}))
            manager=SimpleNamespace(folder=lambda _:root)
            with patch.object(jobs,'context',return_value=({'artifact_sha256':'candidate'},output)), patch.object(jobs,'assert_current'):
                archive=jobs.download(manager,'job')
            with ZipFile(BytesIO(archive)) as zipped:
                self.assertEqual({n:zipped.read(n) for n in zipped.namelist()},output)
        with self.assertRaisesRegex(ValueError,'already_applied'):resolve(output,character,'leg','motion')

    def test_fixed_projection_failure_stays_diagnostic_and_regression_is_visible(self):
        files, character = bundle(.3)
        with patch(CONTACT, return_value={'status':'unavailable_no_labels'}):
            output, evidence, geometry = build(files, character, plan_for(files,character))
        compact = json.loads(output['motion-repair.json'])['transverse_repair']
        self.assertFalse(geometry['passed']); self.assertFalse(compact['geometry_passed'])
        self.assertEqual(compact['validation'],'projected_only_diagnostic')
        self.assertGreater(compact['fixed_area_blocker']['observations'],0)
        self.assertLess(compact['fixed_area_blocker']['worst']['setup_ratio'],.5)
        self.assertIn('motion_transverse_fixed_area_diagnostic',[r['reason_code'] for r in evidence['issues']])
        report = json.loads(output['motion-transverse.json'])
        next(r for r in report['geometry']['records'] if r['slot']=='leg')['failing_frame_count'] = 999
        self.assertIn('failing_frame_count',summary(report,'leg')['regressions'])

    def test_changed_frozen_scope_stops_before_bake(self):
        files, character = bundle(); plan = plan_for(files,character)
        files['motion-contact.json'] = b'{"changed":true}'
        with patch('autospine_workbench.targets.character43.selected_transverse_candidate.compensate') as bake:
            with self.assertRaisesRegex(ValueError,'scope_changed'):build(files,character,plan)
        bake.assert_not_called()

    def test_readonly_capability_and_visual_entry_do_not_accept_or_modify(self):
        files, character = bundle()
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); (root/'request.json').write_bytes(canonical_bytes({'character_sha256':'character'}))
            store=Mock(); store.read.return_value=character
            manager=SimpleNamespace(folder=lambda _:root,
                character_manager=lambda:SimpleNamespace(application=SimpleNamespace(store=store)))
            with patch.object(jobs,'context',return_value=({'artifact_sha256':'parent'},files)), patch.object(jobs,'assert_current'):
                raw,_ = jobs.review_file(manager,'job',['transverse-repair','leg','motion.json'])
                value=json.loads(raw);self.assertTrue(value['available']);self.assertFalse(value['selected'])
                self.assertEqual(value['scope']['character_sha256'],'character')
                with self.assertRaisesRegex(RuntimeError,'candidate_changed'):api.scope(manager,'job','leg','motion','stale')
                from autospine_workbench.automation.motion_visual_scope_event import validate
                event=validate(manager,'job',dict(visual_inspection=True,triangle=-1,action='transverse_repair',
                    slot='leg',animation='motion',time=.4,artifact_sha256='parent'))
                self.assertFalse(event['detected_failure'])
                files.pop('motion-review.json')
                raw,_=jobs.review_file(manager,'job',['transverse-repair','leg','motion.json'])
                self.assertEqual(json.loads(raw)['reason_code'],'motion_transverse_source_missing')
            self.assertEqual([p.name for p in root.iterdir()],['request.json'])

    def test_worker_dispatch_provenance_revalidation_and_summary_with_mock_capture(self):
        files, character = bundle(); plan = plan_for(files,character)
        request = dict(character_sha256='character',repair_execution=dict(profile=PROFILE,draft=plan,
            draft_sha256=canonical_sha256(plan),parent_job_id='parent-job',parent_artifact_sha256='parent'))
        store=Mock();store.read.side_effect=lambda key:files if key=='parent' else character
        store.publish.return_value='candidate'
        def depth(output,*args):output['motion-depth.json']=b'{"status":"not_evaluated"}';return {}
        with tempfile.TemporaryDirectory() as tmp, patch.object(worker,'AnimatedStore',return_value=store), \
             patch.object(worker,'capture',return_value={'status':'mock_only'}) as capture, \
             patch.object(worker,'progress',wraps=worker.progress) as progress, patch(CONTACT,return_value={'status':'unavailable'}), \
             patch('autospine_workbench.automation.motion_repair_depth.recheck',side_effect=depth) as depth_call, \
             patch('autospine_workbench.automation.motion_repair_local_depth.run',return_value=None):
            worker.execute(Path(tmp),Path(tmp),Path(tmp),request)
            output=store.publish.call_args.args[0]
            self.assertEqual(json.loads(output['motion-repair-provenance.json'])['draft'],plan)
            self.assertEqual(capture.call_count,1);self.assertEqual(depth_call.call_count,1)
            self.assertTrue({'transverse_compensate','transverse_joint','transverse_validate'} <= {c.args[1] for c in progress.call_args_list})
            result=json.loads((Path(tmp)/'worker-result.json').read_bytes())
            self.assertEqual(result['repair_profile'],PROFILE);self.assertFalse(result['production_authorized'])
            with patch.object(jobs,'context',return_value=({'artifact_sha256':'candidate'},output)):
                raw,_=jobs.review_file(None,'job',['repair-summary.json'])
            self.assertEqual(json.loads(raw)['transverse_repair']['sample_count'],
                json.loads(output['motion-transverse.json'])['sample_count'])
            request['character_sha256']='stale'
            with self.assertRaisesRegex(ValueError,'character_changed'):worker.execute(Path(tmp),Path(tmp),Path(tmp),request)
            self.assertEqual(capture.call_count,1)

    def test_failure_reason_preserves_specific_internal_diagnostic(self):
        from autospine_workbench.automation.motion_intake_process import failure_reason
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'stderr.log'
            path.write_bytes(canonical_bytes({'reason_code':'limb_transverse_interpolation_unresolved'}))
            self.assertEqual(failure_reason(path),'limb_transverse_interpolation_unresolved')
            path.write_bytes(canonical_bytes({'reason_code':'arbitrary local path'}))
            self.assertEqual(failure_reason(path),'motion_decode_failed')
