"""Read-only contact provenance and intervals for exact compiled sources."""
from hashlib import sha256

from ..bvh_parser import parse_bvh
from ..motion_bundle_reader import VerifiedMotionBundleReader
from ..motion2d.contact_candidate import infer
from ..safe_input_files import read_real_file
from .pipeline_run import PipelineRunError


def inspect(manager, job_id):
    job = manager.get(job_id)
    if job.get('kind') == 'adapt' or job['status'] != 'succeeded' or job['result'].get('motion_status') != 'compiled':
        raise PipelineRunError('motion_contact_source_unavailable')
    raw = read_real_file(manager.folder(job_id)/('source.'+job['format']), 64 << 20, 'motion source')
    if sha256(raw).hexdigest() != job['source_sha256']:
        raise PipelineRunError('motion_source_changed')
    identity = job['result']['motion']
    bundle = VerifiedMotionBundleReader(manager.state_root).load(identity['clip_sha256'], identity['bundle_sha256'])
    motion = bundle.motion
    markers = [m for m in motion['markers'] if m['kind'] == 'contact']
    if markers:
        report = dict(status='source_markers', markers=markers, ticks_per_second=motion['ticks_per_second'],
                      authority='none', selected=False, profile='compiled-source-contact-markers',
                      scope='source_contact_markers_not_target_validation')
    elif bundle.source_kind == 'bvh':
        report = infer(parse_bvh(bundle.raw_bvh), bundle.bvh_map)
    else:
        report = dict(status='unavailable', markers=[], reason='source_contact_labels_missing',
                      authority='none', selected=False)
    report.update(source_job_id=job_id, input_source_sha256=job['source_sha256'], motion_identity=identity,
                  duration_seconds=motion['duration_ticks']/motion['ticks_per_second'])
    return report
