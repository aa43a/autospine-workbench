# 固定边界的垂布局部形状试验

2026-09-12，继方向补偿试验后，引入独立的局部/全局 ARAP 形状试算。
保持全部非自由顶点为当前人体 FK 位置，仅选择现有 cloth helper 正权重顶点
作为自由顶点；不生成新的语义归属、不改原权重、不替换工作台动画。
每个自由连通区必须接触固定边界。解算使用保向局部旋转、边形状能量和弱方向位置先验，
支持前一时刻初始化，记录 NumPy/SciPy 版本，不声明物理重力或接缝通过。

辉夜新基础包 46473c7d22170126c300ba2c37ecea08d43cc642ed517fda74d05fba01474135
的左袖 cloth-layer-003-component-0000 共 123 个自由顶点。
全周期 33 等距点加原关键时刻，共 37 点；机器证据见 character-cloth-shape-trial-v1.json。
相对于直接世界方向保持，早期帧可消除翻转；全周期仍只有 5/37 点通过几何。
最大翻转数 4、最小面积比 -0.251675、最大边长比 2.722305。试验未采用。

这是稀疏的算法否决试验，不是连续时间证明。它未生成新的官方 Runtime 验收，
未覆盖碰撞、纹理接缝、方向视觉或 loop 精确闭合，也没有扩大既有面积修正的预算。
现有原始波形中固定手部自身的面积失败仍保留，不能因本解算只处理垂布就忽略。
下一步需要带面积/边长约束的布形求解，并与已通过的手部修正组合后重新检查。

14 项求解、方向及工程质量测试通过；覆盖 setup 重建、固定顶点不变、重复确定性、
不接触固定边界的区域拒绝和退化输入拒绝。新模块均少于 100 行。

复现（项目目录，PYTHONPATH=src）：

```text
python tools/inspect-character-cloth-direction.py --state-root workspace --character 46473c7d22170126c300ba2c37ecea08d43cc642ed517fda74d05fba01474135 --helper cloth-layer-003-component-0000 --shape-trial --samples 33 --output ../tmp/cloth-shape.json
```
