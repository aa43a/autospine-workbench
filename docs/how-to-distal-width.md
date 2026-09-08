# Alpha横向宽度与远端权重过渡

这个独立试验以原始全alpha网格为输入，仅改变远端两骨之间的权重分配。
没有继续采用上一轮加密网格。骨架、顶点、UV、三角形、局部坐标、第一根骨骼权重和图层像素不变。

```powershell
python -m autospine_workbench.benchmark.distal_width_cli --manifest docs/benchmark/manifest-frozen-v1.json --workspace .. --mesh ../tmp/r2b-region-mesh/alice-coverage-v2.json --html ../tmp/r2b-distal/alice-width-v1.html --output ../tmp/r2b-distal/alice-width-v1.json
```

在远端关节法线前后各一个较短远端骨长的带状区域内，测量 alpha≥8 像素中心的最大横向距离。
将该半径乘以预设系数1、2、4作为过渡半宽下界候选；不缩小原过渡半宽，
并以相邻上游骨长45%限制扩展（若旧半宽已超过该限制，仍保留旧半宽）。
该限制只约束测量平面的扩展，不代表证明了对上游关节运动无影响。

保持旧权重的上游影响，重新分配下游总权重。每个试验重跑27个原始LBS单关节探针，
以及原48次投影、原位移预算、原QA门槛下的9个远端corrective探针。
报告保存所有三个固定系数，不选最佳项，不产生批准决定。
页面固定展示系数2的交互线框，仅供诊断；表格覆盖全部三个系数。

## 本次结果

系数4下，八处最小面积比均为正；五处通过全部9个远端corrective探针：
Alice左右踝、铃仙左踝、琪露诺左右踝。
铃仙右踝最小面积比约0.492，琪露诺左右腕约0.367／0.458，仍未通过0.5门槛。
不能为了这些样本降低门槛。

所有试验的原始LBS全链QA仍失败，corrective也还没有与主关节运动组合验证，
所以全部总状态保持blocked。较宽过渡会扩大手脚骨对上游图层的影响范围；
远端单关节通过不表示纹理观感、膝肘运动、组合动作或动态接缝通过。
下一步应固定此次三个策略，检验主关节与远端corrective的组合，并定位剩余三处失败，
而不是逐角色寻找恰好通过的系数。

19项针对性测试通过；三个报告通过Schema；Alice精确来源回放通过。
页面经Chrome截图检查，角度控制沿用已验证组件。未运行完整Python/Web套件或官方Runtime。
数据见[实验记录](benchmark/distal-width-2026-09-08.json)。

纯分析位于`asset/joints/distal_width.py`，来源回放和CLI位于`benchmark/distal_width_cli.py`。
`read_experiment`从原网格完整来源重新分析，比较内容地址，拒绝篡改；
输出使用现有16MiB内容寻址存储和独立Schema，旧corrective与网格profile保持原语义。
