# 连续目标锚点的局部 Bake 对照

本切片将有界连续参数候选转换为实际 Spine deform 动画。为了分清变量，沿用原 `alpha_seam_bake` 的局部位移投影和平滑算法，暂不增加切线项、修改权重或扩大位移预算。

## 编译

精确重放参数、弧段、曲线及重配来源，核对输入内容地址。移除上一重配的 follower deform，重建并核对封存 continuous 源 JSON 摘要，再生成新的局部 Bake，避免重复叠加两个接缝修正。

仅替换 9 个可行组中的 100 个目标锚点：在分析副本中追加重心锚点并修改对应索引，保留全部 driver 和原对应身份。未处理的 5 条对应继续使用原始目标，不删除、不静默宣布通过。原 setup 偏移按新锚点重新计算；动画仍为 30 FPS、2 秒、首尾零修正。

局部求解仍使用 48 px 支持半径、12 px 位移上限和 40 轮投影／邻域平滑。几何门禁在 Bake 后检查面积比例、翻转、拉伸、有限数和 loop；目前不是求解过程中的保面积约束，失败会保留 blocked 候选。

## 验证口径

- 原像素中心对应重新验算全部接缝，避免更换目标后制造通过。
- 与之前 remapped 动画逐帧比较，在两版走廊并集上用同一 ROI 和像素网格检查空白、重叠及新增空白。
- 本轮“原局部重配 → 连续锚点”与此前“alpha 局部过渡 → 重配”比较对象不同，不能直接混用峰值。
- 官方 Runtime 验证新动画的编码、固定时刻播放及共享纹理采样一致性；不等同于完整角色视觉验收。

## 入口

设置 `PYTHONPATH=src` 后：

```powershell
python -m autospine_workbench.benchmark.continuous_anchor_cli `
  --manifest docs/benchmark/manifest-frozen-v1.json --workspace .. `
  --source ../tmp/r2b-continuous-parameters/alice-v1.json `
  --directory ../tmp/r2b-continuous-anchor/alice `
  --output ../tmp/r2b-continuous-anchor/alice-v1.json `
  --zip ../tmp/r2b-continuous-anchor/alice.zip
```

输出 JSON／Atlas／PNG、编辑器散图、内容寻址 QA、同帧热图和 `raster-review.html`。`autospine.continuous-anchor-preview/v1` 引用参数和重配工件；reader 完整重建报告和 ZIP 摘要。导出目标仍为 Spine 4.3.26，外部官方 Runtime 包为 4.3.13。

所有结果无生产权。下一步由实际原对应、栅格和面积结果决定是否值得在该锚点候选上增加切线与保面积求解，不能以参数单调或 Runtime 编码通过替代接缝验收。

## 三角色实测

12 个区域几何通过且无翻转。Alice 左／右原对应最大增距为 1.968960／2.338767 px；琪露诺左／右为 1.952775／1.698898 px。三处低于 2 px，但 Alice 右侧相对原重配版约 1.925 px 退化。

共同走廊空白峰值：Alice 左 4 → 4（3 帧有新增空白），右 2 → 3（9 帧有新增空白）；琪露诺左 3 → 3、右 2 → 2，均无新增空白帧。铃仙无接缝关系，不计为通过。

因此本版本不采用。官方 Runtime 363 帧验证只证明新动画编码及采样一致；下一步须处理真实动态栅格退化，而不是进一步降低单一距离指标。
