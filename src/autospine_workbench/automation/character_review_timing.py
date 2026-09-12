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
