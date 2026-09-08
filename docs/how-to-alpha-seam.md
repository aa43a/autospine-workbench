# Alpha 边界与局部过渡约束

本切片以原连续候选为输入，替代邻近网格顶点测量：提取 alpha ≥8 的四邻域边界像素中心，按 UV 三角形保存重心坐标，再随网格插值跟踪真实纹理边缘的采样位置。三个角色共 10,219 个边界像素均成功映射，无未覆盖像素。

仅比较共享末端骨骼的多骨区域与单骨附件，setup 边界采样距离 ≤4 px 时建立最近对应，记录两侧采样索引。四处腿／鞋共 105 个对应；这是接触候选，不能证明遮挡关系或完整接缝覆盖，仍需复核。铃仙无跨附件对应。

## 局部约束

沿用 2 秒、30 FPS 的受限连续动作，保持原权重与骨链。根据腿的边界运动求鞋边界目标位移，将位移分配到边界所在三角形的顶点。使用 40 次松弛投影与 0.5 邻接平滑，支撑范围 48 px，位移上限 12 px；转换为单骨局部 deform，首尾归零。固定同一参数，不按角色或左右侧调节。

未平滑的初步试算曾使接缝缩小但鞋出现翻转，未导出为正式候选。当前平滑版本重新通过 60 FPS 网格采样检查，仍保留接缝超限状态。

|关系|边界对应数|原边界增距|局部约束后|状态|
|---|---:|---:|---:|---|
|Alice 左腿／鞋|16|7.560 px|2.005 px|blocked|
|Alice 右腿／鞋|17|9.079 px|2.390 px|blocked|
|琪露诺左腿／鞋|24|6.654 px|2.143 px|blocked|
|琪露诺右腿／鞋|48|7.016 px|1.685 px|候选待复核|

2 px 门槛不变，2.005 不能四舍五入后判为通过。12 个区域的面积比、拉伸、loop 与有限数采样通过，翻转为零；四只鞋最小面积比为 0.678、0.619、0.758、0.778。原网格顶点邻近诊断仍保留在 `bake_qa`，新的边界测量在 `alpha_seam_qa`，两者不能混用。

## 生成与播放

在仓库根目录设置 `PYTHONPATH=src`：

```powershell
python -m autospine_workbench.benchmark.alpha_seam_cli `
  --manifest docs/benchmark/manifest-frozen-v1.json --workspace .. `
  --source ../tmp/r2b-continuous/alice-v1.json `
  --directory ../tmp/r2b-alpha-seam/alice `
  --output ../tmp/r2b-alpha-seam/alice-v1.json `
  --zip ../tmp/r2b-alpha-seam/alice-v1.zip
```

另两角色为 lingxian、crino。输出 `autospine.alpha-seam-preview/v1`，profile `alpha-barycentric-smoothed-projection-v1`；保存边界像素、三角形重心映射、对应候选、前后 QA、约束范围和源连续地址。CLI 精确重建来源链，reader 重建并比较 CAS 地址。JSON Schema 与数字语义检查独立于人工批准。

官方播放使用已有验证工具，输出根目录设为 `r2b-alpha-seam`；参数见 [Runtime 说明](how-to-ownership-spine43.md)。目标 JSON 4.3.26，实际官方 Runtime 4.3.13。所有结果为 `authority:none`，未采用约束；当前仅一处边界关系达到采样门槛，不代表完整角色或连续时间证明。

下一项：针对仍超限的对应检查边界法线、局部拓扑和多对一冲突，建立保持三角形面积的约束求解；同时补动态 alpha 重叠／裂缝栅格检查。不能只增加迭代次数或放宽阈值。
