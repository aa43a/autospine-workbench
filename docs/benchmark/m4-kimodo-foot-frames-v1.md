# Kimodo 脚部姿态接入同视角适配

2026-09-22。原 `source_foot_orientation.extract` 只接受 BVH，导致完整视角及接触后鞋子朝向适配遇到 SOMA77 NPZ 时拒绝来源。NPZ 本身已有 foot_contacts → MotionIR 区间转换，本次不新增推断标签，也不将姿态观测当成脚底接触。

新增 NPZ 读取器：验证来源声明和映射，核对 local/global 旋转、root 与 posed_joints 的矩阵 FK 一致性，再重建全局脚部旋转。与 BVH 共用首帧相对旋转、带符号相机基、yaw 转换、角度展开及退化拒绝。NPZ 使用独立 `declared-kimodo-relative-foot-frame-v1` / `declared-kimodo-relative-foot-view-v1` 证据标识；BVH 原标识及计算保持。

已有 `motion_pose_policy.prepare` 和 `motion_view_pose.prepare(post_contact=True)` 自动调用此读取器。未修改默认动作策略、源动画、原始 NPZ、接触标签或历史候选。

## 实测范围

两份真实来源经过 VerifiedMotionBundleReader：

| 来源 | 任务 | 验证 |
| --- | --- | --- |
| Kimodo 生成 | motion-dc7dc44a65c74445bd87e1baaf81c6cf | 120 帧 × 0° / −45° / 45° |
| NPZ 导入 | motion-1261e0ce40754bf49bed2f8a16fefddb | 120 帧 × 0° / −45° / 45° |

执行 `tools/m4_foot_source_check.py`，报告位于 `localset/tmp/m4-motion-center/kimodo-foot-frames-v1/generated.json` 和 `imported.json`。脚部与姿态适配时间一致，MotionIR markers 未变，来源 motion 哈希未变。真实来源两脚的相对旋转较小，因此不代表大幅脚部旋转验证。

26 项测试通过，包括 NPZ 旋转父级继承、非零首帧相对角、跨 180° 连续展开、yaw 变换、全局矩阵不一致拒绝、投影平面退化拒绝，以及旧 BVH / 接触后适配回归。

这是来源准备的交付，尚不是目标角色或 Runtime 验收。下一步在独立角色候选上运行同视角鞋子朝向适配，核对脚踝位置、原标签保留、目标几何与官方 Runtime。无标签的 NPZ 不复用 BVH 推断器，也不宣称三种来源的全部接触策略已经对齐。
