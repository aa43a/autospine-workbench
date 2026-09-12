# 已确认的服装处理方向

用户确认“两项都确认”：

- 红美铃 `layer-011 topwear-front`、小恶魔 `layer-007 topwear-front` 刚性随 `chest`。
- 裙装 `bottomwear / bottomwear-front` 按腰部固定、裙摆独立辅助骨链开发可变形候选。

前片确认已经追加到项目绑定记录；逐条核对只有上述两行改变。
确切提案、前后来源和确认范围保存于 `benchmark/character-garment-confirmation-v1.json`。
候选 profile 补全保留全部旧绑定决定及原始图层，不构成视觉或发布授权。

裙装开发顺序：

1. 从实际 alpha、已复核 pelvis/hip 和图层位置产生腰部固定带候选；无有效接触时阻塞。
2. 为连续裙面产生左、中、右辅助链。前片与主裙分层保留；不能按名称把相邻附件合并。
3. 腰部顶点保持固定；下摆沿局部材料区域平滑分配辅助骨权重，不直接继承手或腿旋转。
4. 检查 setup 重建、权重归一化、面积和边长、腰部接缝、腿与裙面的遮挡。
5. 合入当前整角色候选的 idle、wave-left、walk，使用同帧官方 Runtime 检查；失败区域留在队列。

目前只是确认开发方向，尚未确认具体腰部锚点、权重、裙摆运动或视觉效果。
不将裙装临时刚性随 pelvis 当成可变形裙装里程碑完成。

前片候选补全会改变整份绑定候选地址。已新增残余排除范围重放 v2：必须保持原
resolved/semantic/skeleton 来源、该图层账本、完整骨架、slot、附件及纹理完全一致。
仅允许其他图层候选变化；范围重放记录原确认，不产生新的人工确认。
红美铃更新后包含 idle、wave-left、walk 的整角色包已通过 1,028 帧 Runtime，
证据见 `benchmark/character-garment-hongmeiling-v1.json`。

小恶魔更新后的完整动作组合已通过 1,675 帧官方 Runtime；前片仍为显式确认的
chest 绑定，腿部残余排除范围及原确认保持一致。证据见
`benchmark/character-garment-xiaoemo-motions-v1.json`。这恢复了三个固定角色的
idle / wave-left / walk 技术检查范围，不构成整角色视觉验收。
