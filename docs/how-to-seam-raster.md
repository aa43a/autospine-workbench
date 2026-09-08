# 接缝栅格与对应冲突诊断

本切片只分析已生成的 alpha 局部过渡候选，不再改变动画、网格或对应决定。

## 测量范围

在角色原生像素尺度下，以 30 FPS 对两秒动作取 61 个时刻。对每处接缝分别将两侧附件三角形逆映射到 UV，双线性采样 alpha；纹理外视为透明，同一附件三角形覆盖采用最大 alpha。以 alpha ≥8 定义覆盖。

沿对应边界采样之间的线段建立单像素走廊，记录走廊空白像素、双层覆盖像素、附近 ROI 的重叠像素。红色表示走廊内空白，蓝／绿为两侧附件，紫色为重叠。这是 CPU 的覆盖探针，不等同于 Spine 的混合渲染或完整 Runtime 栅格认证；没有检查所有未配对边界。

每个阶段导出空白像素最多时刻的热图。前后热图可能来自不同时间和 ROI，不能直接当作同帧差分。峰值计数也受走廊形状、像素量化和采样时刻影响，不能直接解释为裂缝面积降低的百分比。减少重叠不一定是质量提升，因此不据此自动通过。

## 三角色结果

|关系|空白像素峰值：原始 → 局部过渡|双层覆盖峰值：原始 → 局部过渡|对应数／互为最近|多对一目标最大分歧|
|---|---:|---:|---:|---:|
|Alice 左腿／鞋|15 → 4|37 → 19|16 / 4|1.012 px|
|Alice 右腿／鞋|15 → 2|54 → 20|17 / 4|2.547 px|
|琪露诺左腿／鞋|3 → 3|35 → 28|24 / 6|1.092 px|
|琪露诺右腿／鞋|3 → 2|67 → 57|48 / 22|0.979 px|

铃仙没有跨附件对应，不计为通过。四处接缝的原始与候选合计检查 488 个关系时刻，所有对应保留 pending。多对一的目标分歧按原动作计算：多个源边界点要求同一目标边界点到达不同位置时，记录这些要求的最大距离。重复对应不天然等于冲突，不因“互为最近”比例低就删除难点。

## 生成

仓库根目录设置 `PYTHONPATH=src` 后执行：

```powershell
python -m autospine_workbench.benchmark.seam_raster_cli `
  --manifest docs/benchmark/manifest-frozen-v1.json --workspace .. `
  --source ../tmp/r2b-alpha-seam/alice-v1.json `
  --directory ../tmp/r2b-seam-raster/alice `
  --output ../tmp/r2b-seam-raster/alice-v1.json
```

另两角色为 lingxian、crino。打开输出目录中的 `index.html` 查看热图和统计。报告合同为 `autospine.seam-raster-diagnostic/v1`，源 alpha 候选必须精确重放。还原的原动画必须逐字节匹配其已封存 skeleton JSON 摘要，否则阻塞；不把猜测的反向变换当作来源。

报告进入独立 CAS，热图记录内容摘要，reader 重建报告及图像摘要。NumPy/Pillow 仅在分析路径使用，不增加核心运行依赖。所有输出为 `authority:none`、`production_authorized:false`，状态 `needs_review`；官方 Runtime raster 状态保持 `not_evaluated`。

下一步优先解决 Alice 右侧的局部多对一冲突，保留其他对应作为对照，再用同帧、同走廊栅格检查约束变化。完整接触轮廓覆盖和官方 Runtime 分层 alpha 证据仍需补齐。
