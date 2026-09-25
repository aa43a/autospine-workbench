"""Aggregate exact candidate evidence without treating execution as acceptance."""
from hashlib import sha256
import json


def build(files, artifact_sha256, runtime=None):
    def read(name):
        return json.loads(files[name]) if name in files else {}
    motion = read('motion-review.json'); geometry = read('deformation.json')
    contact = read('motion-contact.json'); depth = read('motion-depth.json')
    digest = sha256(files['skeleton.json']).hexdigest()
    for evidence in (geometry, depth):
        if evidence and evidence.get('skeleton_sha256') != digest:
            raise ValueError('motion_readiness_skeleton_mismatch')
    if runtime and runtime.get('bundle_sha256') != artifact_sha256:
        raise ValueError('motion_readiness_runtime_mismatch')
    rows = []
    def add(stage, status, explanation, href, **extra):
        rows.append(dict(stage=stage, status=status, explanation=explanation, href=href, **extra))
    projection = [i for i in motion.get('issues', []) if i['stage'] == 'projection']
    torso = read('motion-torso-projection.json')
    if torso:
        if torso.get('skeleton_sha256') != digest:raise ValueError('motion_readiness_torso_identity_mismatch')
        add('躯干投影','sampled_pass' if torso.get('applied') is True else 'needs_changes',
            '实验性网格烘焙；头部与手臂作形状补偿，骨骼辅助线不随烘焙移动。侧背面素材和视觉效果仍需检查。',
            'motion-torso-projection.json',applied=torso.get('applied'))
    pose = motion.get('source_pose_fit', {})
    unreliable = [dict(bone=row['bone'], **frame) for row in pose.get('records', [])
                  for frame in row.get('unreliable_frames', [])]
    pose_measured = bool(pose.get('records')) and all(
        'unreliable_frames' in row for row in pose['records'])
    add('投影', 'needs_changes' if projection or unreliable else
        'sampled_pass' if motion.get('projected_lengths') or pose_measured else 'unmeasured',
        '源骨段接近朝向镜头，二维方向不可靠；查看标记时间，不应仅靠旋转平滑隐藏。' if unreliable else
        '当前视角存在缩短或塌缩异常，请切换源视角或截取片段后重新构建。' if projection else
        '只说明已实施的骨段投影检查；不代表具有侧面或背面贴图。',
        'player.html' if unreliable else '/motions.html',
        reasons=[i['reason_code'] for i in projection],
        unreliable_frames=unreliable, pose_profile=pose.get('target_profile'),
        failures=[dict(time=f['time'], bone=f['bone'], reason='source_projection_unreliable') for f in unreliable])
    failed = [r for r in geometry.get('records', []) if not r['passed']]
    add('几何', 'sampled_pass' if geometry.get('passed') is True else 'needs_changes' if geometry else 'unmeasured',
        f'{len(failed)} 个附件动作记录超限；按失败时间检查。' if failed else '采样网格检查，不是连续时间证明。',
        'player.html', failures=[dict(slot=r['slot'], animation=r['animation'],
                                     time=r['first_failure']['time']) for r in failed if r.get('first_failure')])
    state = contact.get('status')
    moving = read('motion-moving-ankles.json')
    if moving or motion.get('moving_ankles'):
        checked = moving.get('final_check', {})
        if checked and checked.get('skeleton_sha256') != digest:
            raise ValueError('motion_readiness_moving_ankle_identity_mismatch')
        moving_status = ('unmeasured' if not moving or not checked else
            'sampled_pass' if moving.get('applied') is True and checked.get('passed') is True else 'needs_changes')
        worst = checked.get('worst', {})
        failure_time = moving.get('failure', {}).get('time') if moving.get('failure') else worst.get('time')
        add('脚端轨迹', moving_status,
            '检查跟随源脚端的最终采样误差；与静止接触、鞋底接地和视觉验收分别判断。',
            'motion-review.json', applied=moving.get('applied'), final_check=checked,
            failures=[dict(time=failure_time,reason='moving_ankle_failed')] if moving_status=='needs_changes' else [])
    passed = state in ('ankle_proxy_passed', 'ankle_proxy_corrected', 'inferred_proxy_passed', 'inferred_proxy_corrected')
    add('接触', 'sampled_pass' if passed else 'needs_changes' if state in ('needs_changes', 'inferred_proxy_drift') else 'unmeasured',
        '仅检查源标签或推断区间的踝部支点；不证明鞋底接地。', 'contact.html', evidence_status=state)
    order = depth.get('order', {}); failures = order.get('failures', [])
    # A blocked order or missing overlap evidence cannot become a green stage
    # simply because the document retained its original drawing order.
    depth_failed = bool(failures) or bool(depth.get('target_overlap', {}).get('ambiguous_visible_pair_samples'))
    depth_passed = ((order.get('status') == 'no_visible_order_change'
                     or order.get('status') == 'candidate' and depth.get('selected') is True)
                    and not depth.get('target_overlap', {}).get('unmeasured_pair_samples', 1))
    depth_state = 'needs_changes' if depth_failed else 'sampled_pass' if depth_passed else 'unmeasured'
    if depth.get('profile') == 'external-regional-depth-order-v1':
        from .regional_depth_gate import evaluate
        depth_state = evaluate(files, depth)
    add('遮挡', depth_state,
        '顺序约束未通过，保留原动画；查看冲突位置。' if depth_failed else
        '手臂/躯干与受影响顺序的采样检查；整角色视觉遮挡仍需复核。',
        'depth.html', failures=[dict(time=f['time'], reason=f['reason_code']) for f in failures[:20]])
    add('Runtime', 'sampled_pass' if runtime and runtime.get('passed') is True and runtime.get('results') else 'needs_changes' if runtime else 'unmeasured',
        '官方捕获的顶点数值与画面边界检查；不代替几何、接触或视觉验收。', 'player.html',
        frames=len(runtime.get('results', [])) if runtime else 0)
    other = [i for i in motion.get('issues', []) if i['stage'] not in ('projection', 'geometry', 'contact')]
    if other:
        refinement = motion.get('post_contact_repair', {}).get('correction', {}).get('refinement', [])
        residual = refinement[-1].get('check', {}).get('failures', []) if refinement else []
        add('其他修正', 'needs_changes', '局部修正仍有未解决问题。', 'player.html',
            reasons=[i['reason_code'] for i in other],
            failures=[dict(time=r['time'],slot=r['slot'],reason='post_contact_constraint_failed') for r in residual])
    status = ('needs_changes' if any(r['status'] == 'needs_changes' for r in rows) else
              'evidence_incomplete' if any(r['status'] == 'unmeasured' for r in rows) else 'stage_review')
    return dict(profile='external-motion-readiness-v1', artifact_sha256=artifact_sha256,
                skeleton_sha256=digest, status=status, stages=rows, authority='none',
                human_visual_acceptance='not_recorded_here', production_authorized=False,
                scope='implemented_sampled_checks_only_not_arbitrary_motion_support')
