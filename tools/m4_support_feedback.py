"""Read sampling feedback only from an exact, verified Runtime experiment."""
from hashlib import sha256
import json
from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.automation.storage_io import canonical_bytes
from autospine_workbench.targets.character43.numeric_reference import read


def load(folder,job,source):
    report=json.loads((folder/'report.json').read_bytes())
    if report['source_job_id']!=job or report['source_candidate_sha256']!=source:
        raise ValueError('support_feedback_source_mismatch')
    artifact=report['candidate_bundle_sha256']
    files=AnimatedStore(folder/'isolated-store').read(artifact)
    raw=(folder/'runtime/report.json').read_bytes(); runtime=json.loads(raw)
    numeric=read(files)
    if runtime['bundle_sha256']!=artifact or runtime['passed'] is not True or numeric['skeleton_sha256']!=sha256(files['skeleton.json']).hexdigest():
        raise ValueError('support_feedback_runtime_identity_mismatch')
    times=[r['time'] for r in runtime['results']]
    if any(r['animation']!='external-motion' for r in runtime['results']) or times!=[r['time'] for r in numeric['animations']['external-motion']]:
        raise ValueError('support_feedback_time_grid_mismatch')
    return times,dict(profile='runtime-sample-feedback-v1',artifact_sha256=artifact,
        runtime_report_sha256=sha256(raw).hexdigest(),times_sha256=sha256(canonical_bytes(times)).hexdigest(),
        sample_count=len(times),authority='none',scope='additional_samples_not_visual_acceptance')
