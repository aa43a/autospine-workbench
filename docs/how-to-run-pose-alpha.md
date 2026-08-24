# 使用 pose-alpha 生成四肢候选

本指南面向已经能运行 AutoSpine Workbench、并拥有一个外部人体姿态检测结果的开发者。目标是把检测结果与 See-through 图层 alpha 证据融合，发布一份可人工复核的不可变候选工件。

`pose-alpha` 不运行姿态模型，也不生成 Spine 骨架。它只消费规范化观测，并验证观测是否确实属于当前项目的合成图。

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

## 2. 运行融合分析

```powershell
$env:PYTHONPATH = (Resolve-Path .\src).Path

python -m autospine_workbench analyze-joints seethrough_output `
  --workspace .. `
  --state-root .\workspace `
  --provider pose-alpha `
  --pose-observations .\inputs\seethrough_output.pose.json `
  --alpha-threshold 8
```

成功时命令输出 provider、run SHA、artifact SHA 和文件路径。相同项目 revision、pose 文档、图层 PNG、配置和 provider 版本会得到相同的内容地址。

## 3. 检查工件

候选文件位于：

```text
workspace/analysis/<project-id>/joint-candidates/<artifact-sha256>.json
```

对每个四肢关节依次检查：

1. `pose` 候选是否保留检测器原始坐标。
2. `fusion` 候选的 `source_layer_ids` 是否指向正确肢体层。
3. `layer_alpha` evidence 的 component、距离和面积是否合理。
4. `observability` 与遮挡情况是否一致。
5. 文档和候选的 `qa_flags` 是否需要回到工作台人工校正。

`heuristic_score` 只用于同一 provider 内排序，不是成功概率。工件固定为 `qa.status=manual_required`，不能直接进入自动导出。

## 4. 常见失败

- “source image hash does not match”：检测器使用了错误、缩放或重新编码的合成图。
- “canvas does not match”：观测坐标不在 audit 原画布空间。
- `SIDE_CONVENTION_AMBIGUOUS`：角色自身左右尚未由朝向/镜像元数据确认。
- `NO_RELEVANT_ALPHA_LAYER`：对应肢体图层缺失或已排除；保留 pose 候选并人工处理。
- `ALPHA_SNAP_OUTLIER`：pose 点离有效 alpha 太远，系统拒绝硬拉到轮廓。
- `OCCLUDED_JOINT`：例如长裙遮挡髋/膝，alpha 只能作为弱证据。

修正输入或人工决定后重新运行。不要直接编辑已发布的哈希工件；任何变化都应产生新的内容地址。
