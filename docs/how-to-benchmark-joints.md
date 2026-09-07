# PSD 关节点录入

此入口在已经核验的 PSD 合成图上记录17个关节点草稿：root、pelvis、chest、neck、head，
以及双侧 shoulder、elbow、wrist、hip、knee、ankle。初始全部未标注，不根据 bbox 猜点。
侧别指角色自身左右。坐标以 PSD 画布左上角为原点，X向右、Y向下，单位为像素。

```powershell
$env:PYTHONPATH = (Resolve-Path ./src).Path
python -m autospine_workbench.benchmark joint-review --manifest docs/benchmark/manifest-frozen-v1.json --evidence docs/benchmark/development-audit-2026-09.json --workspace .. --character crino.psd --html ../tmp/benchmark-joints/crino-v1.html --output ../tmp/benchmark-joints/crino-pending-v1.json
```

选择关节后在图上点击录入，可清除或明确设为不可观测并填写原因。未标注与不可观测
是不同状态；不可观测不会自动补成对称点。草稿下载后可在同一页面恢复，或通过
`--draft` 精确验证后生成新页面：

```powershell
python -m autospine_workbench.benchmark joint-review --manifest docs/benchmark/manifest-frozen-v1.json --evidence docs/benchmark/development-audit-2026-09.json --workspace .. --character crino.psd --draft joint-draft.json --html ../tmp/benchmark-joints/crino-edited.html --output ../tmp/benchmark-joints/crino-edited.json
```

CLI 重验原文件、审计与图层字节，绑定当前语义候选；漏关节、重复ID、非有限数、越界点、
错误候选或冒充批准的字段均拒绝。`read_joint_draft` 通过语义候选的完整输入闭包复验。
不同内容使用新文件名；旧输出不覆盖。页面编号或辅助显示不是已生成/批准的骨架。

这个入口只生成待复核的 PSD 坐标标注，不生成真实 Pose Observation、JointCandidate、
RigIR 或生产授权。PNG 坐标的模型观测仍需单独验证 PNG↔PSD 映射；后续将把草稿复核、
自动候选对照和关节误差报告接起来。当前没有代替操作者录入真实关节位置。
