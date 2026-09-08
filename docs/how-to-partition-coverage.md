# 分区网格覆盖修复与远端过渡对照

`improve-partition-coverage` 引用v1失败基线，生成独立的新网格profile。
默认保留 alpha≥8 的可见主组件检查，再为全部 alpha≥1 像素所在网格单元建立三角形。
因此不会因为透明碎片改变主组件判断，也不会删掉小碎片来消除覆盖缺口。
顶点/三角形上限、拓扑验证和变形QA阈值保持原要求。

```powershell
python -m autospine_workbench.benchmark improve-partition-coverage `
  --manifest docs/benchmark/manifest-frozen-v1.json --workspace .. `
  --mesh ../tmp/r2b-region-mesh/alice-v1.json `
  --html ../tmp/r2b-region-mesh/alice-coverage-v2.html `
  --output ../tmp/r2b-region-mesh/alice-coverage-v2.json
```

默认 profile 为 `partition-full-alpha-supported-v2`。
`--eligibility all-alpha` 保留早期 `partition-full-alpha-v2` 对照：它对全部alpha做主组件判断，
琪露诺左鞋因此仍被多组件检查阻塞。两个profile都能独立重放，不覆盖旧内容地址。

网格覆盖检查只证明源像素中心位于三角形中，不等于带过滤纹理采样、边缘raster或官方Runtime认证。
残余沿用原分区文件完整保留，未采用4px规则；旧绑定、原PNG、UV坐标规则和旧Mesh不改写。

## 踝/腕试验

本版候选仍使用原关节平面权重。另将远端权重起始位置移到关节平面的前侧半区，
输出独立 `distal_trials` 权重和QA。这些试验始终 `adopted=false`。
同一网格、骨架及角度范围用于对照；前移过渡并不能稳定解决翻转，部分案例更差，故未采用。
单骨鞋区域不做此试验。

本轮测试覆盖低alpha孤立像素、低alpha次级组件、旧主组件门槛、
setup重建、权重归一化、试验隔离、确定性和Schema。
12项相关测试通过，三个角色12个区域漏覆盖均为0，补齐原65个遗漏像素。
4个鞋区域通过当前数值与覆盖QA，8个肢体区域继续因远端变形阻塞。
8项前移过渡试验均未通过，未采用；未运行全量测试和官方Runtime。
真实结果见[验证记录](benchmark/partition-coverage-2026-09-08.json)。

下一步处理踝/腕局部的形变约束或corrective补偿，并继续使用既有探针范围对照。
不能以单纯收窄旋转角或移除第三骨影响掩盖问题，R3仍需组合动作与接缝验证。
