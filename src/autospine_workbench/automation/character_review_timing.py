"""Explicit operator stopwatch metadata; not total project labor or active attention."""
import math


def valid(value):
    return (type(value) is dict and set(value)=={'method','seconds','scope'}
            and value['method']=='operator_stopwatch_v1'
            and value['scope']=='whole_character_visual_review_session'
            and type(value['seconds']) in (int,float) and math.isfinite(value['seconds'])
            and 0<=value['seconds']<=86400)


def minutes(review):
    value=(review or {}).get('timing')
    return value['seconds']/60 if valid(value) else None


def summarize(rows):
    """Count measured current-candidate sessions, keeping missing time unknown."""
    measured = [r['visual_review_session_minutes'] for r in rows
                if r.get('visual_review_session_minutes') is not None]
    return dict(scope='current_candidate_visual_review_sessions_only',
                measured_characters=len(measured), total_characters=len(rows),
                unmeasured_character_ids=[r.get('character_id', r['project_id']) for r in rows
                                          if r.get('visual_review_session_minutes') is None],
                measured_minutes=math.fsum(measured) if measured else None,
                all_characters_measured=bool(rows) and len(measured)==len(rows))
