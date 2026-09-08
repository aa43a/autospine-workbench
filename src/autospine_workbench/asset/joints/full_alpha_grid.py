"""Keep perceptible component eligibility; include all nonzero-alpha cells."""
from dataclasses import dataclass
from ...alpha_grid_mesh import build_alpha_grid_mesh,AlphaGridMeshError,_grid_edges,_active_cells,_vertices,_triangles
from ...mesh_topology import validate_mesh_topology,MeshTopologyError


@dataclass(frozen=True)
class SupportedGrid:
    vertices_xy: tuple
    triangles: tuple
    uvs: tuple


def build_supported_grid(image,step):
    build_alpha_grid_mesh(image,grid_step_px=step,alpha_threshold=8)
    cells=_active_cells(image,1,_grid_edges(image.width,step),_grid_edges(image.height,step))
    vertices=_vertices(cells);triangles=_triangles(cells,vertices)
    uvs=tuple((x/image.width,y/image.height) for x,y in vertices)
    try:validate_mesh_topology(vertices_xy=vertices,uvs=uvs,triangles=triangles,width_px=image.width,height_px=image.height)
    except MeshTopologyError as exc:raise AlphaGridMeshError(str(exc)) from exc
    return SupportedGrid(vertices,triangles,uvs)
