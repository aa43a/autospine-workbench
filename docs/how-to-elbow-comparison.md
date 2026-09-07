# 比较肘部辅助骨和 corrective deform

三方案使用相同三角形、UV、setup 和绑定来源，逐 1° 扫描 −90° 至 +90°。
本实验仅固定上臂、旋转肘部并让手部继承；不覆盖独立肩/腕或复合动作。

```powershell
python -m autospine_workbench.benchmark compare-elbow-deformation `
  --manifest docs/benchmark/manifest-frozen-v1.json --workspace .. `
  --mesh ../tmp/r2b-mesh/alice-joint-plane-v2.json `
  --html ../tmp/r2b-mesh/alice-elbow-v1.html `
  --output ../tmp/r2b-mesh/alice-elbow-v1.json
```

将 `alice` 替换为 `lingxian` 或 `crino` 可重放其他开发样本；未选多骨图层继续未评估。
报告 `elbow-comparison/v1` 使用独立内容地址，读取器重放精确来源并重算结果。
CLI 成功表示报告生成成功；各方案是否通过实验阈值见 `methods[].status`。

## 两条实现路线

设原近端权重为 `1-t`，远端两骨合计权重为 `t`，肘旋转为 θ：

- **半角辅助骨**：保留近端 `(1-t)²`，远端原权重各乘 `t`，额外肘骨权重为 `2t(1-t)`，
  额外骨绕同一肘点旋转 θ/2。每顶点最多四影响，归一化；未修改正式骨架。
- **旋转保持修正**：使用 `atan2(t sin θ, 1-t+t cos θ)` 旋转 setup 顶点到肘点的向量，
  保持该向量长度。空间变化的旋转角仍可能压缩局部面积，因此仍需相同 QA。
  将目标与原 LBS 的世界坐标差逆旋转到每个影响骨的局部坐标，得到可重建的 corrective 偏移。

数值测试验证辅助骨可用额外骨 LBS 表达，corrective 局部偏移可经原 LBS 精确重建。
这些不是 Spine 附件/时间轴编码或 Runtime 验证；要导出仍需采样时间轴、插值误差和版本适配。

## 结果与下一步

四张手臂原最小面积比约 12%–23%，辅助骨约 24%–38%，旋转修正约 19%–41%。
三方案逐度扫描均无翻转，但两种改进均未满足最小面积比 50% 的实验阈值。
当前不选择、不自动采用任何方案；原 mesh、权重与用户决定保持原地址。

辅助骨对四张手臂的收缩改善较稳定，可作为下一步局部约束修正的起点；
不能仅凭该结果批准通用四肢。下一切片应约束关节邻域面积与边长，同时保持刚性端部、
setup 和接触锚点，再测试是否需要关节支撑点；不降低阈值或删透明三角形绕过失败。
页面为同角度三列线框对照，尚无纹理 golden、接缝或官方 Runtime 证据。

[本切片验证记录](benchmark/elbow-comparison-2026-09-08.json)记录精确地址与逐方案数值。
32 项相关测试和文件长度检查通过；三个真实角色完成来源重放、Schema 校验、数值重算与 CAS 读回。
Chrome 核对 Alice 页面。未运行全量 Python/Web 或官方 Spine Runtime。
