"""Shared per-character acceptance gates; callers verify source evidence first."""


def assess_character(character, observed, required_animations):
    job=observed.get('job') or {};reasons=[]
    current=job.get('status')=='needs_review'
    missing=sorted(set(required_animations)-set(job.get('animations',[])))
    if not current:reasons.append(observed.get('reason_code') or job.get('reason_code') or 'character_candidate_missing')
    if missing:reasons.append('required_animations_missing')
    runtime=observed.get('verified_runtime');runtime_passed=runtime is not None and runtime.get('passed') is True
    from .character_motion_metrics import motion_rows
    motions=motion_rows(job,runtime,required_animations)
    if any(r['status']!='passed' for r in motions):reasons.append('required_motion_runtime_incomplete')
    if not runtime_passed:reasons.append('runtime_failed' if runtime is not None else 'runtime_unmeasured')
    if job.get('runtime',{}).get('geometry_status')!='passed':reasons.append('geometry_not_passed')
    layers=job.get('layers',[])
    from .character_weighted_review import confirmed_layers
    region_confirmed=confirmed_layers(job,observed.get('weighted_review'))
    from .character_binding_status import needs_review
    unresolved=[r['layer_id'] for r in layers if needs_review(r,region_confirmed)]
    stale_auto=[r['layer_id'] for r in layers
                if r.get('binding_decision',{}).get('decision_source')=='policy_auto'
                and r['binding_decision'].get('evidence_current') is not True]
    unresolved=sorted(set(unresolved+stale_auto))
    from .character_auto_audit import verified_reviews
    audit = verified_reviews(job, observed.get('auto_binding_audit'))
    incorrect = [key for key, verdict in audit.items() if verdict == 'incorrect']
    if incorrect:
        unresolved=sorted(set(unresolved+incorrect));reasons.append('automatic_binding_audit_needs_changes')
    if stale_auto:reasons.append('automatic_binding_evidence_stale')
    if not layers:reasons.append('layer_inventory_missing')
    if unresolved:reasons.append('layer_binding_incomplete')
    review=observed.get('visual_review')
    from .character_review_timing import minutes
    visual=bool(review and all(review.get('aspects',{}).get(k)=='acceptable' for k in ('setup','draw_order','connections','motion')))
    if not visual:reasons.append('whole_character_visual_review_required')
    return dict(project_id=character['project_id'],name=character['name'],job_id=job.get('job_id'),
                     artifact_sha256=job.get('artifact_sha256'),completed=not reasons,reason_codes=reasons,
                     motions=motions,
                     missing_animations=missing,unresolved_layers=unresolved,region_confirmed_layers=sorted(region_confirmed),stale_auto_layers=stale_auto,runtime_measured=runtime is not None,
                     runtime_passed=runtime_passed,visual_accepted=visual,visual_review_session_minutes=minutes(review))
