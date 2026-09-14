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
    from .character_acceptance import assess_character
    rows=[assess_character(c,observations[c['project_id']],cohort['required_animations'])
          for c in characters]
    measured=[r for r in rows if r['runtime_measured']];passed=sum(r['completed'] for r in rows)
    result = dict(schema='autospine.character-cohort-assessment/v1',cohort_id=cohort['cohort_id'],authority='none',
                characters=rows,metrics=dict(completed_characters=passed,total_characters=len(rows),
                completion_rate=passed/len(rows) if rows else None,runtime_measured_characters=len(measured),
                required_motion_cases=len(rows)*len(cohort['required_animations']),
                runtime_passed_motion_cases=sum(m['status']=='passed' for r in rows for m in r['motions']),
                runtime_failure_rate=sum(not r['runtime_passed'] for r in measured)/len(measured) if measured else None,
                human_review_minutes=None,incorrect_auto_adoption_rate=None),
                unmeasured_reasons=dict(human_review_minutes='operation_timing_not_available',incorrect_auto_adoption_rate='independent_labels_not_available'))
    if any('auto_binding_audit' in o for o in observations.values()):
        from .character_auto_audit_metrics import summarize as audit_metrics
        result['metrics']['auto_binding_audit'] = audit_metrics(observations)
    return result
