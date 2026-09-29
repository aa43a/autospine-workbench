"""M5 stages reference the final bundle, while inherited body issues stay visible."""
import json


def append(files, digest, add):
    if 'joint-animation.json' not in files:
        return
    joint = json.loads(files['joint-animation.json'])
    if joint.get('skeleton_sha256') != digest:
        raise ValueError('joint_animation_readiness_identity_mismatch')
    preservation = joint.get('preservation', {})
    add('联合主动作保留', 'sampled_pass' if preservation.get('passed') is True else 'needs_changes',
        '身体骨骼与轨道保持原样；新增通道和既有服装修形分别核对。', 'joint-animation.json')
    face = joint['face']
    if joint['config']['face']['enabled']:
        add('基础表情', 'needs_changes' if face.get('missing') else 'sampled_pass',
            '眨眼、视线、眉毛及口型按当前素材生成；压缩闭眼和替换口型的外观仍需检查。',
            'joint-animation.json', missing=face.get('missing', []),
            actual_effects=face.get('enabled_effects', []))
    secondary = joint['secondary']
    if any(joint['config'].get(k, {}).get('enabled') for k in ('hair', 'cloth', 'objects')):
        good = secondary.get('status') == 'applied' and secondary.get('root_error_px', 1) <= 1e-7
        add('发束、裙袖与挂饰连接', 'sampled_pass' if good else 'needs_changes',
            '检查固定根、袖口边界和物件挂点；新增响应按几何和头身二维代理约束，不代表表面遮挡已通过。',
            'joint-animation.json', skipped=secondary.get('skipped', []),
            root_error_px=secondary.get('root_error_px'))
    loop = joint['loop']
    if loop.get('requested'):
        add('联合循环', 'sampled_pass' if loop.get('status') == 'passed' else 'needs_changes',
            '原身体、新增控制骨、显隐和整体接续分别检查；不会因新增摆动较平滑而撤销原动作的接缝。',
            'joint-animation.json', original_body_loop_ready=loop.get('source_body', {}).get('loop_ready'),
            added_effects_passed=loop.get('added_effects', {}).get('passed'))
    add('联合外观', 'unmeasured',
        '请在同一时间轴检查发眼、袖手和裙腿覆盖。技术数值检查不代替新增效果的阶段视觉验收。',
        'player.html')
