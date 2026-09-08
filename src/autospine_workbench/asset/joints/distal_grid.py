"""Conforming axis strips near distal joints; preserve full-alpha support."""
from copy import deepcopy
import hashlib
import math

from ...alpha_grid_mesh import (build_alpha_grid_mesh,
    _grid_edges, _active_cells, _vertices, _triangles)
from ...mesh_topology import validate_mesh_topology
from ...png_rgba import decode_rgba_png
from ...resolved_project import canonical_sha256
from .full_alpha_grid import SupportedGrid
from .joint_plane_weights import weights_for_vertices
from .partition_mesh_qa import evaluate, raster_support

PROFILE = 'partition-distal-axis-support-v1'


def refined_edges(extent, step, center, length):
    if not all(math.isfinite(v) for v in (center, length)) or length <= 0:
        raise ValueError('distal_grid_joint_invalid')
    spacing = max(1, math.floor(length / 4))
    low = max(0, math.floor(center - length))
    high = min(extent, math.ceil(center + length))
    extra = range(low, high + 1, spacing) if low <= high else ()
    return tuple(sorted(set(_grid_edges(extent, step)) | set(extra) |
                        ({high} if low <= high else set())))


def build_grid(image, step, pivot, length):
    # Eligibility is unchanged; even faint disconnected pixels retain support.
    build_alpha_grid_mesh(image, grid_step_px=step, alpha_threshold=8)
    xs = refined_edges(image.width, step, pivot[0], length)
    ys = refined_edges(image.height, step, pivot[1], length)
    cells = _active_cells(image, 1, xs, ys)
    vertices = _vertices(cells); triangles = _triangles(cells, vertices)
    uvs = tuple((x / image.width, y / image.height) for x, y in vertices)
    validate_mesh_topology(vertices_xy=vertices, uvs=uvs, triangles=triangles,
                          width_px=image.width, height_px=image.height)
    return SupportedGrid(vertices, triangles, uvs)


def refine(mesh, candidate, skeleton, images):
    if (mesh.get('profile') != 'partition-full-alpha-supported-v2' or
            mesh['source_skeleton_sha256'] != canonical_sha256(skeleton)):
        raise ValueError('distal_grid_source_mismatch')
    result = deepcopy(mesh)
    result.update(profile=PROFILE, source_mesh_sha256=canonical_sha256(mesh))
    result.pop('distal_trials', None)
    sources = {r['layer_id']: r for r in candidate['layers']}
    bones = {b['id']: b for b in skeleton['bones']}
    for row in result['layers']:
        if len(row['bone_ids']) != 3:
            continue
        raw = images[row['layer_id']]
        if hashlib.sha256(raw).hexdigest() != row['image_sha256']:
            raise ValueError('distal_grid_image_mismatch')
        image = decode_rgba_png(raw)
        x, y, right, bottom = sources[row['layer_id']]['bbox']
        if (image.width, image.height) != (right-x, bottom-y):
            raise ValueError('distal_grid_dimensions_invalid')
        chain = [bones[b] for b in row['bone_ids']]
        length = min(math.dist(b['head_xy'], b['tail_xy']) for b in chain[-2:])
        pivot = [chain[2]['head_xy'][0]-x, chain[2]['head_xy'][1]-y]
        grid = build_grid(image, max(4, math.ceil(max(image.width, image.height)/32)), pivot, length)
        vertices = [[a+x, b+y] for a, b in grid.vertices_xy]
        triangles = [list(t) for t in grid.triangles]
        weights = weights_for_vertices(vertices, chain)
        qa = evaluate(vertices, triangles, weights, chain)
        raster = raster_support(image.pixels[3::4], image.width, image.height, vertices, triangles, (x,y))
        reasons = ['distal_axis_support', 'binding_not_adopted']
        if not qa['passed']: reasons.append('partition_deformation_qa_failed')
        if raster['uncovered_alpha_pixels']: reasons.append('partition_raster_support_incomplete')
        row.update(vertices_xy=vertices, triangles=triangles, weights=weights,
                   uvs=[list(uv) for uv in grid.uvs], qa=qa, raster_qa=raster,
                   reason_codes=reasons, status='candidate_requires_review' if len(reasons)==2 else 'blocked')
    return result
