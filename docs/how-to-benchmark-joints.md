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
RigIR 或生产授权。PNG 坐标的模型观测仍需单独验证 PNG↔PSD 映射；下述基线对照已接入，
草稿正式复核仍待后续。当前没有代替操作者录入真实关节位置。

## 与旧自动算法对照

`compare-joints` 复用历史 audit/bbox 算法生成17点基线，再与指定草稿逐点比较。
不指定 `--draft` 时使用全未标注草稿，不把基线复制成观察值。命令核验开发集素材、
audit、候选与草稿身份，输出可精确重放的报告及离线叠加页。

```powershell
python -m autospine_workbench.benchmark compare-joints --manifest docs/benchmark/manifest-frozen-v1.json --evidence docs/benchmark/development-audit-2026-09.json --workspace .. --character crino.psd --draft ../tmp/benchmark-joints/crino-pending-v1.json --html ../tmp/benchmark-joints/crino-comparison-v1.html --baseline-output ../tmp/benchmark-joints/crino-baseline-v1.json --output ../tmp/benchmark-joints/crino-comparison-v1.json
```

录点后把 `--draft` 改为下载的 `joint-draft.json`，并使用新的输出文件名。
橙色为旧算法猜点，绿色为草稿观察，复选框可独立隐藏。图中编号与右侧关节表对应。
每个已观察点输出像素距离和高度比；未标注、不可观测不参与距离统计。
报告单列 shoulder/hip/ankle 六个核心点的中位数，无可比较点时输出 `null`。

高度比分母取核验合成 PNG 非零 alpha 的垂直范围；包含头饰等内容，因此只是诊断用
归一化尺度，不等于已复核人体高度。不透明 RGB 或透明空图没有此尺度。精确读取器
`read_joint_comparison(..., workspace=...)` 重新核验实际源文件、基线算法和 alpha 高度，
不相信报告内自报的分母。Pillow 是此图像分析入口的可选依赖。

基线保留旧算法的 fallback、启发式分数和未复核左右侧，未接入新 Pose/Contact 融合。
距离参照仍是未经正式复核的草稿，固定标记 `diagnostic_only` 和 `unreviewed_joint_draft`，
不能用作 R2 精度达标、自动采用准确率或生产授权。下一步由 Contact Geometry 候选
与受约束关节优化器替换这些猜点，同时保留这个基线供改进对照。
