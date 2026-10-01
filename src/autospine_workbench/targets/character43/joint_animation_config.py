"""Versioned, source-independent controls for a baked M5 animation."""
from copy import deepcopy
import math

SCHEMA = 'autospine.joint-animation-config/v1'
PROFILE = 'joint-face-hair-cloth-follow-v2'


def defaults(*, wind=True):
    from . import joint_face, joint_secondary
    from .joint_wind import defaults as wind_defaults
    secondary = joint_secondary.defaults(wind=wind)
    return dict(schema=SCHEMA, seed=0, fps=30, loop=False,
                face=joint_face.defaults(), hair=secondary['hair'], cloth=secondary['cloth'], objects=secondary['objects'],
                **({'wind':wind_defaults()} if wind else {}))


def normalize(value, duration):
    from . import joint_face, joint_secondary
    if not isinstance(value, dict) or set(value) - {'schema', 'seed', 'fps', 'loop', 'face', 'hair', 'cloth', 'objects', 'wind'}:
        raise ValueError('joint_animation_config_invalid')
    result = defaults(wind='wind' in value)
    result.update(deepcopy(value))
    if result['schema'] != SCHEMA or type(result['loop']) is not bool:
        raise ValueError('joint_animation_config_invalid')
    if type(result['seed']) is not int or not 0 <= result['seed'] <= 2147483647:
        raise ValueError('joint_animation_seed_invalid')
    if type(result['fps']) is not int or result['fps'] not in (24, 30, 60):
        raise ValueError('joint_animation_fps_invalid')
    if not math.isfinite(duration) or not 0 < duration <= 120:
        raise ValueError('joint_animation_duration_invalid')
    result['face'] = joint_face.normalize(result['face'], duration)
    secondary = joint_secondary.normalize(dict(hair=result['hair'], cloth=result['cloth'], objects=result['objects'], loop=result['loop'],
        **({'wind':result['wind']} if 'wind' in value else {})), duration)
    for group in ('hair', 'cloth', 'objects'): result[group] = secondary[group]
    if 'wind' in value:
        result['wind'] = secondary['wind']
    else:
        result.pop('wind', None)  # Preserve frozen pre-wind jobs and their checksums.
    return result


def controls():
    rows = []
    def add(group, key, label, low=None, high=None, step=None, channel=None):
        row = dict(group=group, key=key, label=label, type='boolean' if low is None else 'number')
        if low is not None:
            row.update(min=low, max=high, step=step)
        if channel:
            row.update(animatable=True, channel=channel)
        rows.append(row)
    add('face', 'enabled', '面部动画')
    add('face', 'mouth.template_enabled', '使用基础开口模板（程序绘制）')
    for channel, label in [('blink', '眨眼'), ('gaze', '视线'), ('brows', '眉毛'), ('mouth', '口型'), ('turn', '小幅五官转向')]:
        add('face', channel+'.enabled', label, channel='blink' if channel == 'blink' else None)
    for key, label, lo, hi, step in [('period', '眨眼间隔 / 秒', .5, 20, .1),
                                    ('duration', '闭合周期 / 秒', .08, .8, .01),
                                    ('phase', '首次眨眼 / 秒', 0, 60, .1)]:
        add('face', 'blink.'+key, label, lo, hi, step)
    for channel, fields in [('gaze', [('x', '视线左右'), ('y', '视线上下')]),
                            ('brows', [('lift', '眉毛抬起'), ('tilt', '眉毛倾斜')]),
                            ('mouth', [('open', '张口'), ('wide', '嘴型宽度')]),
                            ('turn', [('yaw', '五官左右'), ('pitch', '五官上下')])]:
        for key, label in fields:
            add('face', channel+'.'+key, label, 0 if key == 'open' else -1, 1, .05, channel)
    for group, label in [('hair', '发束'), ('cloth', '裙袖'), ('objects', '挂饰与物件')]:
        add(group, 'enabled', label+'响应')
        add(group, 'strength', label+'强度', 0, 2, .05)
        add(group, 'stiffness', '回弹刚度', 9, 100, 1)
        add(group, 'damping', '阻尼比', .3, 2, .05)
        add(group, 'max_angle', '摆动上限 / 度', 0, 10, .5)
        add(group, 'wind_response', label+'受风系数', 0, 2, .05)
    add('wind', 'enabled', '启用风场')
    add('wind', 'strength', '风强', 0, 100, 1)
    add('wind', 'direction', '吹向 / 度（0 向右，90 向上）', 0, 360, 1)
    add('wind', 'gust', '阵风强度', 0, 1, .05)
    add('wind', 'frequency', '阵风变化 / Hz', 0, 4, .05)
    add('wind', 'seed', '阵风种子', 0, 2147483647, 1)
    add('hair', 'root_fraction', '固定发根比例', .15, .75, .05)
    add('hair', 'cascade', '发梢跟随上游发束（级联惯性）')
    add('objects', 'anchor_x', '挂点横向比例（父骨坐标）', 0, 1, .05)
    add('objects', 'anchor_y', '挂点纵向比例（0 下端 / 1 上端）', 0, 1, .05)
    return rows
