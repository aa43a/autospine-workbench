# 脚端跟随关键帧时间兼容性

2026-09-28。红美铃正面拳击候选的官方捕获在启动 Runtime 前被
`runtime_storage_key_times_collapsed` 阻止。该次失败不是 Runtime 验证通过。

## 原因与修复

脚端跟随阶段此前使用 Python 浮点集合合并源帧、已有动画关键帧和检查采样。
例如 `0.21484375` 与 `0.21484375000000003` 在集合中不同，
但 Runtime 的 Float32 时间数组不能区分，导致新增的根骨平移和双腿旋转轨道重复。

现在在求解前按 Runtime 可表示的时刻分组；只有计算舍入量级的别名可以合并。
保留源时间优先，并记录 `merged_time_aliases`。真正不同的事件即使存储后重合，
仍以 `moving_ankle_distinct_times_collide_in_runtime` 拒绝，不静默删键。
原始素材、已有候选、几何门槛及 Runtime 重复时间检查保持不变。

后续补强：不同的源观测帧绝不合并，即使两者时间差处于舍入量级。
这些帧可能携带不同的姿态，不能将它们当作重复采样。新增反例使用相邻的
双精度时间值，确认其发生 Float32 冲突时明确拒绝；相关测试共 22 项通过。
正在运行的真实拳击重建仍使用前一修订；其固定 30fps 来源无此类观测碰撞，
本次补强不改变该来源的时间集合。

## 验证与边界

21 项测试通过：`test_moving_ankle_candidate`、`test_motion_moving_ankles`、
`test_runtime_storage_reference`。回归覆盖输出时间转成 Float32 后严格递增、
源端点优先、输入不变及真实事件碰撞拒绝。

真实候选重建目录为 `tmp/m4-boxing-front-pose-time-v2`（workspace 根目录下）。
记录本文时重建仍在运行，尚无新 Runtime 或视觉通过结论。
旧 `m4-boxing-front-pose-v1` 的脚端跟随通过不能抵消其右臂翻转、
其他部件压缩及近相机方向不可靠问题；本修复仅处理时间兼容性。
