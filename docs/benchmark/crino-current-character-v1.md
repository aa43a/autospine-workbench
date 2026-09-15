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

## walk 接入

复用固定角色集 MotionIR `fa8b2c22c273ae82d146efc0cf584c50b2bac44f05588cf7ed213f3d56955134`
及原 motion bundle `b0793dc9b5e541f601cfa915067b024a6cf02868e03bb9258621bf6da62a2b85`，
使用 513 个 walk 数值样本、投影长度、有界 v2 面积修正及踝点代理根修正，未按角色调参。

- walk 候选：`08958a1c4762aec6b3a74ace226c880c4069c693f23adb154aa2e4b21104d7c4`。
- 工作台动作选择：`dd78baa2256fb11f38f051373c7830bdde1eaee9611511ac1aaa5c6981781325`。
- 新任务：`job-f9738d49728f41819ae6355cd8902035`。
- 整角色输出：`0e645c692c1a5786e9890ff9269d5405f599ceb58e9a679c6b681abf58cb6d7d`。
- 官方 Runtime 1,028 帧，几何 passed。保留原 idle、wave-left 和 limb-flex-15。

踝点代理不等于鞋底锁定，toe anchor 仍不可用。绑定缺项未因加入动作而消失。

旧候选静态区域扫描证明 layer-003-residual / layer-005-residual / layer-006-residual
分别有 3,709 / 8,188 / 464 个非零 alpha 像素，alpha ≥ 8 均为 0。
扫描没有删除素材，也没有写入人工确认。下一步接入独立可撤销的系统默认残余策略。

## 低透明度残余默认处理

`low-alpha-residual-v1` 已处理以上三处残余，共 12,361 个非零 alpha 像素。
原纹理字节和有效网格动作保留；取消整角色构建中的默认隐藏选项并重建可恢复。

- 任务：`job-6169643bacfe44e7ab68905cff9a5e24`。
- 输出：`dd86719985d88ab067b99ff180cde0b71272d03f9242dea32ed5e1a5bbda23e9`。
- 原输出：`0e645c692c1a5786e9890ff9269d5405f599ceb58e9a679c6b681abf58cb6d7d`。
- 官方 Runtime 1,028 帧，四动作几何通过，失败记录 0。
- 腿和鞋两层符合既有加权默认策略，记录系统采用；双臂合层仍保留绑定异常。
- 六个静态参考层仍待归属，整角色视觉验收未完成，不计入完成角色数。

验证：相关 Python 45 项、Web 594 项通过。系统处理不代表人工视觉确认或发布授权。
