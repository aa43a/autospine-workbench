# 肘部局部约束预览

在半角辅助骨的结果上，使用固定顺序、48 次迭代的面积/边长投影修正。
不改变原 Mesh 顶点数、三角形、UV、骨架或已确认绑定，生成独立诊断报告。

```powershell
python -m autospine_workbench.benchmark correct-elbow-preview `
  --manifest docs/benchmark/manifest-frozen-v1.json --workspace .. `
  --mesh ../tmp/r2b-mesh/alice-joint-plane-v2.json `
  --html ../tmp/r2b-mesh/alice-constraints-v1.html `
  --output ../tmp/r2b-mesh/alice-constraints-v1.json
```

`lingxian`、`crino` 同理。CLI 成功表示报告写入成功，实际状态读取每层 `status`。
`benchmark.elbow_constraint_cli.read_constraints` 重放精确来源后重新计算数值。
无已选 Mesh 仍为 `not_evaluated`，不作为通过。

## 约束与质量边界

- 仅过渡区顶点可移动；近端/远端刚性区固定在辅助骨变形的位置。
- 三角形投影目标面积比为 0.55–1.9，边长比上限为 1.9。
- 单点相对辅助骨的偏移不超过相邻上臂/前臂较短骨长的 10%。
- 每次扫描固定 48 轮，固定遍历顺序；不保证任意输入收敛。
- 独立 QA 仍使用面积比 0.5–2、边长比不超过 2、零翻转，另检查 setup、端部锁定和位移预算。
- 不能满足 QA 则阻塞，不通过增大预算、删除三角形或调整角色专用参数绕过失败。

数值门槛是实验阈值，仍待 Benchmark 校准。修正点可通过各影响骨局部偏移在原三骨 LBS 中重建，
但尚未编码为 Spine deform timeline；没有自动采用、修改绑定或正式导出。
锁定的是刚性顶点，不是已验证的跨图层接缝；接触锚点和 seam 仍需后续处理。

## 下一步

将确定的角度序列 Bake 为逐帧 corrective 数据，验证关键帧之间的插值误差、带纹理栅格结果与接缝。
本次逐 1° 数值通过不能代替连续角度、独立肩腕、组合动作、纹理 golden 或官方 Runtime 验证。

## 实测记录

四张已选手臂均通过本项逐度 QA：最小面积比约 0.55，翻转为 0，最大边长比约 1.51；
局部修正最大约 2.91px，刚性端部误差为 0。琪露诺未选 Mesh，继续未评估。
[结果清单](benchmark/elbow-constraints-2026-09-08.json)保留精确地址和逐层数值。
37 项相关测试、Schema、真实 CLI 来源重放、数值重算和 CAS 读回通过；Chrome 检查 Alice 页面。
本切片未运行全量 Python/Web 或官方 Spine Runtime。
