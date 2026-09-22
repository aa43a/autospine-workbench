"""SOMA77 foot frames from cross-checked local/global matrix evidence."""
from ...kimodo_npz_reader import decode_kimodo_npz
from ...kimodo_npz_consistency import validate_kimodo_consistency, _global_frame
from ...kimodo_npz_map_validation import require_kimodo_npz_map
from ...kimodo_npz_projection import kimodo_frame_ticks
from ...kimodo_soma77 import SOMA77_INDEX_BY_NAME


def read(bundle, mapping):
    require_kimodo_npz_map(mapping, source=bundle.kimodo_source)
    snapshot = decode_kimodo_npz(bundle.raw_npz, bundle.kimodo_source)
    validate_kimodo_consistency(snapshot, bundle.kimodo_source)
    # Reconstruct from the admitted hierarchy, not unchecked global matrices.
    poses = [_global_frame(snapshot.arrays, frame)[0] for frame in range(snapshot.frame_count)]
    return poses, SOMA77_INDEX_BY_NAME, [t/1e6 for t in kimodo_frame_ticks(bundle.kimodo_source)]
