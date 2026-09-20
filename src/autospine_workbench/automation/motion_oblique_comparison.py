"""Source-bound whole-clip oblique proposals; no target or visual approval."""
from ..resolved_project import canonical_sha256
from ..targets.character43.oblique_source import extract
from ..targets.character43.oblique_motion import compile_candidate
from .motion_projection_review import source_context

PROFILE='whole-source-oblique-selection-v1'


def compare(bundle):
    data=extract(bundle); records=[]
    precision=5 if bundle.source_kind=='kimodo_npz' else 12
    for yaw in range(-90,91,15):
        try:
            _,receipt=compile_candidate(bundle.motion,*data,yaw,precision=precision)
        except ValueError as exc:
            records.append(dict(yaw_degrees=yaw,passed=False,reason_code=str(exc)))
            continue
        report=receipt['projection']
        records.append(dict(yaw_degrees=yaw,passed=report['passed'],motion_sha256=receipt['motion_sha256'],
                            failed_roles=[r['role'] for r in report['records'] if not r['passed']]))
    passing=[r['yaw_degrees'] for r in records if r['passed']]
    selected=min(passing,key=lambda yaw:(abs(yaw),yaw)) if passing else None
    return dict(profile=PROFILE,recommended_yaw_degrees=selected,records=records,authority='none',
                status='qualified_source_angle' if selected is not None else 'no_qualified_angle',
                scope='full_source_sampled_projection_not_target_or_artwork_acceptance')


def inspect(manager,job_id):
    job,bundle,_=source_context(manager,job_id)
    report=compare(bundle)
    report.update(source_job_id=job_id,source_sha256=job['source_sha256'],motion_identity=job['result']['motion'])
    report['comparison_sha256']=canonical_sha256(report)
    return report


def validate_selection(manager,job_id,selection,projection):
    if not isinstance(selection,dict) or set(selection)!={'comparison_sha256'}:
        raise ValueError('motion_oblique_selection_invalid')
    report=inspect(manager,job_id)
    if (report['comparison_sha256']!=selection['comparison_sha256'] or projection is None
            or report['recommended_yaw_degrees'] is None
            or projection['yaw_degrees']!=report['recommended_yaw_degrees']):
        raise ValueError('motion_oblique_selection_changed')
    return dict(profile=PROFILE,comparison_sha256=report['comparison_sha256'],
                source_job_id=job_id,yaw_degrees=report['recommended_yaw_degrees'])
