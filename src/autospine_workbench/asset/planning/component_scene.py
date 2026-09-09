"""Full-canvas visual context; pixel runs retain their layer-local coordinates."""
import base64
from html import escape
import math


def render_scene(layer, image, paths, scene):
    x, y, right, bottom = layer['bbox']
    if scene is None:
        return f'<svg viewBox="0 0 {right-x} {bottom-y}" role="group"><image href="data:image/png;base64,{image}" width="{right-x}" height="{bottom-y}"/><g opacity=".55">{paths}</g></svg>'
    width, height = scene['canvas']
    groups = []
    for bone in scene['bones']:
        a, b = bone['head_xy'], bone['tail_xy']
        if len(a) != 2 or len(b) != 2 or not all(math.isfinite(v) for v in a+b):
            raise ValueError('component_scene_invalid_bone')
        identifier = escape(bone['id'], quote=True)
        line = f'x1="{a[0]}" y1="{a[1]}" x2="{b[0]}" y2="{b[1]}"'
        groups.append(f'<g data-bone="{identifier}" style="cursor:pointer"><title>{identifier}</title>'
                      f'<line {line} stroke="transparent" stroke-width="16" vector-effect="non-scaling-stroke"/>'
                      f'<line data-visible="true" {line} stroke="#65d6ff" stroke-width="2" vector-effect="non-scaling-stroke"/>'
                      f'<circle cx="{a[0]}" cy="{a[1]}" r="3" fill="#65d6ff"/>'
                      f'<text x="{a[0]+5}" y="{a[1]-5}" fill="#ffdf88" font-size="16" style="display:none">{identifier}</text></g>')
    background = base64.b64encode(scene['composite']).decode('ascii')
    return f'''<svg viewBox="0 0 {width} {height}" role="group" aria-label="区域与全部骨骼画布">
<image href="data:image/png;base64,{background}" width="{width}" height="{height}" opacity=".3"/>
<image href="data:image/png;base64,{image}" x="{x}" y="{y}" width="{right-x}" height="{bottom-y}"/>
<g transform="translate({x} {y})" opacity=".55">{paths}</g>{''.join(groups)}</svg>'''
