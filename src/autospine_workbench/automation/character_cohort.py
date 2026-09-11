"""Fixed-denominator character acceptance; missing evidence never means success."""


def validate_cohort(cohort):
    if (cohort.get('schema')!='autospine.character-milestone-cohort/v1' or cohort.get('authority')!='none'
            or cohort.get('purpose')!='development_integration_not_independent_holdout'
            or cohort.get('required_animations')!=['idle','wave-left','walk'] or len(cohort.get('characters',[]))!=3):
        raise ValueError('character_cohort_invalid')
    if {r['structure'] for r in cohort['characters']}!={'ordinary_limbs','ordinary_sleeve_repair','wide_sleeve_repair'}:
        raise ValueError('character_cohort_structure_inventory')
    if any(r['original_split'] not in {'development','visible','reserve'} for r in cohort['characters']):
        raise ValueError('character_cohort_holdout_not_development')


def summarize(cohort,observations):
    validate_cohort(cohort)
    characters=cohort['characters'];ids=[r['project_id'] for r in characters]
    if len(ids)!=len(set(ids)) or set(observations)!=set(ids):raise ValueError('character_cohort_inventory')
    rows=[]
    for character in characters:
        observed=observations[character['project_id']];job=observed.get('job') or {};reasons=[]
        current=job.get('status')=='needs_review'
        missing=sorted(set(cohort['required_animations'])-set(job.get('animations',[])))
        if not current:reasons.append(observed.get('reason_code') or job.get('reason_code') or 'character_candidate_missing')
        if missing:reasons.append('required_animations_missing')
        runtime=observed.get('verified_runtime');runtime_passed=runtime is not None and runtime.get('passed') is True
        if not runtime_passed:reasons.append('runtime_failed' if runtime is not None else 'runtime_unmeasured')
        if job.get('runtime',{}).get('geometry_status')!='passed':reasons.append('geometry_not_passed')
        layers=job.get('layers',[])
        unresolved=[r['layer_id'] for r in layers if r['state'] not in {'rigid_reviewed','weighted_candidate','excluded','not_visible'}
                    or r.get('binding_decision',{}).get('decision_source')=='pending']
        stale_auto=[r['layer_id'] for r in layers
                    if r.get('binding_decision',{}).get('decision_source')=='policy_auto'
                    and r['binding_decision'].get('evidence_current') is not True]
        unresolved=sorted(set(unresolved+stale_auto))
        if stale_auto:reasons.append('automatic_binding_evidence_stale')
        if not layers:reasons.append('layer_inventory_missing')
        if unresolved:reasons.append('layer_binding_incomplete')
        review=observed.get('visual_review')
        visual=bool(review and all(review.get('aspects',{}).get(k)=='acceptable' for k in ('setup','draw_order','connections','motion')))
        if not visual:reasons.append('whole_character_visual_review_required')
        rows.append(dict(project_id=character['project_id'],name=character['name'],job_id=job.get('job_id'),
                         artifact_sha256=job.get('artifact_sha256'),completed=not reasons,reason_codes=reasons,
                         missing_animations=missing,unresolved_layers=unresolved,stale_auto_layers=stale_auto,runtime_measured=runtime is not None,
                         runtime_passed=runtime_passed,visual_accepted=visual))
    measured=[r for r in rows if r['runtime_measured']];passed=sum(r['completed'] for r in rows)
    return dict(schema='autospine.character-cohort-assessment/v1',cohort_id=cohort['cohort_id'],authority='none',
                characters=rows,metrics=dict(completed_characters=passed,total_characters=len(rows),
                completion_rate=passed/len(rows) if rows else None,runtime_measured_characters=len(measured),
                runtime_failure_rate=sum(not r['runtime_passed'] for r in measured)/len(measured) if measured else None,
                human_review_minutes=None,incorrect_auto_adoption_rate=None),
                unmeasured_reasons=dict(human_review_minutes='operation_timing_not_available',incorrect_auto_adoption_rate='independent_labels_not_available'))
