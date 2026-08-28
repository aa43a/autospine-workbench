# Kimodo `wave-left-v1` Pilot Handoff

本文是当前真实运行 pilot 的唯一身份记录，面向需要继续 P5/P9 的维护者。它固定
`wave-left-v1` 的六输入准入、P7 与 P8 exact 地址，避免 README、路线图和操作手册重复
抄写 SHA 后发生漂移。

## 已闭合的证据

| 项目 | SHA-256 |
| --- | --- |
| 原始 Kimodo NPZ | `9b3b9e991370538e48b139ba618bcd8f52502835689bd828df7068dc3fc6c582` |
| Pilot intake report | `95f65a78683ff6fbcea8644f15244f2e57d2d8d8e77b74503b84d501a19d8307` |
| P7 MotionIR | `f67a9e9beae9d1292c0bd16bcb03024692ea43179be4ceeaf4ca413690636a93` |
| P7 bundle | `7d564a7f26e4a21a8f7d1e85e0d3875a8996ce191e8f4eea56d65856a786451f` |
| P7 compile run | `5fd8378eccf199b59e16502a71045ccfaf2e8045b35d08b580f829c430bc35a9` |
| P8 ProjectedMotionIR | `24608181e658a188aa6e05e5639b1c511dd9ce7fafcbc56d074815ec9c3a3195` |
| P8 bundle | `0e0275f8508e291c4f21b851b8a515ba635b24429c348ed7f15c40dea3150634` |
| P8 compile run | `5f7d05000bec92a1b9535d7392f5a48c1e0d83d27d23e5b2589225346d57fdf2` |

六输入 intake 已得到 `eligible_for_p7_p8_compile`，随后 P7/P8 均已按上述 exact 地址发布并
通过各自 reader 复验。P8 的 collapsed sample 数为 `0`；全部已映射骨段的
`foreshortening_ratio` 范围为 `0.691123702`–`0.999703849`。

## 权限与质量边界

这份 handoff 只允许声明：该组 recorded 输入已经闭合、P7 结构编译与 exact replay 通过、
显式相机的 P8 投影与 exact replay 通过。它不授予或证明：

- 外部 checkpoint authenticity、模型或素材许可；
- 广泛动作集的质量验收，或目标角色上的视觉质量；
- A/B 任一目标 rig 的 P5 MotionInstance；
- P9 foot-lock/depth-order 人工决定或 reviewed-motion bundle；
- seam、官方 Spine Runtime、连续 raster 安全、publishable timeline 或 release authority。

intake report SHA 不是 P7/P8 bundle 地址；P7/P8 地址也不能作为 P9 reviewed-motion 地址填入
readiness 请求。任何输入、map、camera、compiler 或算法 profile 变化都必须生成新地址，不能
沿用本 handoff 的人工结论。

## 下一步

1. 为 `seethrough_output` 与 `seethrough_output_5` 分别从上述 P7 动作生成并复验 P5。
2. 用上述 P7/P8 与各目标 P5 生成 foot-lock/depth-order candidates。
3. 完成人工决定，发布并复验各项目的 P9 reviewed-motion bundle。
4. 只有取得各项目 P9 exact 地址后，才能继续回填 readiness 和后续 P10 链。
