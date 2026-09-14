"""Measured spot-check counts, distinct from population accuracy or automatic acceptance."""
from .character_auto_audit import summary


def summarize(observations):
    counts = dict(eligible_bindings=0, assessed_bindings=0, correct=0, incorrect=0,
                  unobservable=0, not_reviewed=0)
    projects = 0
    for observed in observations.values():
        job = observed.get('job') or {}
        if job.get('status') != 'needs_review': continue
        row = summary(job, observed.get('auto_binding_audit'))
        for key in counts: counts[key] += row[key]
        projects += 1
    total = counts['assessed_bindings']
    return dict(counts, sampled_error_rate=counts['incorrect']/total if total else None,
                projects_with_current_candidate=projects,
                sampling_scope='human_selected_current_bindings_not_population_accuracy')
