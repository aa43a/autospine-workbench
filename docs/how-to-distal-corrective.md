# 踝／腕局部 corrective 试算

`correct-distal-preview` 从全alpha覆盖网格重放来源，针对第三骨所在的踝/腕关节，
输出原LBS与修正线框对照，以及每个影响骨骼的局部偏移。
它不改变原权重，也不把失败试验写进 Spine 动画。

```powershell
python -m autospine_workbench.benchmark correct-distal-preview `
  --manifest docs/benchmark/manifest-frozen-v1.json --workspace .. `
  --mesh ../tmp/r2b-region-mesh/alice-coverage-v2.json `
  --html ../tmp/r2b-distal/alice-v1.html `
  --output ../tmp/r2b-distal/alice-v1.json
```

页面滑杆切换 -90/-60/-30/-15/0/15/30/60/90 度；红线为原LBS，青线为修正网格。
淡色原图仅为setup参照，不是带纹理的形变预览。展开表格可看每个角度的失败指标。

## 算法与约束

用远端骨权重生成半角辅助过渡基底，再做48次面积/边长投影。
目标面积比0.55–1.9、边长比1.9；验收仍是原来的面积比0.5–2、边长比≤2及零翻转。
只有远端权重严格介于0与1之间的顶点可移动，其他顶点固定。
位移预算为末两骨较短骨段长度的10%，相对于半角基底；不是相对于原LBS的总偏移上限。
setup精确保留，所有坐标必须有限。

最终坐标与原LBS之差转换到各影响骨骼的局部坐标，再用原权重重建，
独立记录偏移重建误差、固定顶点误差和投影位移。该偏移可供后续Bake使用，
当前没有做帧间插值、组合动作、接缝或Runtime验证。

## 真实结果

八个肢体区域都未通过本轮变形QA，selected_method保持null。
本轮只有2–6个混合权重顶点可移动；末端短骨约9–13.5px，投影预算约0.9–1.35px。
Alice另做了扩大可移动邻域的局部试验，保持位移预算不变仍未通过，未纳入已采用算法。
不能据此单独证明网格密度是唯一原因，但它是下一步优先验证的限制。

16项相关测试通过，覆盖确定性、setup、位移预算、固定顶点、局部偏移重建、Schema和滑杆切换。
真实计数与误差见[验证记录](benchmark/distal-corrective-2026-09-08.json)。
旧网格、权重、残余及已通过数值QA的鞋区域不改写；未运行全量测试或官方Runtime。

下一步为踝/腕局部加入按骨长控制的支撑点，形成无T接缝的网格，并保持完整alpha覆盖。
在同一位移预算和角度范围下比较，避免通过放宽阈值隐藏翻转。
