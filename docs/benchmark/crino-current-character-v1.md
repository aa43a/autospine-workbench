# 琪露诺当前版本整角色候选

2026-09-15：使用当前已登记 PSD 项目
`imported-9457d50ec689ef628e347db4125bbc4926192f0dbdcbc361d17fd9f1b00ec2c0`。
保留旧 crino 项目及历史证据。

双臂合在一个 bilateral 图层，几何路线检查返回 `character_side_unknown`。
按用户要求的默认流程，使用 `combined-arm-preview-first-v1` 进入普通候选构建；
这只决定运行路线，不自动批准合层归属，也不推断角色无袖。

- 任务：`job-e7575c4c070b4ba5afc6238650384737`。
- 输出：`03ff5c58bbb9235d0150710bb29fdd909dbf0c9e24d44a7d0c4f38ed62ce42b0`。
- 官方 Runtime 515 帧，几何 passed。
- 18 个源层：8 rigid_reviewed、3 partial、6 static_reference、1 not_visible。
- 当前动画：idle、limb-flex-15、wave-left；必需 walk 仍缺失。

尚未完成整角色验收。接下来处理部分覆盖与静态参考归属，再补 walk 和阶段视觉验收。
不能把播放成功或默认路线计为绑定完成。
