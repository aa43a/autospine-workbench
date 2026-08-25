# 生成并复核四肢候选

本指南面向已经能运行 AutoSpine Workbench、并拥有一个外部人体姿态检测结果的开发者。目标是把检测结果与 See-through 图层 alpha 证据融合，发布可人工复核的不可变 pose、geometry 和 candidate 工件。

`pose-alpha` 发布 pose/fusion 候选；P1 推荐的 `pose-geometry` 还会发布 alpha 中轴线、层接触与可观测性证据，并把候选 fragment 固定到 geometry SHA。二者都不运行姿态模型，也不生成 Spine 骨架。

如果上游输出标准 COCO17，优先按 [导入并评估 COCO17 四肢姿态](how-to-import-and-evaluate-pose.md) 使用 `import-pose` 生成带左右、视角和镜像 provenance 的 v2 文档。下面的 v1 示例继续用于已有 canonical 输入。

## 1. 准备合成图和姿态观测

姿态检测器必须分析 audit 项目的 `composite.png`，不能分析另一个缩放、裁切或镜像版本。先取得文件哈希：

```powershell
$composite = "..\tmp\psd_audit\results\seethrough_output\composite.png"
(Get-FileHash $composite -Algorithm SHA256).Hash.ToLowerInvariant()
```

把检测器输出转换为 `autospine-pose-observations/v1`。最小示例：

```json
{
  "format": "autospine-pose-observations",
  "format_version": 1,
  "project_id": "seethrough_output",
  "source": {
    "image_kind": "composite",
    "image_sha256": "替换为上一步的64位小写哈希",
    "canvas_size": [1024, 1024]
  },
  "detector": {
    "id": "your-anime-pose-detector",
    "version": "1.0.0",
    "model_revision": "不可变模型revision或权重标识",
    "config_sha256": "替换为检测配置的64位小写哈希",
    "runtime": "onnxruntime-1.x-cpu"
  },
  "subject": {
    "detected_count": 1,
    "selected_index": 0,
    "selection_method": "single"
  },
  "coordinate_system": {
    "origin": "top_left",
    "x_axis": "right",
    "y_axis": "down",
    "units": "pixel",
    "side_naming": "character_side"
  },
  "joints": {
    "shoulder.left": {
      "xy": [630.5, 330.0],
      "detector_score": 0.82,
      "visibility": "visible"
    },
    "elbow.left": {
      "xy": [710.0, 455.0],
      "detector_score": 0.74,
      "visibility": "visible"
    },
    "wrist.left": {
      "xy": [780.0, 590.0],
      "detector_score": 0.63,
      "visibility": "occluded"
    }
  }
}
```

`left/right` 必须表示角色自身左右，不是画面左右。如果检测器只输出 image-side，而角色朝向或镜像状态尚未确定，先保留源结果并进行人工映射；不要通过交换字段名掩盖不确定性。

完整字段定义见 [pose observations reference](pose-observations-reference.md) 和 [JSON Schema](../schemas/pose-observations-v1.schema.json)。

## 2. 运行 geometry-bound 分析

```powershell
$env:PYTHONPATH = (Resolve-Path .\src).Path

python -m autospine_workbench analyze-joints seethrough_output `
  --workspace .. `
  --state-root .\workspace `
  --provider pose-geometry `
  --pose-observations .\inputs\seethrough_output.pose.json `
  --alpha-threshold 8
```

成功响应的 `artifacts` 按 `pose_observations → alpha_geometry_evidence → joint_candidates` 返回各自 SHA 和路径。三份文档会先完成语义和跨文档 fragment 校验，再按该 provenance 顺序逐件原子发布；某一步失败时不会继续发布下游，已完成的不可变上游可以复用。

只需要旧版 pose/fusion 软约束时，可把 provider 改为 `pose-alpha`；它不会生成 geometry artifact。相同 stage-scoped 项目、pose、有效图层语义与 PNG、配置和 provider 版本会得到相同内容地址；最终 joint decision/revision 不进入该身份。

## 3. 发布两份诊断样本

没有真实模型输出时，可用当前 resolved setup joints 验证 P1 工件链和 UI。默认处理仓库旁的两份 See-through 样本：

```powershell
python .\tools\publish_diagnostic_samples.py `
  --workspace .. `
  --state-root .\workspace `
  --alpha-threshold 8
```

只处理一个项目时，在选项前给出项目 ID：

```powershell
python .\tools\publish_diagnostic_samples.py seethrough_output `
  --workspace .. `
  --state-root .\workspace
```

工具不会写 override 或增加 revision。它把 resolved setup 四肢点写成 `detector_score=0`、`visibility=unknown` 的 diagnostic prior；重复输入应得到相同三组 SHA。这只能验证可复现发布和审查链，不能用于声称模型精度。

## 4. 在工作台复核

刷新工作台并切换到“关节”模式：

1. 选择关节和候选 artifact；比较列表中的 `pose`、`fusion`、`medial_axis`、`contact` 等方法。
2. 选择候选卡片或画布标记；带 geometry 引用的候选会按固定 SHA/fragment 加载对应 layer component、path 或 contact 覆盖。
3. 确认 `source_layer_ids`、可观测性、误差半径和 QA flags；`heuristic_score` 只用于同一 provider 内排序，不是成功概率。
4. 对候选选择“接受”“按当前位置调整”或“拒绝”；没有可靠候选时标记当前关节不可观测。后三类人工判断必须填写理由；adjust 使用当前 X/Y。
5. 保存校正后刷新，确认 revision 增加且决定读回。切换算法 artifact 时，旧决定仍显示其固定 SHA，不会静默套用。

工件位于：

```text
workspace/analysis/<project-id>/pose-observations/<pose-sha256>.json
workspace/analysis/<project-id>/alpha-geometry-evidence/<geometry-sha256>.json
workspace/analysis/<project-id>/joint-candidates/<candidate-sha256>.json
```

工件固定为 `qa.status=manual_required`，不能直接进入自动导出。只读 API 和 fragment 语法见 [分析工件参考](analysis-artifacts-reference.md)，保存语义见 [候选关节决定参考](candidate-decisions-reference.md)。

## 5. 常见失败

- “source image hash does not match”：检测器使用了错误、缩放或重新编码的合成图。
- “canvas does not match”：观测坐标不在 audit 原画布空间。
- `SIDE_CONVENTION_AMBIGUOUS`：角色自身左右尚未由朝向/镜像元数据确认。
- `NO_RELEVANT_ALPHA_LAYER`：对应肢体图层缺失或已排除；保留 pose 候选并人工处理。
- `ALPHA_SNAP_OUTLIER`：pose 点离有效 alpha 太远，系统拒绝硬拉到轮廓。
- `OCCLUDED_JOINT`：例如长裙遮挡髋/膝，alpha 只能作为弱证据。
- “geometry … does not exist/match”：候选引用的 SHA 或 fragment 不属于同时发布的 geometry 文档；不要手改哈希工件。

修正输入或人工决定后重新运行。不要直接编辑已发布的哈希工件；任何变化都应产生新的内容地址。
