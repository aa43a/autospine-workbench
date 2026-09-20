# M4 当前策略固定回归

本轮使用 [计划 v3](benchmark/m4-cohort-plan-v3.json)，重新执行 Alice、辉夜、红美铃与八类动作的 24 个组合。角色工件、原始动作字节和正面完整动作范围与 [旧基线](m4-fixed-baseline-results.md) 一致，复用已经验证的源导入任务。侧面行走试验单独保留，不替换本轮的正面行走。

固定执行策略：

- 支撑：`external-phase-contact-auto-v1`，先尝试全段静止支撑，再尝试源证据合格的局部支撑区间。
- 遮挡：`external-arm-torso-depth-overlap-v2`，原生 alpha 重叠检查与受保护的绘制顺序候选。
- Runtime 参考：`spine43-linear-weighted-float32-storage-v1`。

每个成功任务必须与计划中的策略一致，否则编排停止并保留任务记录。报告绑定具体候选身份；不能将旧候选的综合检查作为新候选的证据。旧基线的失败不被本轮覆盖，也不自动重试失败项。

从仓库根目录运行：

```powershell
python -X utf8 -u tools/m4_motion_cohort.py docs/benchmark/m4-cohort-plan-v3.json ../tmp/m4-motion-center/cohort-state-v3.json --steps 1000
python -X utf8 tools/m4_motion_cohort_report.py docs/benchmark/m4-cohort-plan-v3.json ../tmp/m4-motion-center/cohort-state-v3.json ../tmp/m4-motion-center/cohort-current-policy.html
```

第二条命令生成当时的快照，不是自动更新的仪表盘。第一条命令可从精确任务 ID 恢复；遇到不确定的提交标记时，先核对服务端是否已经接收，不能盲目重复提交。锁文件用于避免多个编排器同时提交。

报告分别展示任务、候选、综合检查、几何、Runtime 帧数、接触、遮挡和人工视觉状态。部分支撑区间修正成功不代表整段接地通过；Runtime 捕获完成也不代表几何和遮挡通过。人工阶段验收仍需针对本轮精确候选进行，不能继承原角色基础动作的验收。

本轮正在执行，尚不能给出完整支持率。完成后应保留逐项任务 ID、工件身份、Runtime 证据身份及综合检查，按失败阶段确定后续修复优先级。M4 尚未完成。
