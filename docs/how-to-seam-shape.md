# 局部切向位移约束与面积回退

本实验保留上一版连续目标锚点和全部原对应，改变局部 deform 求解器。没有改骨链、权重、纹理或扩大既有支持范围。

## 求解内容

每帧构造线性最小二乘问题，同时包含：

- 锚点位移误差，权重 1；
- 每个可行弧段组中相邻锚点的位移差误差，权重 2，除以不小于 1 px 的静态锚点间距；
- Mesh 边两端位移差，权重 0.08；
- 自由变量零偏移正则，权重 0.01。

这是一阶离散切向位移约束，目标来自原 driver 运动及 setup 相对偏移，不是独立曲率求解。48 px 支持范围外的自由度为零，范围内沿用平方衰减；全体位移缩放至最大 12 px。

在当前帧的世界空间 Mesh 上检查面积比例 0.5–2 和边拉伸不超过 2。若失败，以二分缩小位移，最多检查 13 个尺度；全部失败则记录 `blocked_no_admissible_step`，使用零新增位移保留可回放诊断。不得把这种回退当成求解通过。

帧内回退不保证帧间插值安全，因此 Bake 后仍以 60 FPS 检查整个动画。setup 和 loop 端点为零修正。求解器使用可选 NumPy；核心依赖环境不变。

## 来源与输出

先精确重放连续锚点 Bake 包，取其封存的同一套 mapped anchors，再重建并核对原 continuous 源 JSON 字节摘要。新求解结果替代上一局部 deform，不重复叠加两次修正。

```powershell
python -m autospine_workbench.benchmark.seam_shape_cli `
  --manifest docs/benchmark/manifest-frozen-v1.json --workspace .. `
  --source ../tmp/r2b-continuous-anchor/alice-v1.json `
  --directory ../tmp/r2b-seam-shape/alice `
  --output ../tmp/r2b-seam-shape/alice-v1.json `
  --zip ../tmp/r2b-seam-shape/alice.zip
```

设置 `PYTHONPATH=src` 后从仓库根运行。版本合同为 `autospine.seam-shape-preview/v1`，新增 `shape_qa`，不覆盖旧 profile；reader 重建报告与 ZIP 摘要。帧级记录包含切向约束数量、回退次数、实际尺度和锚点残差。

诊断包提供 Spine 4.3.26 JSON／Atlas／PNG、散图、原对应几何报告、CPU 同帧走廊差分及 `raster-review.html`。比较对象是“原连续锚点 Bake → 形状约束 Bake”，与更早的原重配对照不同，不应混用数值。

原对应重新验算全部四处接缝；CPU 栅格和官方 Runtime 分别提供证据，不互相替代。任何改善仍是候选，无生产权。最终采用必须同时解决动态退化与未覆盖区域，不能用单一距离或 Runtime 编码通过代替视觉验收。

## 实测：保留为负向实验

12 个区域几何通过、无翻转，最大回退次数为 2，未出现全部尺度都失败的帧。但 Alice 左／右原对应增距为 4.372／6.878 px，琪露诺左／右为 3.354／3.781 px，四处均超限。

本轮共同走廊空白峰值分别为 Alice 4 → 8、8 → 9，琪露诺 5 → 8、5 → 34；新增空白帧数为 22、30、36、37。共同走廊由当前两版动画的并集确定，原版峰值不能与上一轮不同走廊的峰值混用。原对应距离退化不受该走廊口径变化影响。

官方 Runtime 363 帧通过仅证明编码与采样一致。本固定参数配置不采用，也不替换之前的候选。本轮同时改变点约束解法、平滑形式和切向项，没有独立消融证据证明是哪一项单独造成退化。

下一项以固定原 deform 为基准，仅优化有限局部增量；面积检查使用原 setup 参考，不能每次以已变形帧作为新参考而累计放宽限值。增量回退到零应恢复原动画，而非撤销原接缝修正。
