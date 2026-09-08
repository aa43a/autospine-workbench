"""Common-frame review of fixed baseline deform versus bounded increments."""
from .continuous_anchor_view import render as common_render


def render(report):
    return (common_render(report).replace('continuous-raster/','increment-raster/')
            .replace('连续锚点 Bake 栅格对照','固定 deform 增量栅格对照')
            .replace('沿用原局部平滑求解器，仅替换可行组目标锚点。','保留固定原 deform，仅加入至多 2 px 的局部增量。')
            .replace('原局部重配','原连续锚点 Bake').replace('<figcaption>连续锚点 Bake','<figcaption>有界增量 Bake'))
