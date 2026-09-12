# 布料压缩与主拉伸试验

2026-09-12。新增三角形变形梯度的主拉伸值分析，区分面积保持与方向性压缩/剪切。
指标相对于 setup 计算，对画布旋转、平移和统一缩放不敏感。
只检查与既有 cloth helper 正权重顶点相接的三角形，不改变人工服装归属。

求解可选 `--material`，内侧目标主拉伸 0.72–1.38；独立试验检查范围 0.7–1.4。
这些是明确版本化的探索参数，尚未跨角色校准，不作为永久发布规则。
当前材料约束作用于求解时刻，实际烘焙帧另行检查；几何、材料、视觉结果分开保留。

| 候选 | 最小主拉伸 | 最大主拉伸 | 最大方向比 | 材料失败时刻 |
| --- | ---: | ---: | ---: | ---: |
| 前版连续布形 bb5ae029… | 约 0.21 | 约 2.68 | 约 13.01 | 1003/1029 |
| 材料约束 f3dd3e21… | 约 0.53 | 约 1.43 | 约 2.08 | 251/1029 |

新完整候选：f3dd3e2135bfb7d69621126db30acef40812d43d2099fef4906df6eecf3a75be。
机器证据分别为 character-cloth-continuation-strain-v1.json、
character-cloth-material-strain-v1.json。新候选原网格与独立 1029 中点几何均通过，
见 character-cloth-material-midpoints-v1.json。

官方 spine-webgl 4.3.13 捕获新候选 1029 帧、25 附件，
最大位置误差 0.000196867 px。报告：../tmp/cloth-material-runtime/report.json。
直接检查第 256 帧：布片宽度较前版改善，但整体仍拱起，不能声称自然垂落。
**未采用，未替换工作台角色。** 69 个求解时刻中也有 9 个材料超限，
另有子帧压缩；下一步检查固定边界可行性并扩展子帧材料约束。

10 项材料分析、来源身份、求解/烘焙及工程检查通过。
对抗测试覆盖“原面积/边长检查通过但剪切严重”的情况。NumPy/SciPy 保持可选。

复现（PYTHONPATH=src）：

```text
python tools/build-character-cloth-wave.py --state-root workspace --wave c69947dcd79fd874a73f35a236d642f088e069837ccd7a57480e9c499e621b36 --helper cloth-layer-003-component-0000 --samples 65 --exact-temporal --continuation --material
python tools/inspect-character-cloth-strain.py --state-root workspace --bundle f3dd3e2135bfb7d69621126db30acef40812d43d2099fef4906df6eecf3a75be --helper cloth-layer-003-component-0000 --output ../tmp/cloth-material-strain.json
```
