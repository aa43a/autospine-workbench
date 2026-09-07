# 生成实验性三骨加权网格

本入口消费已封存的v2绑定选择，只处理明确选择的单侧三骨链。
单骨保持刚性；未选择项不生成网格；双侧六骨目前明确返回 `bilateral_mesh_pending`。
本profile独立于历史P3 leg-only合同，不修改旧算法或历史地址。

```powershell
python -m autospine_workbench.benchmark build-weighted-mesh `
  --manifest docs/benchmark/manifest-frozen-v1.json --workspace .. `
  --draft ../tmp/r2b-multibone/alice-defaults-confirmed.json `
  --html ../tmp/r2b-mesh/alice-v1.html `
  --output ../tmp/r2b-mesh/alice-v1.json
```

同样替换为 `lingxian` 或 `crino`。HTML显示setup网格及逐角度QA表；CLI生成诊断报告
并返回0，不代表所有图层通过。必须查看每层 `status`、`reason_codes` 与 `qa.passed`。
重复构建幂等，来源图、骨架、绑定候选及选择草稿均精确回读。

当前算法是受限实验基线：

- alpha≥8，复用已有单显著连通域规则网格；步长为 `max(4, ceil(max(width,height)/32))`。
- 三骨权重为 `1/(骨段距离²+1)` 归一化，每顶点三个影响，不超过四骨目标限制。
- 每个影响保存逆setup变换的局部坐标，避免只导出权重而丢失LBS变换。
- setup和第二骨±30°/60°/90°共7个探针，第三骨位置和旋转继承第二骨的变化。
- setup误差≤1e-7、权重和误差≤1e-9，所有探针无翻转且最大边长比≤2才通过。

失败保留诊断网格、权重和数值结果，不把失败网格当作可发布资产。
多个显著连通域暂不合并、不填补透明间隙。检查的只是离散角度，
不包含连续角度保证、接缝质量、真实动作或官方Runtime证据。

网格报告使用独立16MiB上限的不可变存储，保持旧小型报告128KiB限制不变。
每次读取均验证规范字节与内容地址，再重建算法结果；输出冲突不覆盖已有文件。

本步尚未加入关节支撑环、轮廓约束三角剖分、刚性末端锁定、双侧多区域网格或接缝补偿。
下一步应根据本次失败位置改进关节附近拓扑和权重，再接完整Spine加权Mesh输出。

实际结果：Alice和铃仙各2张手臂图层生成网格，共4张。3张通过全部7个离散探针；
Alice `handwear-r` 的+90°探针有2个翻转三角形，保持blocked，其余探针未翻转。
setup最大重建误差约2.55e-13 px，权重和误差约2.23e-16。
琪露诺无已选的Mesh骨链，未擅自选择双侧绑定，因此没有生成网格。
[结果清单](benchmark/weighted-mesh-2026-09-08.json)记录地址、顶点/三角形数量及逐探针QA。

18项相关测试通过（核心、权重、CLI源闭包、大报告存储及质量门禁），实际报告通过Schema校验。
Chrome已检查Alice的setup叠图；未运行全量Python/Web或官方Runtime。
3张候选通过只表示本profile的离散数值检查通过，不等于通用Mesh/接缝或Spine输出完成。
