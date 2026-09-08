# 局部对应冲突重配

本切片沿用已有骨链、网格、权重和局部过渡求解器，只改变被诊断为冲突的边界对应候选。所有源边界点继续保留，没有通过删除失败点制造通过结果。

## 策略

多对一目标在受限动作中的分歧超过 2 px 时触发。为该组源点搜索原目标像素周围 8 px 内的边界样本，仍要求 setup 距离 ≤4 px，并保留其他组已占用的目标。以 setup 距离平方和最小为目标求完整一对一分配，确定性处理同分情况。

搜索最多 8 个源点、16 个目标候选；无法完整分配或超过预算时保留原组，明确阻塞，不输出部分采用。正常的多对一聚合不重配。局部邻近不证明语义接触正确，目标对应仍需人工或独立策略复核。

重配后使用原 40 次投影、0.5 邻接平滑、48 px 支撑和 12 px 位移上限重新 Bake，不改变参数。边界验算与栅格走廊继续使用原始对应集合，避免更换考题。此前 alpha 候选以及原连续 JSON 均须精确重建或匹配封存字节摘要。

## 结果

只有 Alice 右侧的一组被触发：6 个源点原先指向同一目标，现分配到 6 个不同目标；该侧仍保留全部 17 个源点。剩余多对一最大目标分歧从 2.547 降到 1.524 px。

|关系|原边界增距 → 重配后|CPU 空白峰值 → 重配后|
|---|---:|---:|
|Alice 左腿／鞋|2.005 → 2.005 px|4 → 4|
|Alice 右腿／鞋|2.390 → 1.925 px|2 → 1|
|琪露诺左腿／鞋|2.143 → 2.143 px|3 → 3|
|琪露诺右腿／鞋|1.685 → 1.685 px|2 → 2|

12 个区域网格采样继续通过，无翻转。两处边界关系达到 2 px 门槛，但 Alice 左侧与琪露诺左侧仍超限；CPU 空白采样也未全部消失。峰值可能来自不同帧，走廊随各版本边界运动，不能当作固定 ROI 同帧差分或完整 Runtime 栅格验收。

## 使用

在仓库根目录设置 `PYTHONPATH=src`：

```powershell
python -m autospine_workbench.benchmark.seam_remap_cli `
  --manifest docs/benchmark/manifest-frozen-v1.json --workspace .. `
  --source ../tmp/r2b-alpha-seam/alice-v1.json `
  --directory ../tmp/r2b-seam-remap/alice `
  --output ../tmp/r2b-seam-remap/alice-v1.json `
  --zip ../tmp/r2b-seam-remap/alice-v1.zip
```

另两角色为 lingxian、crino。报告为 `autospine.seam-remap-preview/v1`，profile `alpha-local-conflict-remap-v1`；记录原目标、源点集合、新对应、原集合 QA、栅格前后统计和纹理摘要。支持精确 reader 重放。

官方 Runtime 工具根目录设为 `r2b-seam-remap`，参数见[播放说明](how-to-ownership-spine43.md)。JSON 目标 4.3.26，实际 Runtime 4.3.13；叠加仍显示原对应。全部为候选，未产生接受决定或生产发布权。

下一步针对剩余非冲突接缝研究保面积约束和边界形状误差，并补同帧同走廊的栅格对照及完整 Runtime alpha 验证。不得把“四处点距都通过”直接等同于生产采用；还需完整接缝覆盖、重叠质量、代表动作及适用的采用合同。
