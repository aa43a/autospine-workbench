# Pose observations v1/v2 参考

`autospine-pose-observations` 是外部姿态 adapter 与 AutoSpine 候选 provider 之间的规范边界。它描述一个已选中的人物、原画布像素坐标和检测器原生分数。

- v1 保持已有手工或外部 canonical 输入的只读兼容。
- v2 增加必需的 `adapter` provenance；`import-pose` 固定输出 v2。

两个版本都可由 `pose-alpha` 和 `evaluate-pose` 读取。完整 COCO17 输入、左右/镜像语义与评估合同见 [姿态 adapter 与评估参考](pose-adapter-reference.md)。

## 顶层字段

| 字段 | 含义 |
| --- | --- |
| `format` | 固定为 `autospine-pose-observations`。 |
| `format_version` | v1 为 `1`，带 adapter provenance 的版本为 `2`。 |
| `project_id` | 必须与 audit 项目 ID 相同。 |
| `source` | 被检测合成图的哈希和画布尺寸。 |
| `detector` | 检测器、模型、配置和运行时 provenance。 |
| `subject` | 上游检测到的人数及被选择的人。 |
| `adapter` | 仅 v2；输入合同哈希、坐标变换、左右、视角和镜像声明。 |
| `coordinate_system` | 固定的 top-left、Y-down 画布像素坐标。 |
| `joints` | 以规范关节 ID 为键的观测。 |

未知字段、重复 JSON 键、非有限数、越界坐标、错误哈希或坐标系都会被拒绝。文档最大为 1 MB。

## Source

`source.image_kind` 固定为 `composite`。`image_sha256` 必须是当前 audit `composite.png` 的字节哈希，`canvas_size` 必须与项目画布完全一致。

这项检查阻止以下输入被静默混用：

- 缩放后的模型输入图；
- 未还原到项目画布的左右镜像坐标；
- 裁切或补边版本；
- 另一个 seed 或角色的合成图。

模型可以在内部缩放或镜像图像，但 adapter 必须把输出坐标映射回原画布后再生成本合同。

## Detector

| 字段 | 规则 |
| --- | --- |
| `id` | 稳定的安全标识符。 |
| `version` | 检测器或检测流程版本。 |
| `model_revision` | 不可变仓库 revision、权重版本或发布标识。 |
| `model_sha256` | 可选；本地权重文件存在时建议填写。 |
| `config_sha256` | 预处理、输入尺寸、阈值和关节映射配置的 canonical 哈希。 |
| `runtime` | 例如 ONNX Runtime 版本与执行后端。 |

`detector_score` 保留检测器原生数值。不同模型、关节或版本的分数不保证可直接比较，也不被称为 `confidence` 或概率。

## Adapter（v2）

v2 的 `adapter` 与 `detector` 分开记录，防止 adapter 版本覆盖模型 provenance。当前支持 `coco17-limb-adapter/v1`，其中包括 raw 输入 canonical SHA、`identity|unmirror_x` 坐标变换、`as_reported|swap_left_right` 标签映射、视角、镜像状态和 6 位小数量化规则。

`coordinate_transform` 只处理完整画布的明确水平镜像；crop、resize、pad 或 letterbox 必须由模型专用 runner 先逆变换。`view_orientation` 和 `mirror_state` 是审计事实，不会自动推导或改写 `side_mapping`。

## Subject

单人检测使用：

```json
{
  "detected_count": 1,
  "selected_index": 0,
  "selection_method": "single"
}
```

多人结果必须使用 `manual`、`largest_area` 或 `tracker` 明确记录选择方式。`selected_index` 必须小于 `detected_count`。多人自动选择会在候选工件中继续保留 QA 提示。

## 规范关节 ID

当前四肢融合识别：

```text
shoulder.left   shoulder.right
elbow.left      elbow.right
wrist.left      wrist.right
hip.left        hip.right
knee.left       knee.right
ankle.left      ankle.right
```

可以只提供部分关节。缺失关节会保留 audit/bbox 候选并标记 `MISSING_POSE_OBSERVATION`，不会补造模型输出。

每个关节包含：

- `xy`：原画布中的 `[x, y]` 浮点坐标；
- `detector_score`：范围 `[0, 1]` 的检测器原生排序信号；
- `visibility`：`visible`、`occluded`、`out_of_frame` 或 `unknown`。

## pose-alpha 融合语义

provider 对相关肢体图层使用 alpha `>= threshold`，以 run-length 算法计算 8 连通域。小于 `max(16 px, 图层前景的 0.1%)` 的组件不参与最近轮廓证据。

alpha 是软约束：

- 原始 `pose` 候选始终保留；
- 只有最近有效 alpha 距离不超过画布对角线的 4% 时才生成 `fusion`；
- fusion 最多向 alpha 移动 35%，不会把遮挡关节硬吸附到衣物边缘；
- 超出范围时保留 pose，并标记 `ALPHA_SNAP_OUTLIER`；
- 所有输出分数均为 `score_kind=heuristic`，文档始终要求人工复核。

provider 的 run SHA 覆盖 project/resolved revision、pose 文档哈希、参与分析的 layer 语义、PNG 哈希、alpha 组件统计、配置和 provider 版本。

## 主要 QA flags

| Flag | 含义 |
| --- | --- |
| `HEURISTIC_SCORE_NOT_CALIBRATED` | 排序分数不是概率。 |
| `SIDE_CONVENTION_AMBIGUOUS` | 角色自身左右尚不能由元数据证明。 |
| `OPPOSITE_SIDE_LAYER_SELECTED` | 最近 alpha 来自相反 side 标签，可能存在命名约定冲突。 |
| `MISSING_POSE_OBSERVATION` | 该四肢关节没有外部观测。 |
| `NO_RELEVANT_ALPHA_LAYER` | 没有可用的对应肢体层。 |
| `BILATERAL_FUSED_COMPONENT` | 双侧图层只形成一个有效组件。 |
| `EXCESS_LIMB_COMPONENTS` | 双侧图层包含两个以上有效组件。 |
| `ALPHA_SNAP_OUTLIER` | 最近 alpha 超出软约束范围。 |
| `OCCLUDED_JOINT` | 衣物/遮挡使 alpha 无法直接观测关节。 |
| `SOFT_ALPHA_CONSTRAINT` | fusion 已使用有限幅度的 alpha 拉近。 |

JSON 的结构性定义分别以 [pose-observations-v1.schema.json](../schemas/pose-observations-v1.schema.json) 和 [pose-observations-v2.schema.json](../schemas/pose-observations-v2.schema.json) 为准。
