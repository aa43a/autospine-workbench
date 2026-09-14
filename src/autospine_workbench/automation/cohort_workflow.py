"""First-ten workflow progress with the same gates as the fixed-three assessment."""
from .character_acceptance import assess_character

REQUIRED = ['idle', 'wave-left', 'walk']


def selected_project(row):
    active = [p for p in row['exact_projects'] if p['lifecycle'] == 'active']
    if row['reason_code'] == 'source_matched_workflow_not_assessed' and len(active) == 1:
        return active[0]['id']
    return None


def summarize(intake, observations):
    if (intake.get('schema') != 'autospine.cohort-intake/v2' or intake.get('authority') != 'none'
            or intake.get('production_authorized') is not False):
        raise ValueError('cohort_workflow_verified_intake_required')
    characters = intake['characters']
    if len(characters) != 10 or len({r['character_id'] for r in characters}) != 10:
        raise ValueError('cohort_workflow_fixed_ten_required')
    projects = [selected_project(r) for r in characters if selected_project(r) is not None]
    if len(projects) != len(set(projects)):
        raise ValueError('cohort_workflow_duplicate_project')
    expected = set(projects)
    if set(observations) != expected:
        raise ValueError('cohort_workflow_observation_inventory')
    rows = []
    for character in characters:
        project = selected_project(character)
        observation = observations[project] if project else {'reason_code': character['reason_code']}
        row = assess_character(dict(project_id=project, name=character['name']), observation, REQUIRED)
        row.update(character_id=character['character_id'], dataset_split=character['dataset_split'],
                   source_reason_code=character['reason_code'])
        rows.append(row)
    measured = [r for r in rows if r['runtime_measured']]
    completed = sum(r['completed'] for r in rows)
    result = dict(schema='autospine.cohort-workflow/v1', authority='none', production_authorized=False,
                scope='first_ten_current_selected_versions_not_independent_holdout', characters=rows,
                required_animations=REQUIRED, metrics=dict(total_characters=10,
                    completed_characters=completed, completion_rate=completed / 10,
                    runtime_measured_characters=len(measured), required_motion_cases=30,
                    runtime_passed_motion_cases=sum(m['status'] == 'passed' for r in rows for m in r['motions']),
                    runtime_failure_rate=sum(not r['runtime_passed'] for r in measured) / len(measured) if measured else None,
                    human_review_minutes=None, incorrect_auto_adoption_rate=None),
                unmeasured_reasons=dict(human_review_minutes='operation_timing_not_available',
                    incorrect_auto_adoption_rate='independent_labels_not_available'))
    if any('auto_binding_audit' in o for o in observations.values()):
        from .character_auto_audit_metrics import summarize as audit_metrics
        result['metrics']['auto_binding_audit'] = audit_metrics(observations)
    return result
