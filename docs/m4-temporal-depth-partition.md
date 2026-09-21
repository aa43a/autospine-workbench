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
