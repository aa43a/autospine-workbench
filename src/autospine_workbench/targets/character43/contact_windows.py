"""Map source hypotheses to the explicitly selected clip, without source mutation."""
from fractions import Fraction


def for_motion(motion, hypothesis, clip_bounds=None):
    if any(m['kind'] == 'contact' for m in motion['markers']):
        raise ValueError('motion_contact_source_labels_take_precedence')
    rate = motion['ticks_per_second']
    source_rate = hypothesis['ticks_per_second']
    duration = Fraction(motion['duration_ticks'], rate)
    offset = Fraction(0)
    if clip_bounds is not None:
        if (len(clip_bounds) != 2 or any(type(t) is not int for t in clip_bounds)
                or not 0 <= clip_bounds[0] < clip_bounds[1]
                or Fraction(clip_bounds[1] - clip_bounds[0], 1_000_000) != duration):
            raise ValueError('motion_contact_clip_bounds_invalid')
        offset = Fraction(clip_bounds[0], 1_000_000)
    markers = []
    for marker in hypothesis['markers']:
        start = max(Fraction(0), Fraction(marker['start_tick'], source_rate) - offset)
        end = min(duration, Fraction(marker['end_tick'], source_rate) - offset)
        start_tick, end_tick = round(start * rate), round(end * rate)
        if start_tick < end_tick:
            markers.append(dict(marker, start_tick=start_tick, end_tick=end_tick))
    return markers
