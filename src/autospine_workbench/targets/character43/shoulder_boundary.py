"""Source-supported proximal boundary constraints for shoulder trials."""
from collections import Counter
import math

from .affine_pose import matrices
from .skirt_candidate import inverse
from ...asset.planning.cloth_shape_constraints import refine
from ...asset.planning.component_local_solver import metrics


def prepare(points, triangles, contact, root, distal):
    """Pin only the proximal contact-facing mesh boundary; leave distal vertices fixed."""
    length = math.dist(root, distal)
    if not math.isfinite(length) or length <= 0 or not contact:
        raise ValueError('shoulder_boundary_reference_invalid')
    edge_counts = Counter(tuple(sorted((a, b))) for tri in triangles for a, b in zip(tri, tri[1:]+tri[:1]))
    edges = sorted(edge_counts)
    lengths = sorted(math.dist(points[a], points[b]) for a, b in edges)
    spacing = lengths[len(lengths)//2]
    if spacing <= 0: raise ValueError('shoulder_boundary_degenerate')
    boundary = sorted({v for edge, count in edge_counts.items() if count == 1 for v in edge})
    axis = [(distal[k]-root[k])/length for k in (0, 1)]
    projection = [sum((p[k]-root[k])*axis[k] for k in (0, 1)) for p in points]
    supported = [v for v in boundary if min(math.dist(points[v], p) for p in contact) <= spacing]
    if not supported: raise ValueError('shoulder_boundary_contact_missing')
    proximal = min(projection[v] for v in supported)
    pins = [v for v in supported if projection[v] <= proximal+spacing]
    if len(pins) < 2: raise ValueError('shoulder_boundary_support_insufficient')
    free = [v for v in range(len(points)) if v not in pins and projection[v] < proximal+.8*length]
    if not free: raise ValueError('shoulder_boundary_free_region_missing')
    return dict(pins=pins, free=free, spacing_px=spacing, upperarm_length=length,
                proximal_projection_px=proximal, budget_px=length*.75)


def solve(document, animation, time, points, triangles, world, context):
    setup_matrix = matrices(dict(document, animations={'setup': {}}), 'setup', 0)['chest']
    current = matrices(document, animation, time)['chest']
    a, b, c, d, x, y = current
    fixed = [list(p) for p in world]
    for vertex in context['pins']:
        u, v = inverse(setup_matrix, points[vertex])
        fixed[vertex] = [a*u+b*v+x, c*u+d*v+y]
    corrected, evidence = refine(points, triangles, fixed, context['free'], world, seed=world)
    moved = max(math.dist(a, b) for a, b in zip(corrected, world, strict=True))
    quality = metrics(points, corrected, triangles)
    evidence.update(geometry=quality, displacement_from_original_px=moved,
                    within_budget=moved <= context['budget_px']+1e-7)
    return corrected, evidence
