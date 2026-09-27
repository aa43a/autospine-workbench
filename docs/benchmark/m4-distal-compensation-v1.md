# M4 小腿与脚端补偿范围对照

日期：2026-09-27。状态：局部实验，不采用为生产结果。
接续 [共享顶点约束冲突](m4-shared-vertex-conflict-v1.md)。

## 方法与边界

新增显式实验选项 `distal_gain`：同一 calf/forearm 骨骼的所有影响使用一致
补偿强度。结合既有 corrected-surface transport 和 terminal anchor，保持
单骨表面的面积，保留 foot/hand 原有世界位置修正。骨轨道、权重、UV、拓扑和
其他附件不变。默认强度仍为 1，不改变线上工作流。

另一个空间渐变实验 `terminal_transition` 按骨链轴向位置衰减补偿。该方案
破坏单骨区域面积，真实两姿态产生固定三角形面积失败，已排除。保留独立实验
入口用于复现，不能将它描述为面积保持变换。

## 覆盖与结果

父包：`2424c43da460100d70b0c4d43ef380da86b999fd8daa8beba04e98480005479c`。
对象：Alice `external-motion` 的 `layer-001-l`。从已有 `regressions-v2.json`
选择全部 44 个可动区域退化的最差时刻，均作为精确补偿键。每姿态独立求解，
保护父包压缩下限和原正常区域，不放宽原 15.607425 px 位移预算或面积门槛。

| 固定小腿补偿强度 | 局部约束通过 | 面积下限失败记录 | 最大边长比 | 最大局部修正 px |
| --- | ---: | ---: | ---: | ---: |
| 0.25 | 42/44 | 16 | 1.883193 | 14.304129 |
| 0.125 | 43/44 | 8 | 1.999990 | 13.295480 |

两组均未检出新增翻转、父包压缩区域进一步退化或原正常区域失效，固定顶点
位移为零。但这些统计不能替代面积下限门禁；失败姿态仍明确失败。

0.25 在 0.70729179296875、0.7100261684570313 秒失败，均检出三角形
314/323 对共享顶点 196 的必要条件冲突。仅两个代表姿态通过不能外推全段。
0.125 仍在 0.7100261684570313 秒失败，且其他姿态边长已接近 2 的上限。
因此不继续将更小参数视作自动改进，不提升任一结果为已接受候选。

原始 setup 面积压缩仍存在，最小面积比约 0.225251；每姿态仍有 27–169 个
setup 面积失败。局部约束通过绝不意味着全角色几何或视觉通过。

## 可追溯证据

文件均位于 `tmp/m4-transverse-batches-v1/`：

- `terminal-transition-probe-v1.json`：被排除的空间渐变对照。
- `distal-quarter-all-counterexamples-v1.json`：SHA256
  `d78ff43ca265b0554ceb53c822a09e265f02e7bd5675e708a978a8bea3bf9725`。
- `distal-eighth-all-counterexamples-v1.json`：SHA256
  `a8251e2f8bd6c9f1f67cf9a26c2041a702e26b24be3c92409d08ea509983e47e`。

报告保存各姿态所有点、下限、失败三角形、必要条件反例和优化器结果；均为
`selected=false`、`authority=none`。0.25 报告生成于组合 profile 命名修正前，
其 `distal_gain=0.25`、anchor 和 correction-frame 字段完整保留，未改写原报告。

复现使用 `tools/m4_parent_pose_probe.py`，指定上述父包、slot、独立输出路径，
加 `--regressions ../tmp/m4-transverse-batches-v1/regressions-v2.json
--protect-setup --correction-frame transverse --exact-poses --anchor-terminal
--distal-gain .25 --local-refinement`（第二组改 `.125`）。

相关 86 项测试通过，包括单骨已修正表面的面积保持、末端位置保留、空间渐变
警示、面积约束和 Runtime 分批覆盖。最终 profile 命名与文档修正后补跑 11 项通过。

## 下一步

需要基于连接处可行约束选择补偿范围，而非对每帧独立调参数；必须同时保护
时间连续性、父包正常区域、接触和深度关系。然后再生成完整动画、执行密集
几何与官方 Runtime 验证。本轮没有新完整动画包、Runtime 捕获或视觉验收。
