# 宽袖方向补偿与几何对照

2026-09-12。本轮没有替换已登记的挥手候选。

新增通用诊断工具 `tools/inspect-character-cloth-direction.py`，对显式指定的
既有腕部 cloth helper 比较 0/25/50/75/100% 祖先旋转补偿。
复用原方向驱动的来源、拓扑、腕部锚点、线性旋转限制，不按角色名写规则。
报告独立记录方向残留、网格面积/边长、首次失败时间，不自动选择任何比例。

真实输入为辉夜新基础包
`46473c7d22170126c300ba2c37ecea08d43cc642ed517fda74d05fba01474135`，
helper 为 `cloth-layer-003-component-0000`。
密集对照每组 517 个时间点，机器证据见 `character-cloth-direction-sweep-v1.json`。

| 补偿比例 | 最大残留祖先旋转 | 最小面积比 | 最大边长比 |
| --- | ---: | ---: | ---: |
| 0% | 154.22° | 0.45 | 1.45 |
| 25% | 115.67° | -1.61 | 2.47 |
| 50% | 77.11° | -4.04 | 3.98 |
| 75% | 38.56° | -4.77 | 6.03 |
| 100% | 0° | -6.42 | 7.46 |

这是未经面积修正的波形对照；0% 的面积失败不与已经修正并验证的当前挥手候选混淆。
旋转数值描述 helper 的方向，不声称最终布片自然下垂。
本试验否决这五个直接补偿方案，不能证明所有中间比例均不可行。
它支持下一步检查实际 sleeve/cuff/drape 的边界与固定顶点运动约束，
不能继续靠改变刚性根部旋转或扩大面积修正预算宣布问题解决。

验证：12 项方向/旋转/对照测试、3 项工程质量检查通过。
对抗测试覆盖方向完全固定但线性蒙皮塌缩，并核对无输入修改、无自动采用、确定性。
本轮只有 CPU 诊断，不冒充新的官方 Runtime 或视觉验收。

复现（项目根目录，PYTHONPATH=src）：

```text
python tools/inspect-character-cloth-direction.py --state-root workspace --character 46473c7d22170126c300ba2c37ecea08d43cc642ed517fda74d05fba01474135 --helper cloth-layer-003-component-0000 --samples 513 --output ../tmp/cloth-direction.json
```
