# 材质切换的遮挡采样

2026-09-23。遮挡 Probe 现在支持材质候选使用的二值 stepped slot alpha。
切入时刻包含、切出时刻不包含；首关键帧之前遵循 setup alpha。
不支持的 attachment/color 轨道、非二值透明度及非法时间仍返回未测量错误，不能当作没有遮挡。

验证：`test_depth_slot_visibility` 与 `test_motion_depth_overlap` 共 10 项通过。
真实不可变候选 `9c627a5e3278e841ca69ce59ad8ca6bf44506b24c43e93b7d7b88e42edd40a5f`，
external-motion 的 layer-004-material-original/replacement，在 CPU 原生像素中心采样：

| 秒 | 原图可见像素 | 替换图可见像素 | 两图共同可见像素 |
| --- | --- | --- | --- |
| 0.9999 | 60 | 0 | 0 |
| 1 | 0 | 60 | 0 |
| 1.9999 | 0 | 62 | 0 |
| 2 | 62 | 0 | 0 |

另一个单三角形候选 4363d1ddfbdf86eb252e9cc400df64cdd8b69eb52ca7e767010e902c586a2db1
未满足“可见图块必有非零 alpha 像素”的实验断言，不能以它证明非零可见覆盖；未修改该候选。

这是 CPU overlap 能力扩展，不是 GPU 重捕获或整段遮挡验收。
修复 worker 的 depth_order_status 仍为 not_evaluated；下一步仍需重新建立修复产物的深度来源及区域映射，不能沿用父候选通过状态。
