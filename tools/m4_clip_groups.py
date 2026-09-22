"""Group adjacent triangles only when one plane reproduces all sampled depths."""
import numpy as np


def group(points, values, triangles, selected, tolerance=1e-7, *, pixel_tolerance=None):
    points = np.asarray(points, dtype=float); values = np.asarray(values, dtype=float)
    triangles = np.asarray(triangles, dtype=int)
    planes = {}
    for index in selected:
        tri = triangles[index]
        matrix = np.concatenate((points[:, tri], np.ones((len(points), 3, 1))), axis=2)
        planes[int(index)] = np.linalg.solve(matrix, values[:, tri, None])[..., 0]
    remaining = set(int(i) for i in selected); groups = []
    while remaining:
        seed = min(remaining); remaining.remove(seed)
        members = [seed]; vertices = set(triangles[seed]); frontier = [seed]
        plane = planes[seed]
        while frontier:
            index = frontier.pop()
            for other in sorted(remaining):
                if len(set(triangles[index]) & set(triangles[other])) != 2:
                    continue
                used = triangles[other]
                predicted = np.einsum('fi,fvi->fv', plane[:, :2], points[:, used]) + plane[:, 2, None]
                error = np.max(np.abs(predicted-values[:, used]), axis=1)
                if pixel_tolerance is None:
                    if error.max() > tolerance: continue
                else:
                    same_side = (((predicted >= 0).all(axis=1) & (values[:, used] >= 0).all(axis=1)) |
                                 ((predicted < 0).all(axis=1) & (values[:, used] < 0).all(axis=1)))
                    gradient = np.minimum(np.linalg.norm(plane[:, :2], axis=1),
                                          np.linalg.norm(planes[other][:, :2], axis=1))
                    if np.any((~same_side) & ((gradient <= 1e-12) | (error > gradient*pixel_tolerance))):
                        continue
                members.append(other); remaining.remove(other)
                vertices.update(triangles[other]); frontier.append(other)
        groups.append(members)
    return groups
