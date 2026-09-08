# 轨迹上的动态 alpha 边界证据

新增 `autospine.seam-gap-boundary/v1`，沿运动补偿轨迹逐像素测量两张附件的边缘距离和朝向。
动画、Mesh、权重、旧报告均不改变；结果始终 needs_review，无采用权。

```powershell
python -m autospine_workbench.benchmark.seam_gap_boundary_cli `
  --before ../tmp/r2b-continuous-anchor/alice-v1.json `
  --after ../tmp/r2b-seam-increment/alice-v1.json `
  --before-dir ../tmp/r2b-continuous-anchor/alice `
  --after-dir ../tmp/r2b-seam-increment/alice `
  --output-dir ../tmp/r2b-gap-boundary/alice
```

输出内容地址 JSON 和包含轨迹及逐像素边界证据的复核页。
`read_boundary` 重跑诊断并比对地址。source_transport_sha256 绑定旧补偿报告，来源文件与逐帧指标继续核验。

## 测量语义

使用同帧 CPU 双线性纹理采样后的 alpha≥8 占用掩码，提取填充／空白相邻栅格单元之间的有向边。
不将 ROI 裁剪边缘当作附件轮廓；法向由填充指向空白，坐标为世界 Y 向上。
距离是到线段的距离，保留所有并列最近边缘。它是阈值栅格单元边界，不是连续亚像素 alpha 等值线，也不是 GPU 栅格证据。

两侧最近边缘都在 4px 内，所有并列组合的朝向余弦均≥0.5，法向点积均≤-0.5，
才标为 opposed_facing_boundaries。仅部分组合满足时保留 ambiguous_boundary_ties；
没有组合满足为 no_opposed_nearest_boundaries；缺边界或超距为 insufficient_boundary_evidence。
以上标签均不是裂缝确认或放行判决。

对附件并集的空白作四连通检查：reaches_roi_edge 只说明连到本 ROI 边缘，不能证明角色外部；
enclosed_in_roi 只证明当前阈值及栅格邻接下局部封闭。敞开的裂缝也可以连到外部。

## 2026-09-08 实测

| 关系 | 相向边缘 | 并列歧义 | 最近边缘不相向 | 证据不足 |
| --- | ---: | ---: | ---: | ---: |
| Alice 左 | 1 | 6 | 0 | 0 |
| Alice 右 | 0 | 0 | 0 | 0 |
| 琪露诺左 | 0 | 18 | 41 | 40 |
| 琪露诺右 | 0 | 17 | 149 | 46 |

合计仍为 318 个跨帧像素样本。铃仙没有接缝候选，不计为通过。
Alice 第 36–38 帧均存在最近边缘并列歧义；37 帧局部封闭，36、38 帧连到 ROI 边缘。
52 帧两个像素中，一个具有明确相向边缘，另一个有并列歧义；两者都连到 ROI 边缘。

下一步检查双线性 alpha 等值轮廓及其法向，优先解释这三帧的栅格角点歧义。
不能删除并列边、把单附件／不相向计数当成正常外轮廓，或通过改权重消灭尚未校准的 QA 信号。
