"""SOMA77 length projection uses validated NPZ positions, never fabricated BVH."""
import math

from ...kimodo_npz_reader import decode_kimodo_npz
from ...kimodo_npz_consistency import validate_kimodo_consistency
from ...kimodo_npz_projection import kimodo_frame_ticks
from ...kimodo_npz_map_validation import require_kimodo_npz_map, kimodo_npz_map_sha256
from ...kimodo_npz_source import kimodo_npz_source_sha256
from ...kimodo_soma77 import SOMA77_INDEX_BY_NAME
from .motionir_candidate import ROLES
from .projected_lengths import apply_ratios


def build(document, name, raw, source, mapping):
    require_kimodo_npz_map(mapping, source=source)
    validated = validate_kimodo_consistency(decode_kimodo_npz(raw, source), source)
    axes = ['XYZ'.index(mapping['basis'][key][1]) for key in ('screen_x', 'screen_y')]
    ratios, summary = {}, []
    for row in mapping['bones']:
        if not row['role'].startswith(('humanoid.leg.', 'humanoid.arm.')):
            continue
        values = []
        a_index, b_index = (SOMA77_INDEX_BY_NAME[row[k]] for k in ('joint_name', 'aim_joint_name'))
        for frame in validated.positions:
            a, b = frame[a_index], frame[b_index]
            world = math.dist(a, b)
            visible = math.sqrt(sum((a[i]-b[i])**2 for i in axes))
            if world <= 1e-8 or visible/world < .2:
                raise ValueError('character_length_projection_collapsed')
            values.append(visible/world)
        values = [v/values[0] for v in values]
        if min(values) < .5 or max(values) > 1.5:
            raise ValueError('character_length_ratio_outside_preview_range')
        bone = ROLES[row['role']]
        ratios[bone] = values
        summary.append(dict(role=row['role'], bone=bone, min_ratio=min(values), max_ratio=max(values)))
    return apply_ratios(document, name, ratios, summary,
                        [tick/1_000_000 for tick in kimodo_frame_ticks(source)],
                        kimodo_npz_source_sha256(source), kimodo_npz_map_sha256(mapping))
