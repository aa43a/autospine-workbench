"""Create an isolated full-animation diagnostic retaining source and time identity."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.automation.storage_io import canonical_bytes
from autospine_workbench.targets.character43.limb_transverse_repair import build as compensate
from autospine_workbench.targets.character43.joint_boundary_animation import build
from m4_transverse_timeline_screen import validate_times


def run(state,artifact,slot,source,output,margin_source=None,subdivisions=4,compensation_source=None,refine_source=None):
    raw=(source/'report.json').read_bytes();declaration=json.loads(raw)
    times=json.loads((source/'validation-times.json').read_bytes())
    validate_times(declaration,times,artifact,slot)
    output.mkdir(parents=True,exist_ok=False)
    parent=json.loads(AnimatedStore(state).read(artifact)['skeleton.json'])
    def key_times(doc):return [k['time'] for k in doc['animations']['external-motion']['attachments']['default'][slot][slot]['deform']]
    if compensation_source is None:
        candidate,compensation=compensate(parent,'external-motion',[slot],correction_frame='transverse',anchor_terminal=True)
    else:
        from autospine_workbench.targets.character43.boundary_curve_sources import read_compensation
        compensation_raw=(compensation_source/'report.json').read_bytes();compensation=json.loads(compensation_raw)
        candidate=read_compensation(parent,(compensation_source/'skeleton.json').read_bytes(),compensation,artifact,slot,'external-motion')
        times=sorted(set(times)|set(compensation['times']))
        compensation=dict(profile=compensation['profile'],source_report_sha256=sha256(compensation_raw).hexdigest(),
                          skeleton_sha256=compensation['skeleton_sha256'],status=compensation['status'])
    refinement=None
    if refine_source is not None:
        from autospine_workbench.targets.character43.boundary_curve_sources import refinement_times
        refinement_raw=(refine_source/'report.json').read_bytes();previous_report=json.loads(refinement_raw)
        required=refinement_times(parent,(refine_source/'skeleton.json').read_bytes(),previous_report,
                                  artifact,slot,'external-motion',key_times(candidate))
        candidate,refinement=compensate(parent,'external-motion',[slot],correction_frame='transverse',
                                       anchor_terminal=True,required_times=required)
        refinement['source_report_sha256']=sha256(refinement_raw).hexdigest()
        times=sorted(set(times)|set(previous_report['times']))
    margins=None;margin_evidence=None
    if margin_source is not None:
        from autospine_workbench.targets.character43.joint_boundary_margin import measure
        previous_raw=(margin_source/'report.json').read_bytes();previous_report=json.loads(previous_raw)
        if previous_report['parent_artifact_sha256']!=artifact:raise ValueError('boundary_margin_parent_identity')
        times=sorted(set(times)|set(previous_report['times']))
        previous=json.loads((margin_source/'skeleton.json').read_bytes())
        margins,margin_evidence=measure(parent,previous,previous_report,'external-motion',slot)
        from autospine_workbench.targets.character43.boundary_curve_sources import resample_margins
        margins=resample_margins(margins,key_times(previous),key_times(candidate),len(candidate['skins'][0]['attachments'][slot][slot]['triangles'])//3)
        margin_evidence['resampled_target_keys']=len(margins)
        margin_evidence['source_report_sha256']=sha256(previous_raw).hexdigest()
        (output/'margin-evidence.json').write_bytes(canonical_bytes(margin_evidence))
    def progress(value):
        (output/'progress.json').write_bytes(canonical_bytes(value));print(json.dumps(value),flush=True)
    result,report=build(parent,candidate,'external-motion',slot,times,progress=progress,
                        solver_margins=margins,subdivisions=subdivisions)
    skeleton=canonical_bytes(result)
    report.update(parent_artifact_sha256=artifact,slot=slot,source_sha256=sha256(raw).hexdigest(),
                  skeleton_sha256=sha256(skeleton).hexdigest(),compensation=compensation,margin_evidence=margin_evidence)
    report['refinement']=refinement
    (output/'skeleton.json').write_bytes(skeleton)
    (output/'report.json').write_bytes(canonical_bytes(report))
    progress(dict(stage='complete',local_constraints_passed=report['local_constraints_passed'],
                  keys=report['key_count'],samples=len(report['times']),failures=len(report['failures'])))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('state',type=Path);p.add_argument('artifact');p.add_argument('slot')
    p.add_argument('source',type=Path);p.add_argument('output',type=Path)
    p.add_argument('--margin-source',type=Path);p.add_argument('--subdivisions',type=int,default=4)
    p.add_argument('--compensation-source',type=Path)
    p.add_argument('--refine-source',type=Path)
    a=p.parse_args();run(a.state,a.artifact,a.slot,a.source,a.output,a.margin_source,a.subdivisions,a.compensation_source,a.refine_source)
