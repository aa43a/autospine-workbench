import tempfile
import unittest
from pathlib import Path
from copy import deepcopy
from autospine_workbench.automation.sleeve_overlap_step import summaries
from autospine_workbench.automation.storage_io import publish_document
from autospine_workbench.resolved_project import canonical_sha256
from autospine_workbench.asset.planning.sleeve_motion_envelope import MOTIONS


class OverlapStepTests(unittest.TestCase):
    def fixture(self):
        export = dict(schema='autospine.sleeve-export-report/v1',records=[dict(layer_id='sleeve', component_id='part', status='candidate_exported', files={'image':'a'*64})])
        row = dict(layer_id='sleeve', component_id='part', asset_sha256={'image':'a'*64}, authority='none',
            production_authorized=False, framebuffer_status='not_evaluated', status='diagnostic_only',
            profile='pairwise-triangle-overlap-v2', texture_visibility='native_centers_all_intersecting_pairs',
            tracks=[dict(animation=n, frames=257, frames_with_increased_overlap=0, tested_pair_frames=0,
                frames_with_increased_dual_alpha8=0, visible_peak=None) for n, _ in MOTIONS])
        doc = dict(purpose='sleeve_overlap_diagnostic', project_id='fixture', source_report_sha256=canonical_sha256(export),
            authority='none', production_authorized=False, framebuffer_status='not_evaluated', records=[row])
        return export, doc

    def read(self, export, doc):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); path=root/'overlap/fixture'; path.mkdir(parents=True)
            publish_document(path/(canonical_sha256(doc)+'.json'), doc, staging=root/'.staging')
            return summaries(root, 'fixture', export)['sleeve', 'part']

    def test_no_findings_still_diagnostic(self):
        row=self.read(*self.fixture())
        self.assertEqual(row['status'], 'diagnostic_only')
        self.assertEqual(row['framebuffer_status'], 'not_evaluated')
        self.assertEqual(row['frames'], 1799)

    def test_v2_ordinary_overlap_keeps_four_exact_tracks(self):
        from autospine_workbench.automation.sleeve_motion_inventory import ORDINARY,PROFILES
        export,doc=self.fixture();meta=dict(motion_profile=ORDINARY,motion_source_sha256='b'*64)
        export['schema']='autospine.sleeve-export-report/v2';export['records'][0].update(meta)
        doc.update(schema='autospine.sleeve-overlap/v2',source_report_sha256=canonical_sha256(export))
        track=doc['records'][0]['tracks'][0]
        doc['records'][0].update(meta,tracks=[dict(track,animation=name) for name in PROFILES[ORDINARY]])
        self.assertEqual(self.read(export,doc)['frames'],1028)
        changed=deepcopy(doc);changed['records'][0]['tracks'].pop()
        with self.assertRaisesRegex(ValueError,'motion_inventory'):self.read(export,changed)

    def test_visible_peak_and_frame_count_are_preserved(self):
        export, doc=self.fixture(); track=doc['records'][0]['tracks'][0]
        track.update(tested_pair_frames=20, frames_with_increased_dual_alpha8=3,
            visible_peak=dict(time=.5, triangles=[1,2], excess_pair_pixels=5, setup_pair_pixels=2,
                tested_pixels=10, dual_alpha8_pixels=7, max_min_alpha=96., scope='pair_bbox_native_centers'))
        row=self.read(export,doc)
        self.assertEqual((row['affected_frames'],row['peak_excess_pair_pixels']),(3,5))

    def test_wrong_source_inventory_authority_and_counts_rejected(self):
        export, doc=self.fixture()
        mutations=[lambda d:d.update(source_report_sha256='0'*64),
            lambda d:d.update(records=[]), lambda d:d.update(framebuffer_status='passed'),
            lambda d:d['records'][0].update(status='passed'),
            lambda d:d['records'][0].update(asset_sha256={}),
            lambda d:d['records'][0]['tracks'][0].update(frames=True),
            lambda d:d['records'][0]['tracks'][0].update(frames_with_increased_dual_alpha8=1),
            lambda d:d['records'][0]['tracks'][0].update(animation='unknown')]
        for mutate in mutations:
            changed=deepcopy(doc); mutate(changed)
            with self.assertRaises(ValueError): self.read(export,changed)
