"""Reuse common-frame layout with explicit comparison labels for this experiment."""
from .continuous_anchor_view import render as common_render


def render(report):
    return (common_render(report).replace('continuous-raster/','shape-raster/')
            .replace('连续锚点 Bake 栅格对照','局部形状约束栅格对照')
            .replace('沿用原局部平滑求解器，仅替换可行组目标锚点。','增加切向位移约束，并在帧内检查面积与拉伸。')
            .replace('原局部重配','原连续锚点 Bake').replace('<figcaption>连续锚点 Bake','<figcaption>形状约束 Bake'))
