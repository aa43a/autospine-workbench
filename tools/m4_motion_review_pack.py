"""Build an exact-candidate navigation pack; never write review decisions."""
import json
from urllib.parse import quote
from m4_motion_cohort import digest


def url(plan,state):
    if state.get('plan_sha256')!=digest(plan):raise ValueError('cohort_plan_identity_mismatch')
    groups=[];missing=[]
    for source in plan['motions']:
        original=state['sources'].get(source['id'],{})
        if original.get('status')!='succeeded':
            missing.extend(dict(motion=source['id'],character=c['id'],status='source_'+original.get('status','not_started')) for c in plan['characters'])
            continue
        if original.get('source_sha256')!=source['sha256']:
            raise ValueError('cohort_review_source_mismatch')
        targets=[]
        for character in plan['characters']:
            job=state['cells'].get(source['id']+'/'+character['id'],{})
            if job.get('status')!='succeeded':
                missing.append(dict(motion=source['id'],character=character['id'],status=job.get('status','not_started')))
                continue
            targets.append(dict(label=character['id'],job_id=job['job_id'],
                                artifact_sha256=job['result']['artifact_sha256']))
        if targets:groups.append(dict(label=source['id'],job_id=original['job_id'],
            source_sha256=source['sha256'],targets=targets))
    if not groups:return None
    pack=dict(version=1,plan_sha256=digest(plan),groups=groups,
        coverage=dict(expected=len(plan['motions'])*len(plan['characters']),available=sum(len(g['targets']) for g in groups),missing=missing))
    return 'http://127.0.0.1:8918/motion-cohort.html#'+quote(json.dumps(pack,separators=(',',':'),ensure_ascii=False))
