# 固定原 deform 上的有界增量

本实验的基准为 `continuous-anchor-preview/v1`（f08fc66），不是上一轮退化的 `seam-shape-preview/v1`。保留该动画已有 follower deform，只在其上叠加有限新增位移。

## 固定参考与回退

重新计算当前带 deform 的锚点残差。沿用上一实验的点／切向位移／邻域平滑最小二乘产生增量方向，再限制最大新增位移为 2 px。原求解器的局部几何检查仅作为提案限制；最终准入始终重新检查固定 reference。

最终面积比例为 `当前候选帧面积 / 原 continuous 参考帧面积`，范围 0.5–2；边长也以该参考帧为分母，拉伸不超过 2。该参考只有原骨骼变换，没有 follower 接缝 deform，因此刚性 follower 的比例等同于相对原 setup 的比例，不能逐轮累计放宽预算。

每次二分缩小增量，还要求锚点残差平方和不高于原帧。最多检查 13 个尺度；无可行增量时记录 `retained_baseline`，加零增量保留已有修正，不删除旧 deform。setup／loop 端点不增加位移，原动画保持纯输入。

残差平方和不增加，并不能保证每个锚点、原像素对应或每个栅格像素都改善；因此 Bake 后继续检查全部原对应、60 FPS 几何、同帧走廊新增空白和官方 Runtime。

## 入口与工件

设置 `PYTHONPATH=src`，从仓库根运行：

```powershell
python -m autospine_workbench.benchmark.seam_increment_cli `
  --manifest docs/benchmark/manifest-frozen-v1.json --workspace .. `
  --source ../tmp/r2b-continuous-anchor/alice-v1.json `
  --directory ../tmp/r2b-seam-increment/alice `
  --output ../tmp/r2b-seam-increment/alice-v1.json `
  --zip ../tmp/r2b-seam-increment/alice.zip
```

合同为 `autospine.seam-increment-preview/v1`，profile 为 `fixed-deform-increment2-v1`；引用固定源包，重放并核对其地址和原 continuous JSON 字节摘要。reader 重建报告、文件和 ZIP 摘要。`shape_qa` 记录每帧增量、尺度、残差前后值及保留基准的回退。

输出 Spine 4.3.26 诊断包及同帧热图；官方 Runtime 外部包仍为 4.3.13。对照是“原连续锚点 Bake → 有界增量”，不是与上一轮退化形状版比较。各实验共同走廊不同，跨报告峰值不能混用。

本实验不产生正式采用或发布权。任何原对应或栅格退化都必须保留并说明，不能用总残差下降代替接缝视觉验收。

## 三角色结果与限制

四处原对应增距均低于 2 px：Alice 左／右 1.101901／1.727884 px，琪露诺左／右 0.278950／0.402776 px。12 个区域几何通过且无翻转，最大增量为 2 px（浮点误差约 4e-16）。

共同走廊空白峰值及新增空白帧：Alice 左 4 → 2、6 帧，右 3 → 1、0 帧；琪露诺左 6 → 5、42 帧，右 10 → 17、36 帧。铃仙无对应关系，不计为通过。原版峰值依赖本轮共同走廊，不应与上一轮不同走廊的峰值直接比较。

官方 Runtime 363 帧通过只证明编码／采样一致。热图中部分新增空白靠近外轮廓，现有走廊计数没有区分轮廓移动与真正的内部裂缝；不能据此确认所有新增点都是视觉缺陷，也不能静默排除它们。

本版未采用。下一步为空白增加空间归因与不确定性标记，明确可信接缝区域后再做逐关系、整段动画的增量准入。避免逐帧开关修正造成新的时间抖动。
