"""Compare identical topology over identical dense elbow probes, without adoption."""
import math
from ...resolved_project import canonical_sha256
from .mesh_weights import _area,evaluate_mesh
from .elbow_alternatives import MODES, deform, validate_source


def evaluate(row, bones, mode):
    vertices, triangles, weights = row['vertices_xy'], row['triangles'], row['weights']
    evaluate_mesh(vertices,triangles,weights,bones)  # Validate topology, weights and finite coordinates.
    areas = [_area(vertices, tri) for tri in triangles]
    if not areas or any(abs(a) <= 1e-9 for a in areas):
        raise ValueError('elbow_comparison_degenerate_setup')
    edges = sorted({tuple(sorted((a,b))) for t in triangles for a,b in zip(t,t[1:]+t[:1])})
    lengths = [math.dist(vertices[a],vertices[b]) for a,b in edges]
    minimum, maximum, stretch, inversions, fraction = float('inf'), -float('inf'), 0., 0, 0.
    worst = None
    for angle in range(-90,91):
        moved = deform(vertices,weights,bones,angle,mode)
        ratios = [_area(moved,t)/area for t,area in zip(triangles,areas)]
        index = min(range(len(ratios)),key=ratios.__getitem__)
        if ratios[index] < minimum:
            minimum, worst = ratios[index], {'angle_degrees':angle,'triangle_index':index}
        maximum = max(maximum,max(ratios))
        inversions += sum(r <= 0 for r in ratios)
        fraction = max(fraction,sum(abs(a) for a,r in zip(areas,ratios) if r < .5)/sum(map(abs,areas)))
        stretch = max(stretch,max(math.dist(moved[a],moved[b])/length for (a,b),length in zip(edges,lengths)))
    setup = deform(vertices,weights,bones,0,mode)
    error = max(math.dist(p,q) for p,q in zip(vertices,setup))
    reasons = []
    for failed,reason in ((minimum < .5,'mesh_area_compression'),(maximum > 2,'mesh_area_expansion'),
                          (inversions > 0,'mesh_triangle_inversion'),(stretch > 2,'mesh_edge_stretch'),
                          (error > 1e-7,'mesh_setup_mismatch')):
        if failed: reasons.append(reason)
    return {'mode':mode,'status':'blocked' if reasons else 'passed','reason_codes':reasons,
            'min_area_ratio':minimum,'max_area_ratio':maximum,'max_edge_stretch':stretch,
            'inverted_triangle_samples':inversions,'max_compressed_setup_area_fraction':fraction,
            'setup_max_error':error,'worst':worst}


def build_comparison(mesh,skeleton):
    if mesh.get('profile') != 'joint-plane-three-bone-v2':
        raise ValueError('elbow_comparison_requires_joint_plane_profile')
    bones = {b['id']:b for b in skeleton['bones']}
    layers = []
    for row in mesh['layers']:
        result = {'layer_id':row['layer_id'],'status':'not_evaluated','reason_codes':['weighted_mesh_required'],'methods':[]}
        if row.get('weights'):
            chain = [bones[i['bone_id']] for i in row['weights'][0]]
            validate_source(row['vertices_xy'],row['weights'],chain)
            methods = [evaluate(row,chain,mode) for mode in MODES]
            result.update(status='compared',reason_codes=[],methods=methods)
        layers.append(result)
    return {'schema':'autospine.elbow-comparison/v1','profile':'elbow-alternatives-v1',
            'source_mesh_sha256':canonical_sha256(mesh),'source_skeleton_sha256':canonical_sha256(skeleton),
            'authority':'none','production_authorized':False,'threshold_status':'experimental_uncalibrated',
            'probe_range':[-90,90,1],'selected_method':None,
            'seam_status':'not_evaluated','runtime_status':'not_evaluated','layers':layers}


def validate_comparison(mesh,skeleton,document):
    if canonical_sha256(build_comparison(mesh,skeleton)) != canonical_sha256(document):
        raise ValueError('elbow_comparison_mismatch')
    return document
