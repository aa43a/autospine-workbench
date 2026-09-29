"""Read exact current batch artifacts and report separate compatible groups."""
from ..targets.character43.animation_compatibility import signature, compare, PROFILE
from .motion_target_jobs import context


def inspect(manager, batch):
    value = manager.get(batch)
    production = manager.production
    cells, groups, baselines = [], {}, {}
    for cell in value['cells']:
        row = dict(run_id=cell['run_id'], project_id=cell['request']['project_id'])
        try:
            run = production.get(cell['run_id'])
            production.driver.validate(run['request'])
            joint = run['stages']['joint']
            if joint['status'] != 'succeeded':
                row.update(status='not_ready', reason_code='production_joint_not_ready')
            else:
                result, files = context(production.driver.motions, joint['job_id'])
                if result['artifact_sha256'] != joint['artifact_sha256']:
                    raise ValueError('production_completed_child_changed')
                current = signature(files)
                key = (row['project_id'], current['signature_sha256'])
                groups.setdefault(key, []).append(cell['run_id'])
                baseline = baselines.setdefault(row['project_id'], current)
                row.update(status='checked', job_id=joint['job_id'], artifact_sha256=result['artifact_sha256'],
                           signature_sha256=current['signature_sha256'], animations=current['animations'],
                           differences_from_first=compare(baseline, current))
        except (OSError, ValueError, RuntimeError, KeyError, TypeError) as exc:
            row.update(status='unavailable', reason_code=getattr(exc, 'reason_code', str(exc)))
        cells.append(row)
    return dict(profile=PROFILE, batch_id=batch, batch_revision=value['revision'], cells=cells,
                groups=[dict(project_id=p, signature_sha256=s, run_ids=r, can_merge=len(r) > 1)
                        for (p, s), r in groups.items()],
                authority='none', production_authorized=False, runtime_recheck_required=True,
                scope='structural_compatibility_only_not_visual_or_merged_runtime_validation')
