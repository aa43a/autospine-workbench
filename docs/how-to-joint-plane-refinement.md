# 改进三骨权重的关节过渡

Alice `handwear-r` 的旧网格在+90°有两个翻转三角形。诊断发现二者位于同一9×9轮廓支撑格，
离肘约69–79px，而不是肘点附近。该格只有1/81像素达到alpha阈值，但换三角形对角线仍会翻转，
不能简单归因于对角线选择。旧距离权重让此上臂区域保留约23%–30%的远端影响，产生局部折叠。
本次未删除该格，也未按透明度豁免QA。

新 `joint-plane-three-bone-v2` profile 保留原网格顶点、三角形和UV，使用独立权重算法：

1. 相邻两骨的单位方向相加并归一化，得到关节平面的法向。
2. 过渡半宽为相邻较短骨长的一半；按到平面的有符号投影生成smoothstep过渡。
3. 三骨权重为 `[1-t_elbow, t_elbow*(1-t_wrist), t_elbow*t_wrist]`，过渡区外锁定刚性端部。
4. 沿用原LBS局部坐标和全部7个QA探针，不放宽翻转与拉伸阈值。

算法不读取角色名字、不为某个角色单独改参数；反向退化关节或断开的骨段明确阻塞。
旧网格报告及旧权重保持原地址，新报告引用旧网格地址并独立封存，不能用改进报告再次递归改进。

```powershell
python -m autospine_workbench.benchmark refine-mesh-weights `
  --manifest docs/benchmark/manifest-frozen-v1.json --workspace .. `
  --mesh ../tmp/r2b-mesh/alice-v1.json `
  --html ../tmp/r2b-mesh/alice-joint-plane-v3.html `
  --output ../tmp/r2b-mesh/alice-joint-plane-v2.json
```

`lingxian`、`crino`同理。琪露诺尚无已选多骨图层，继续不生成网格。
页面同时显示setup数值QA与+90°前后网格线形状对照；后者不是带纹理渲染或官方Runtime证据。

这一步仅改进权重，尚未实现关节支撑环、轮廓裁剪、双侧网格、接缝补偿或独立腕部动作QA。
离散角度无翻转不意味着面积收缩、接缝、整体动画或连续时间质量全部合格。

真实结果：四张已选手臂网格全部通过原7个探针；另做每1°扫描，-90°到+90°各181个角度，
四张网格均0翻转，最大边长比约1.415。最小三角形面积比仍仅约0.124，
说明需要进一步处理局部收缩；此扫描没有升级为连续时间保证或正式质量批准。
[测量清单](benchmark/joint-plane-refinement-2026-09-08.json)记录每层结果和新旧内容地址。

21项相关测试通过（关节过渡、来源/拓扑保留、原LBS QA、存储和文件长度），
实际报告均通过独立Schema校验并精确源重放。Chrome检查了+90°网格线前后对照。
本轮没有运行全量Python/Web或Spine Runtime，也未生成正式Spine输出。
