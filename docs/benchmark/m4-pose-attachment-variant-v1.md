# 姿态网格附件切换

2026-09-24。`pose_attachment_variant.py` 允许在单一 slot 中按时间区间切换
原网格和姿态网格。新附件允许独立拓扑、UV 和 deform；原骨骼、绘制顺序、
其他区域及原附件保持不变。源文档摘要固定，已有附件切换轨道拒绝覆盖。
区间使用官方 Float32 有效时间检查，拒绝压缩成零长度的区间。

这与旧材质叠加不同：每个 slot 同时只有一个当前附件，不通过透明度混合
叠放两份表面。它没有自动保证硬切换时的轮廓连续性，也没有生成新姿态素材。
本切片仅为实验编译能力，尚未接入工作台默认修复或全角色候选采样器。

## 真实同表面对照

输入保持历史 `group-target-v2/hongmeiling/target-contact/runtime/player-assets/scene.json`。
对 layer-003 的三角形 116、117 作保真内部细分，得到不同顶点数的网格，
仅在 external-motion 的 0.7–1.2 秒启用它。原 deform 按影响项扩展并复制到
新附件名下，确保不是错误继承旧顶点编号。

`tools/check-pose-variant-core.mjs` 用现有官方 spine-core **4.3.13** 读取目标
Spine **4.3.26** 文档。238 个时刻包含 120 Hz 采样、区间两侧、精确有效边界、
反向跳转和循环。所有时刻 slot 数量不增加，附件选择符合区间，原顶点与
新增重心的最大世界坐标误差为 0.00008138020837122895 px。

文件：`localset/tmp/m4-motion-center/pose-attachment-variant-v1/` 中
`candidate.json`、`report.json`、`runtime.json`。这是隔离实验，未冒用父候选身份，
未重新捕获 GPU，未证明原膝部几何或视觉问题修复。

下一步可在此表示上接入允许局部边界变化的姿态网格，并同时检查边界连接、
纹理采样和切换跳变；不得将此次同表面回归计作大幅 Squat 验收。
