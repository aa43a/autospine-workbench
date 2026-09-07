# 开发集 PNG / PSD 坐标复核

本入口生成可以离线打开的复核页。原图、PSD 合成图和候选身份一并封装，
不需要复制 SHA。当前只开放冻结后的 development 分组，避免无意查看 holdout。

在仓库根目录执行：

```powershell
$env:PYTHONPATH = (Resolve-Path ./src).Path
python -m autospine_workbench.benchmark mapping-review --manifest docs/benchmark/manifest-frozen-v1.json --evidence docs/benchmark/development-audit-2026-09.json --workspace .. --character alice.psd --html ../tmp/benchmark-mapping/alice.html --output ../tmp/benchmark-mapping/alice.json
```

`--character` 可填写开发集的 PSD 文件名（alice.psd、lingxian.psd、crino.psd）、
PNG 中文名或 character id。有多个 PSD 版本时填写具体 PSD 文件名，不能静默选取。

打开生成的 HTML，比较两侧角色身份，再在叠加视图中调整缩放、平移和镜像。
缩放沿 X/Y 分别设置，平移使用 PSD 像素。坐标原点为左上角，X 向右、Y 向下：

```text
x_psd = scale_x * x_png + translation_x
y_psd = scale_y * y_png + translation_y
```

负 scale 表示对应轴镜像；例如水平镜像完整宽度 W 时，scale_x=-1、translation_x=W。
这里使用像素边界坐标，像素中心为 x+0.5/y+0.5。当前模型不表达旋转、剪切、非线性变形，
画布外点不会被裁掉或夹到边缘。大幅姿态/结构变化不能靠本候选解决。

初始值只是假设将 PNG 画布缩放到 PSD 画布；长宽比不同会产生非等比缩放，
不证明真实 See-Through 的缩放、裁切或补边方式。confidence 始终未知，不能用作自动采用依据。

点击下载草稿后，可用 `--draft` 验证并重新打开调整后的候选：

```powershell
python -m autospine_workbench.benchmark mapping-review --manifest docs/benchmark/manifest-frozen-v1.json --evidence docs/benchmark/development-audit-2026-09.json --workspace .. --character alice.psd --draft mapping-draft.json --html ../tmp/benchmark-mapping/alice-adjusted.html --output ../tmp/benchmark-mapping/alice-adjusted.json
```

同一内容重复导出是幂等操作；新内容需新输出文件名，不能覆盖先前记录。
候选保存在 `workspace/benchmarks/<dataset>/mapping-candidates/<sha>.json`，可用
`read_report` 读回并用 `validate_mapping_candidate` 绑定原 manifest 复验。

CLI 重读所选 PNG、PSD 与合成 PNG，核对大小、哈希和画布。候选绑定冻结 manifest、
两份源文件以及审计清单和合成图哈希；任一身份改变都会拒绝旧草稿。审计清单是输入证据，
本命令不重新运行 PSD 审计脚本，也不宣称验证了所有图层文件。

本页导出的是 `authority=none`、`review_required=true` 的候选，不是人工批准。
本切片不写主工作台 override，不填 Benchmark ground truth，不产生 policy_auto 决定，
也不更改历史 Spine 导出。正式人工映射决定、锚点残差和语义/关节标注是后续工作。
