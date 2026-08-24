# 导入并评估 COCO17 四肢姿态

本指南面向正在把 Anime、ONNX 或 MMPose 推理结果接入 AutoSpine Workbench 的开发者。完成后会得到一份可供 `pose-alpha` 消费的 canonical pose，以及一份基于人工复核关节的诊断报告。

本流程不下载或运行姿态模型，也不宣称某个模型已经达到生产精度。模型专用代码只需把输出转换为固定的 COCO17 输入合同。

## 1. 把模型输出还原到项目画布

模型可以在内部 resize、crop、pad 或 letterbox，但写入输入合同时必须已经把坐标逆变换到 audit 的完整 `composite.png` 画布。

准备 `autospine-coco17-detections/v1` JSON。关键字段如下：

```json
{
  "format": "autospine-coco17-detections",
  "format_version": 1,
  "project_id": "seethrough_output",
  "source": {
    "image_kind": "composite",
    "image_sha256": "替换为composite.png的64位小写SHA-256",
    "canvas_size": [1024, 1024]
  },
  "detector": {
    "id": "your-coco17-detector",
    "version": "1.0.0",
    "model_revision": "不可变的仓库revision或权重版本",
    "model_sha256": "可选的权重文件SHA-256",
    "config_sha256": "预处理和推理配置的SHA-256",
    "runtime": "onnxruntime-1.x-cpu"
  },
  "coordinate_system": {
    "origin": "top_left",
    "x_axis": "right",
    "y_axis": "down",
    "units": "pixel",
    "side_naming": "coco_character_side",
    "image_space": "project_canvas"
  },
  "detected_count": 1,
  "detections": [
    {
      "keypoints": [
        [512, 170], [485, 155], [540, 155], [455, 170], [570, 170],
        [440, 300], [585, 300], [390, 430], [635, 430], [350, 560],
        [675, 560], [465, 555], [560, 555], [455, 735], [570, 735],
        [445, 920], [580, 920]
      ],
      "keypoint_scores": [
        0.9, 0.8, 0.8, 0.7, 0.7, 0.9, 0.9, 0.8, 0.8,
        0.7, 0.7, 0.9, 0.9, 0.8, 0.8, 0.7, 0.7
      ],
      "visibility": [
        "unknown", "unknown", "unknown", "unknown", "unknown",
        "visible", "visible", "visible", "visible", "visible", "visible",
        "visible", "visible", "visible", "visible", "visible", "visible"
      ],
      "bbox_xywh": [300, 120, 430, 850],
      "instance_score": 0.9
    }
  ]
}
```

示例坐标只是格式演示，不能用于真实角色。`keypoints` 和 `keypoint_scores` 必须各有 17 项；分数保留上游原生 `[0, 1]` 数值，不要重新命名为概率或 `confidence`。上游没有可证明的可见性时，可以省略 `visibility`，系统会使用 `unknown`，不会按分数猜测遮挡。

如果模型输入是完整画布的水平镜像，并且输出坐标还停留在该镜像画布中，把 `image_space` 写为 `horizontally_mirrored_project_canvas`。adapter 会执行明确的 `unmirror_x`。crop、pad、resize 或 letterbox 不能用这个选项代替专用逆变换。

## 2. 导入 canonical pose

```powershell
$env:PYTHONPATH = (Resolve-Path .\src).Path

python -m autospine_workbench import-pose seethrough_output `
  .\inputs\seethrough_output.coco17.json `
  --workspace .. `
  --state-root .\workspace `
  --side-mapping as_reported `
  --view-orientation front `
  --mirror-state not_mirrored
```

三个方向参数没有默认值：

- `side-mapping` 决定 COCO 解剖左右是否映射到同名角色侧；只有人工证据证明标签相反时才使用 `swap_left_right`。
- `view-orientation` 记录正面、背面、侧面、三分之四或显式 `unknown`，不会自动推导左右。
- `mirror-state` 记录项目合成图的镜像声明；它与坐标 `unmirror_x`、左右标签交换是三个独立概念。

多人结果还必须给出 `--selected-index` 和 `--selection-method manual|largest_area`。`largest_area` 要求每个人都有 `bbox_xywh`，并且最大面积唯一；并列时改用人工选择。

成功响应包含两条不可变路径：

```text
workspace/analysis/<project-id>/pose-adapter-inputs/<sha256>.json
workspace/analysis/<project-id>/pose-observations/<sha256>.json
```

后续命令使用响应中的 pose observations 路径，不要手工修改哈希工件。

## 3. 生成 pose-alpha 候选

```powershell
python -m autospine_workbench analyze-joints seethrough_output `
  --workspace .. `
  --state-root .\workspace `
  --provider pose-alpha `
  --pose-observations .\workspace\analysis\seethrough_output\pose-observations\<sha256>.json `
  --alpha-threshold 8
```

检查原始 `pose` 候选、受限移动后的 `fusion` 候选、来源图层以及 QA flags。alpha 仍是软约束，不能替代人工复核。

## 4. 用人工关节生成误差报告

先在工作台保存至少一个肩、肘、腕、髋、膝或踝的人工坐标，再运行：

```powershell
python -m autospine_workbench evaluate-pose seethrough_output `
  .\workspace\analysis\seethrough_output\pose-observations\<sha256>.json `
  --workspace .. `
  --state-root .\workspace
```

报告位于：

```text
workspace/analysis/<project-id>/pose-evaluations/<sha256>.json
```

重点检查：

1. `reference.reference_joint_ids` 是否只包含已人工调整的四肢点。
2. `metrics.reference_coverage` 是否足以支持当前结论。
3. `mean_error_px`、`rmse_error_px` 和 `mean_error_canvas_diagonal_ratio` 是否随模型或 adapter 版本改善。
4. `side_swap_diagnostic.lower_error_mapping` 是否为 `swapped`；若是，只回到导入阶段核对，不要直接改报告。
5. `qa.flags` 是否包含缺失参考、缺失观测或零重叠。

评估固定为 `qa.status=diagnostic`，不内置合格阈值。应先用真实样本建立基线，再为具体角色类别和动作需求制定门禁。

## 5. 常见失败

- `source hash does not match`：检测结果来自另一张图、重新编码图或错误项目。
- `coordinates must be original-canvas pixels`：输出仍在模型输入、裁切或 letterbox 空间。
- `Multiple subjects require --selected-index`：禁止静默使用第一个人。
- `Selected subject is not the unique largest bbox`：最大框并列或选择索引错误。
- `No manually adjusted limb joints are available`：先在工作台保存人工四肢参考。
- `SIDE_SWAP_COUNTERFACTUAL_LOWER_ERROR`：交换左右后的误差更低；这是诊断信号，不是自动修复。

字段和不变量见 [姿态 adapter 与评估参考](pose-adapter-reference.md)。
