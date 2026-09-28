"""Separate near-contact, interval width and overlapping-surface depth evidence."""
def inspect(ambiguous,al,ah,aw,bl,bh,bw):
    def count(mask):return int((ambiguous&mask).sum())
    separated=(al>bh)|(bl>ah)
    return dict(separated_within_margin=count(separated),overlapping_intervals=count(~separated),
        a_intrinsic_interval=count(aw>1e-10),b_intrinsic_interval=count(bw>1e-10),
        a_multiple_surface_span=count(ah-al>aw+1e-10),
        b_multiple_surface_span=count(bh-bl>bw+1e-10))
