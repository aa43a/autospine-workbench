# 姿态 adapter 与评估参考

本文描述 COCO17 输入、canonical pose v2 和人工关节评估 v1 的机器合同。执行步骤见 [导入并评估 COCO17 四肢姿态](how-to-import-and-evaluate-pose.md)。

## 版本与 Schema

| 合同 | 用途 | Schema |
| --- | --- | --- |
| `autospine-coco17-detections/v1` | 模型专用 runner 与通用 adapter 之间的固定输入 | [coco17-detections-v1](../schemas/coco17-detections-v1.schema.json) |
| `autospine-pose-observations/v1` | 兼容已有手工/外部 canonical pose | [pose-observations-v1](../schemas/pose-observations-v1.schema.json) |
| `autospine-pose-observations/v2` | 带 adapter、左右、镜像和视角 provenance 的 canonical pose | [pose-observations-v2](../schemas/pose-observations-v2.schema.json) |
| `autospine-pose-evaluation/v1` | 对人工复核四肢点的阈值无关诊断 | [pose-evaluation-v1](../schemas/pose-evaluation-v1.schema.json) |

`analyze-joints --provider pose-alpha|pose-geometry` 与 `evaluate-pose` 同时读取 pose v1 和 v2。`import-pose` 固定输出 v2。v1 保持只读兼容，不会被原地升级。

## COCO17 输入

输入根必须固定项目 ID、`composite.png` 字节哈希、画布、检测器版本、不可变模型 revision、配置哈希和运行时。JSON 最大 2 MB，最多 100 人；未知字段、重复键、非有限数和越界像素中心均被拒绝。

每个人包含：

- `keypoints`：17 个 `[x, y]`，范围为 `0 <= x < width`、`0 <= y < height`；
- `keypoint_scores`：17 个检测器原生 `[0, 1]` 排序信号；
- `visibility`：可选的 17 个显式标签，缺省为 `unknown`；
- `bbox_xywh`：可选，使用 `largest_area` 人物选择时必需；
- `instance_score`：可选的人物级原生分数。

数组索引遵循 COCO17：

| 索引 | COCO 语义 | Canonical 输出 |
| ---: | --- | --- |
| 0–4 | nose、eyes、ears | v1 adapter 不输出 |
| 5 / 6 | left/right shoulder | `shoulder.left/right` |
| 7 / 8 | left/right elbow | `elbow.left/right` |
| 9 / 10 | left/right wrist | `wrist.left/right` |
| 11 / 12 | left/right hip | `hip.left/right` |
| 13 / 14 | left/right knee | `knee.left/right` |
| 15 / 16 | left/right ankle | `ankle.left/right` |

COCO left/right 表示人物自身解剖侧，不表示画面左右。adapter 不按屏幕 X 排序，也不把 COCO annotation 的 visibility `0/1/2` 当作 detector score。

## 坐标、镜像与左右

三个操作彼此独立：

| 字段 | 作用 | 是否改变坐标 |
| --- | --- | --- |
| `coordinate_system.image_space` | 声明检测坐标属于原项目画布或完整水平镜像画布 | 镜像画布会执行 `x' = width - 1 - x` |
| `adapter.side_mapping` | `as_reported` 或交换 left/right 标签 | 否 |
| `adapter.mirror_state` | 记录项目合成图的人工镜像声明 | 否 |

`adapter.view_orientation` 只记录 `front`、`back`、左右 profile、`three_quarter` 或 `unknown`，不推导 `side_mapping`。resize、crop、pad 和 letterbox 必须在模型专用 runner 中用显式逆仿射还原，不能由通用 adapter 猜测。

输出坐标和 detector score 统一量化为 6 位小数。canonical pose 仍使用 top-left、X-right、Y-down、pixel 和 `character_side`。

## 人物选择

- 一个人固定 `selected_index=0`、`selection_method=single`。
- 多人 `manual` 接受显式索引。
- 多人 `largest_area` 要求每项都有正面积且与画布相交的 `bbox_xywh`，选择必须是唯一最大框。
- 当前 COCO adapter 不接受 `tracker`，因为 v1 输入没有可验证的 track identity。

## Pose v2 adapter 字段

`adapter` 固定记录：

- `id=coco17-limb-adapter`、`version=1`；
- `input_format=autospine-coco17-detections/v1`；
- raw 输入 canonical SHA-256；
- `coordinate_transform=identity|unmirror_x`；
- `side_mapping`、`view_orientation`、`mirror_state`；
- `float_precision_decimals=6`。

检测器 provenance 保留在 `detector`；adapter provenance 不会覆盖模型 revision 或把 adapter 版本伪装成检测器版本。

## 评估参考与指标

评估器只从当前 `resolved.skeleton.joints` 中选择：

```text
review_state == manual_adjusted
且 joint id 属于 shoulder/elbow/wrist/hip/knee/ankle × left/right
```

自动 bbox 坐标、未复核点、面部/中轴点和 `legacy_review_confidence` 都不是真值。报告绑定 pose 文档 SHA、resolved snapshot SHA、override SHA 与 revision。

| 指标 | 定义 |
| --- | --- |
| `reference_coverage` | 人工四肢参考数 / 12 |
| `observation_coverage` | 有 pose 的人工参考数 / 人工参考数 |
| `mean_error_px` | 匹配点欧氏距离均值 |
| `median_error_px` | 匹配点欧氏距离中位数 |
| `rmse_error_px` | 欧氏距离的均方根 |
| `max_error_px` | 最大欧氏距离 |
| `mean_error_canvas_diagonal_ratio` | 平均误差 / 画布对角线 |

零重叠时 coverage 为 0，误差聚合为 `null`，报告仍可发布以记录失败。没有任何人工四肢参考时直接失败，不发布空报告。

## 左右交换反事实

`side_swap_diagnostic` 仅比较同时具备左右人工参考和左右 pose 的完整关节对：

- `as_mapped_mean_error_px`：当前标签对应的平均误差；
- `swapped_mean_error_px`：只交换左右参考对应后的平均误差；
- `lower_error_mapping`：`as_mapped`、`swapped`、`tie` 或 `insufficient`。

`swapped` 会增加 `SIDE_SWAP_COUNTERFACTUAL_LOWER_ERROR`。评估器不会自动交换字段、修改 pose 或设定合格阈值。

## 内容寻址工件

```text
workspace/analysis/<project-id>/pose-adapter-inputs/<raw-sha256>.json
workspace/analysis/<project-id>/pose-observations/<pose-sha256>.json
workspace/analysis/<project-id>/pose-evaluations/<evaluation-sha256>.json
workspace/analysis/<project-id>/alpha-geometry-evidence/<geometry-sha256>.json
workspace/analysis/<project-id>/joint-candidates/<candidate-sha256>.json
```

文件名是 canonical JSON 内容 SHA-256。相同内容幂等复用；已存在文件会重新验证，内容与地址不符时失败。任何输入、模型、映射、人工 revision、配置或实现版本变化都产生新地址。
