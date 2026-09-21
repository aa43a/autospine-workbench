"""Whole-clip sampled repair footprint, with a separate source-based verifier."""
from .area_preservation import outside_repair_band
from .affine_pose import sample, matrices
from .projected_area_reference import reference
from ..spine43.continuous_pose import area


def collect(worlds, slot, triangles, frame_areas, support):
    band=set()
    for world,refs in zip(worlds,frame_areas):
        _,current=outside_repair_band(world[slot],triangles,refs,support_vertices=support)
        band.update(current)
    return sorted(band)


def verify(source, name, times, prepared, rest, support, expected):
    # Reconstruct from the uncorrected source, never from deformed output.
    actual={slot:set() for slot in prepared}
    for time in times:
        world=sample(source,name,time)[0];transform=matrices(source,name,time)
        for slot,(triangles,areas,influences) in prepared.items():
            refs=reference(areas,triangles,influences,source['bones'],rest,transform)
            vertices=set(support[slot])
            for tri,ref in zip(triangles,refs):
                if not .5<=area(world[slot],tri)/ref<=2:vertices.update(tri)
            actual[slot].update(i for i,tri in enumerate(triangles) if vertices.intersection(tri))
    if {k:sorted(v) for k,v in actual.items()}!=expected:
        raise ValueError('fixed_repair_band_source_mismatch')
    return actual
