# M4 跨帧局部深度分区

本切片将局部像素深度诊断接到可播放的独立网格分区表示。未改变绘制
顺序，也未自动采用为工作台默认结果；尚不能称为侧身遮挡修复完成。

## 算法与边界

逐三角形收集与身体实际 alpha 重叠的像素深度状态，包括前、后、
前后混合、深度裕量不足、未知、无采样重叠。瓦片之间累加证据；若某帧
预算耗尽，丢弃该帧部分统计并标记未知，不能把已测部分冒充完整证据。

每个三角形按所有源帧与中间帧形成状态序列。相同序列可共用分区类别，
但最终附件只合并原三角形顺序中的连续区间，保留原纹理、UV、权重和
三角形绘制次序。同一三角形内部仍混合前后时，继续保留混合状态。

默认分区上限仍为 128。此独立实验显式使用 512 上限，不修改工作台
默认策略。精细时间序列可能产生过多附件，不能无限提高上限来宣称
生产可用。后续需要在保留证据与图像一致性的前提下控制分区复杂度。

新增压缩模块只保留每个分区实际使用的顶点，并按每顶点的骨骼影响数
重新映射 deform 坐标。支持线性/阶梯 deform；其它曲线明确拒绝。
原始稀疏 offset 可展开后映射。UV、权重、关键帧时间与变形值保持对应，
不复用原索引空间。原有不压缩分区 API 保持兼容。

## Alice 转身实测

- 原任务：`motion-02c7a8ea09d44cd0a7ed73ec452d6590`。
- 原候选：`a005044b2e3b0f94029749c6ec0e0e3392eb63c146230d181bbea78553ed3c7a`。
- 双臂生成 494 个连续绘制区域，检查 44 个源帧及 43 个中间帧。
- CPU 对应顶点误差为零；分区前后各捕获 87 帧官方 Runtime。
- 所有对应 framebuffer 的 RGBA 像素完全一致。
- 官方 Runtime 最大顶点误差：前后均约 `0.0000807782 px`。
- 不压缩 JSON 665,921,946 字节；压缩后 12,274,905 字节。
- 三角形/帧状态合计：前 6,952、后 12,210、裕量不足 4,692、内部混合 3、
  无采样重叠 43,829；没有未测状态。这些不是独立样本，也不是正确率。

来源为 BVH，中间帧使用来源通道插值；不是新增的真实动作观测。
原候选转身的背面素材限制仍保留。图像一致只证明表示变换，没有证明
原画面的遮挡正确，更不替代阶段视觉验收。

证据见 [Runtime 对比](benchmark/m4-temporal-partition-runtime-v1.json)。本地
输出目录为 `../tmp/m4-motion-center/temporal-depth-partition-alice-turn-compact-v1/`，
其中 `before/runtime/index.html` 和 `after/runtime/index.html` 可逐帧查看。

## 重现

在仓库根目录设置 `PYTHONPATH=src;tools`，使用已配置的官方捕获环境：

```powershell
python tools/m4_temporal_depth_partition.py motion-02c7a8ea09d44cd0a7ed73ec452d6590 ../tmp/m4-motion-center/temporal-depth-partition-alice-turn-compact-v1 --part-limit 512
python tools/m4_partition_runtime_compare.py ../tmp/m4-motion-center/temporal-depth-partition-alice-turn-compact-v1
```

这两个工具写入独立输出，不修改已确认角色、原动作任务或默认策略。
当前工具限制为未施加躯干投影形变的 BVH 候选，不能直接用于 Kimodo
或已投影变形的候选；这些场景已有独立深度采样器，但分区工具尚未接入。

## 兼容合并与时序约束

`--coalesce` 启用独立的连续区间合并策略。只有 `N`（该时刻无采样
重叠）可作为兼容项；前/后冲突不能合并，未知、裕量不足或混合也不能
被明确的前/后状态覆盖。原三角形状态计数和序列摘要保留在报告中。

Alice 转身的区域数从 494 降到 206，JSON 从 12,274,905 降到
7,203,527 字节。原候选与合并候选再次各捕获 87 帧，全部对应 RGBA
像素一致；最大 Runtime 顶点误差仍约 `0.0000807782 px`。证据见
[合并对比](benchmark/m4-coalesced-partition-runtime-v1.json)。输出目录：
`../tmp/m4-motion-center/temporal-depth-partition-alice-coalesced-v1/`。
206 仍超过默认 128 上限，本实验没有改变工作台默认上限。

时序约束模块将每个区域的明确前/后状态转换为所需前景附件；未知、
裕量不足、内部混合和无重叠均不会生成前景要求。该候选产生 131 个
明确前后关系之间的转变区间，全部标记为需要区间验证，不据此直接
生成已经通过的切换动画。分类统计是区域/采样时刻数，不是三角形数
或真实视觉错误率。

其中 16 个区域在全部已测重叠时刻保持同一方向，11 个需要相对于
原身体顺序调整。`tools/m4_stable_region_order.py` 对这类区域单独尝试
现有的可见部件交叉保护检查；其它区域保持原顺序约束。该实验不修改
原候选，得到结果后仍需官方 Runtime 和阶段复核。

实际交叉检查在 16 个时刻发现同一处顺序环：`layer-004-depth-120`
必须在上衣前方，同时原有可见裙装关系要求它在裙装后方；裙装又在
上衣后方。实测重叠存在，不能移除这些边来伪造通过。

`--safe-subset` 最多尝试四轮，使用同一 Probe 与共享像素预算，只将
顺序环中明确涉及的区域保留在原顺序。资源不足等错误不会通过删除
区域绕过。本例经过两轮，保留上述一处异常，余下 15 条单一方向关系
得到部分调整候选，包含六个绘制顺序关键帧；约使用 497 万像素预算。
这不处理其余混合/近共面区域，也不表示整个候选通过深度检查。

部分调整前后各捕获 173 个源帧、中间帧与区间中间时刻。官方 Runtime
数值检查通过，最大顶点误差约 `0.0000807782 px`。173 帧均有颜色
变化，最大差异帧为 `0.89166675 s`，改变 1,066 个像素。
查看该帧发现胸前局部袖布片段：部分显示与邻接未确定区域的遮挡不
连续。因此不能将这版视为已证明的视觉改善；保持实验状态，未采用。
后续必须加入相邻区域可见性连续性检查，再决定允许哪些局部调整。

证据：[部分顺序 Runtime 对比](benchmark/m4-stable-region-order-runtime-v1.json)。
可拖动时间轴与前后对照：
`../tmp/m4-motion-center/stable-region-order-alice-v3/index.html`。
它播放实际捕获帧，不生成帧间图像，也不会记录用户验收。

```powershell
python tools/m4_stable_region_order.py ../tmp/m4-motion-center/temporal-depth-partition-alice-coalesced-v1 ../tmp/m4-motion-center/stable-region-order-alice-v3 --safe-subset
python tools/m4_partition_runtime_compare.py ../tmp/m4-motion-center/stable-region-order-alice-v3 --allow-order-change
python tools/m4_partition_compare_review.py ../tmp/m4-motion-center/stable-region-order-alice-v3
```

拓扑排序改用按原 slot 序号优先的堆，避免分区增加后反复扫描全部约束
边。随机有环图与 DAG 对照测试验证其选择顺序与旧实现一致；未改变
排序策略和异常门禁。Chrome 检查覆盖最大差异帧、时间轴、播放暂停和
图片加载。

## 相邻显示连续性门禁

新增检查从原网格的共享边恢复分区邻接关系。若原本处于身体同一侧的
相邻区域被新顺序分到身体前后，在共享边两侧向三角形内部最多偏移
0.5 px 采样，确认原材质和遮挡部件的 alpha 均不低于 8/255。
每边采样 3–33 点；采样证据与三角形、区域、时刻和世界坐标一起保存。
这标记的是新出现的不透明显示切口，不能等同于已证明的裂缝。真正
合理的三维遮挡交界也可能触发，因此它用于保守候选门禁与异常定位。

预算耗尽明确返回 `incomplete`，不会作为无异常；原顺序、透明遮挡物、
同侧整体移动，以及不位于遮挡物内的共享边不会仅因邻接而触发。
非流形边与重复/缺失三角形归属拒绝继续分析。

Alice v3 在 173 个时刻产生 2,128 条边界记录，涉及九个提前显示区域。
`--continuity-guard` 将它们保留在 setup 顺序后再次求解，发现另一区域
产生 394 条边界记录。三轮后，十个连续性异常区域和原有一个顺序环
区域均保留原顺序，结果与输入完全相同。最终状态为
`no_supported_order_change`，不输出修复 skeleton，不把回到原结果
记作成功。原 16 条单向关系与所有失败证据仍保留。

本轮没有重新捕获 Runtime；检查的是上一轮已捕获的精确候选。
完整记录：`../tmp/m4-motion-center/stable-region-order-alice-v5/report.json`；
[冻结摘要](benchmark/m4-continuity-guard-evidence-v1.json) 包含原报告 SHA。

```powershell
python tools/m4_partition_continuity.py ../tmp/m4-motion-center/temporal-depth-partition-alice-coalesced-v1 ../tmp/m4-motion-center/stable-region-order-alice-v3 ../tmp/m4-motion-center/stable-region-order-alice-v3/continuity.json
python tools/m4_stable_region_order.py ../tmp/m4-motion-center/temporal-depth-partition-alice-coalesced-v1 ../tmp/m4-motion-center/stable-region-order-alice-v5 --continuity-guard
```

顺序实验现在要求新的空输出目录，避免一次未产出候选的运行留下旧
skeleton 供人误用。复现时请选择新的目录名，历史记录保持不变。
下一步需要同一帧内的连贯区域求解，不能只选择整段始终单向的小区域
提前显示。现有连续性门禁保留为该算法的回归检查，不能通过放宽它来
消除视觉问题。
