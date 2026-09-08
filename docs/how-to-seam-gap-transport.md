# 附件运动补偿的空白轨迹对照

保留世界坐标关联 v1，新增 `dual-triangle4-consensus1-residual3-v1` 诊断。
本切片只改变关联候选，不改变栅格空白、Mesh、权重、动画或采用状态。

```powershell
python -m autospine_workbench.benchmark.seam_gap_transport_cli `
  --before ../tmp/r2b-continuous-anchor/alice-v1.json `
  --after ../tmp/r2b-seam-increment/alice-v1.json `
  --before-dir ../tmp/r2b-continuous-anchor/alice `
  --after-dir ../tmp/r2b-seam-increment/alice `
  --output-dir ../tmp/r2b-gap-transport/alice
```

输出 `autospine.seam-gap-transport/v1` 内容地址 JSON 和自包含轨迹复核页。
`read_transport` 重算本诊断并比对地址。源骨架、纹理及原同帧指标由既有 reader 路径核验；
source_tracks_sha256 绑定原世界坐标轨迹报告，旧报告地址不变。

## 局部运动预测

对相邻帧每对区域，分别以 driver 和 follower 的最近 Mesh 三角形预测质心运动：

1. 质心可位于三角形内部或距其最多 4px 的外部。透明空白并不被认定归属于三角形。
2. 保留质心的重心坐标，以下一帧同一三角形作局部仿射延拓，涵盖骨骼运动及既有 deform。
3. 等距三角形的预测分歧超过 1px，保留 unsupported；不任意挑选有利三角形。
4. driver／follower 的预测分歧超过 1px，拒绝本对关联。
5. 正向与反向都检查，最大质心预测残差 ≤3px 才产生候选边。
6. 沿用双向唯一匹配；分裂／合并歧义新开轨迹，不跨空帧，不闭合首尾。

旧基线用区域间最小像素距离，新 profile 用质心预测残差，语义不同且显式分版本。
几何邻近不是 alpha 边界法向证据；本版既不证明内外拓扑，也不据轨迹长短自动放行。

## 2026-09-08 实测

| 关系 | 原轨迹数 | 补偿轨迹数 | 最长观测帧数 |
| --- | ---: | ---: | ---: |
| Alice 左 | 6 | 4 | 3 |
| Alice 右 | 0 | 0 | 0 |
| 琪露诺左 | 70 | 22 | 20 |
| 琪露诺右 | 107 | 56 | 13 |

Alice 第 36–38 帧现在关联为连续三帧，其余空帧间隔不强行桥接。
全部 318 个新增像素样本保留。铃仙无接缝候选，不计为通过。
这些结果说明固定世界距离会断轨，不证明补偿后每条轨迹都是同一物理裂缝。

下一步围绕连续轨迹计算 driver／follower 的真实 alpha 边界距离、朝向与内外位置，
优先校准 Alice 的连续三帧；继续保留歧义与拒绝关联的证据，暂不修改权重或采用候选。
